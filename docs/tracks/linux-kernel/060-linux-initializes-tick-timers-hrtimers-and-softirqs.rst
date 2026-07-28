第六十章：Linux怎样建立时钟滴答、定时器与软中断基础？
===================================================

第五十九章结束时，CPU0已经具有IRQ描述符、x86向量账本以及FRED或IDT入口，但IF位仍为0。
``start_kernel()`` 接着执行：

.. code-block:: c

   tick_init();
   rcu_init_nohz();
   timers_init();
   srcu_init();
   hrtimers_init();
   softirq_init();

本章追踪到 ``softirq_init()`` 返回，停在 ``vdso_setup_data_pages()`` 之前。这六次调用建立的是
时钟滴答管理、软件定时器队列和软中断动作；硬件时钟事件设备、通用计时状态与x86时间初始化
仍在后续章节。

时钟源、时钟事件设备和时钟滴答层并不相同
--------------------------------------

时钟源提供可读取的连续计数，通用计时子系统用它计算时间；时钟事件设备可以在指定时刻产生
硬件事件；时钟滴答层选择时钟事件设备，并把事件交给周期更新、调度统计或无周期运行逻辑。

``tick_init()`` 不会注册TSC、HPET、PIT或本地APIC定时器。它只执行
``tick_broadcast_init()`` 和 ``tick_nohz_init()``，所以本章不能从函数名推断CPU0已经收到第一
次时钟中断。

``tick_broadcast_init()`` 申请广播管理掩码
----------------------------------------

有些CPU进入深度空闲后，本地时钟事件设备可能停止。广播机制用仍能运行的设备替这些CPU安排
唤醒。 ``tick_broadcast_init()`` 为 ``tick_broadcast_mask``、
``tick_broadcast_on`` 和临时掩码申请清零的 ``cpumask``；启用
``CONFIG_TICK_ONESHOT`` 时，它还申请单次广播、待处理和强制广播掩码。

这些 ``zalloc_cpumask_var(..., GFP_NOWAIT)`` 的结果没有在当前函数中检查。内嵌掩码构建不会
发生动态申请失败；使用栈外掩码的构建则依赖这些早期申请成功。无论哪种构建，当前函数都没有
选择 ``tick_broadcast_device.evtdev``，也没有为任何CPU安排到期事件。

``tick_nohz_init()`` 只处理全动态时钟滴答配置
--------------------------------------------

若启动参数阶段没有设置 ``tick_nohz_full_running``， ``tick_nohz_init()`` 立即返回。设置了
``nohz_full=`` 时，函数先确认架构能够用自身中断驱动 ``irq_work``；不具备该能力就清空
``tick_nohz_full_mask``、撤销全动态状态并返回。

满足架构条件后，某些挂起配置还要求把当前启动CPU从全动态集合移出，以保证至少有CPU承担
计时职责。函数随后对掩码中的CPU执行 ``ct_cpu_track_user()``，并登记一个CPU下线回调，阻止
承担 ``tick_do_timer_cpu`` 职责的CPU在不安全时下线。登记失败只产生警告。

固定GRUB命令行没有 ``nohz_full=``；未固定的内建命令行和 ``bootconfig`` 仍要求保留上述分支。
普通无周期空闲功能由 ``CONFIG_NO_HZ_COMMON`` 及后续设备、CPU状态共同决定，不能把当前短函数
写成已经停止CPU0的周期时钟滴答。

``rcu_init_nohz()`` 确定哪些CPU卸载RCU回调
----------------------------------------

Tree RCU构建中的 ``rcu_init_nohz()`` 先查看 ``tick_nohz_full_mask``。若
``CONFIG_RCU_NOCB_CPU_DEFAULT_ALL`` 要求默认卸载全部回调，并且启动参数还没有建立卸载集合，
它改用 ``cpu_possible_mask``。已有的 ``rcu_nocbs=`` 解析结果也通过
``rcu_state.nocb_is_setup`` 进入同一处理路径。

需要卸载而 ``rcu_nocb_mask`` 尚未取得内存时，函数尝试申请掩码；失败会打印信息并关闭本次
自动卸载。确定掩码后，它把不存在的CPU剔除，为每个入选CPU初始化或标记
``rcu_segcblist`` 的 ``SEGCBLIST_OFFLOADED`` 状态，并由
``rcu_organize_nocb_kthreads()`` 组织后续内核线程的分组关系。启用惰性RCU回调时，它还尝试
登记相应收缩器，申请失败只打印错误。

本章不会创建 ``rcuo`` 内核线程。相应创建函数要求 ``rcu_scheduler_fully_active``，实际线程
要在后续内核线程环境可用后启动。Tiny RCU构建中的 ``rcu_init_nohz()`` 是空函数，所以卸载
掩码和分组也不是所有构建的共同状态。

``timers_init()`` 建立逐CPU的低精度定时器队列
--------------------------------------------

``timers_init()`` 先调用 ``init_timer_cpus()``，后者遍历 ``cpu_possible_mask`` 中的每个CPU。对每个
``timer_base``，它写入CPU编号、初始化 ``raw_spinlock``，把 ``clk`` 设为当前
``jiffies``，把 ``next_expiry`` 放到定时器轮允许的远端位置，并初始化实时构建需要的到期锁。
应用处理器仍未上线，但其静态逐CPU队列从此具有初始时钟和锁状态。

启用 ``CONFIG_NO_HZ_COMMON`` 时，每个CPU有三个基：

* ``BASE_LOCAL`` 保存固定在本CPU的定时器；
* ``BASE_GLOBAL`` 保存可参与迁移的普通定时器；
* ``BASE_DEF`` 保存可延迟定时器。

未启用该选项时，三个名称都映射到同一个基。这个构建分支会改变对象数量，正文不把三套队列
写成无条件事实。

定时器轮按 ``jiffies`` 和分层槽位组织大量 ``struct timer_list``。它追求批量管理开销，而非
纳秒级到期精度。当前只初始化空队列；没有任何设备时钟事件推动 ``jiffies`` 周期增长。

``timers_init()`` 还调用 ``posix_cputimers_init_work()``，为当前
``init_task.posix_cputimers_work`` 清零旧工作项、登记 ``posix_cpu_timers_work`` 并初始化互斥
锁。该动作针对当前任务，不会创建POSIX用户定时器。

最后， ``open_softirq(TIMER_SOFTIRQ, run_timer_softirq)`` 把低精度定时器的软中断编号连接到
处理函数。 ``open_softirq()`` 可以早于 ``softirq_init()`` 调用，因为静态
``softirq_vec`` 已经存在；登记函数指针不表示相应软中断已经待处理或执行。

``srcu_init()`` 把早期SRCU对象转入正常排队路径
-------------------------------------------

Tree SRCU允许读侧临界区睡眠。 ``srcu_init()`` 首先根据 ``nr_cpu_ids`` 和构建参数决定采用
大型结构，还是先采用小型结构并根据争用转换。随后，它把 ``srcu_init_done`` 置为真；从这一
刻起， ``call_srcu()`` 可以走正常的延迟工作路径。

函数再遍历 ``srcu_boot_list``。对于启动阶段已登记的 ``srcu_usage``，它移除早期链表节点，
按尺寸策略更新状态，并把 ``work`` 排入第五十八章创建的 ``rcu_gp_wq``。源码要求这一步位于
RCU工作队列创建和 ``timers_init()`` 之后，当前调用顺序正好满足两项前置条件。

排入 ``rcu_gp_wq`` 仍不等于工作已经执行。普通工作线程尚未开始，队列中的SRCU工作要等待
后续 ``workqueue_init()`` 建立执行条件。Tiny SRCU采用另一实现，不具有这里描述的分层尺寸和
早期链表迁移过程。

``hrtimers_init()`` 只使CPU0的高精度定时器基上线
------------------------------------------------

``hrtimers_prepare_cpu(0)`` 遍历CPU0的各个 ``hrtimer_clock_base``，把它们连接到
``hrtimer_cpu_base``，初始化受自旋锁保护的序列计数器，并建立按到期时间排序的空
``timerqueue``。随后， ``hrtimers_cpu_starting(0)`` 清除上次下线可能遗留的活动标志、
下一定时器和到期值，把 ``expires_next`` 与 ``softirq_expires_next`` 设为
``KTIME_MAX``，最后把CPU0的 ``online`` 置为真。

其他可能CPU没有在本次调用中执行这两个函数；它们要在各自的CPU热插拔启动路径中准备。
``hrtimers_init()`` 最后把 ``HRTIMER_SOFTIRQ`` 连接到 ``hrtimer_run_softirq()``。

高精度定时器使用 ``ktime_t`` 和按到期时间排序的队列，与按 ``jiffies`` 分层的普通定时器轮
不同。软件队列已经存在不代表硬件具备纳秒级唤醒能力；它还需要合适的时钟源、支持单次事件的
时钟事件设备、高精度模式切换以及打开的IF位。

``softirq_init()`` 补齐逐CPU小任务队列
-------------------------------------

``softirq_init()`` 遍历 ``cpu_possible_mask`` 中的每个CPU，把普通 ``tasklet_vec`` 和高优先级
``tasklet_hi_vec`` 的尾指针分别指向各自头指针，使空链表可以接受第一个小任务。然后它登记：

.. code-block:: c

   open_softirq(TASKLET_SOFTIRQ, tasklet_action);
   open_softirq(HI_SOFTIRQ, tasklet_hi_action);

低精度定时器、高精度定时器和可能的RCU软中断处理函数已由各自初始化函数先行登记；当前函数
主要完成小任务队列和两项小任务动作。

软中断是一种执行上下文和待处理位机制，不等同于独立线程。它以后可以在硬中断退出等安全点
直接处理；负载过多时，也可由 ``ksoftirqd/N`` 接手。当前PID 2 ``kthreadd`` 尚未创建，
``ksoftirqd/0`` 因而不存在；IF位仍为0，也没有时钟事件把定时器软中断置为待处理。

本章结束状态
------------

``softirq_init()`` 返回后，时钟滴答广播掩码已经在正常申请路径中取得，全动态时钟滴答和RCU
回调卸载设置已按构建与启动参数处理。 ``cpu_possible_mask`` 中所有CPU的普通定时器基已经初始化，当前
``init_task`` 具有POSIX CPU定时器工作对象；Tree SRCU的早期对象已转入正常排队路径；CPU0的
高精度定时器基已上线；定时器、RCU及小任务所需的软中断动作已按配置登记。CPU0仍未打开
普通中断，也没有选定本地时钟事件设备。

关键边界
--------

* ``tick_init()`` 申请广播掩码并处理 ``nohz_full``，不会注册硬件时钟事件设备。
* ``rcu_init_nohz()`` 只组织回调卸载状态，不会在本章创建 ``rcuo`` 内核线程。
* 普通定时器基覆盖 ``cpu_possible_mask`` 中的所有CPU；高精度定时器本次只准备CPU0。
* ``CONFIG_NO_HZ_COMMON`` 决定普通定时器使用三个基还是一个基。
* ``srcu_init_done`` 允许正常排队，不代表排入 ``rcu_gp_wq`` 的工作已经执行。
* ``open_softirq()`` 登记动作，不会自行设置待处理位，也不会创建 ``ksoftirqd``。
* 本章没有初始化通用计时状态，没有使 ``jiffies`` 周期增长，也没有打开IF位。

下一入口
--------

``start_kernel()`` 的下一条语句是：

.. code-block:: c

   vdso_setup_data_pages();

第61章将从VDSO数据页进入 ``timekeeping_init()`` 和x86 ``time_init()``，区分已经建立的软件
队列与尚未完成的硬件时间来源。

资料
----

* `Linux 7.2-rc1 init/main.c：时钟滴答到软中断的调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1080-L1088>`_
* `Linux 7.2-rc1 kernel/time/tick-common.c：tick_init入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/tick-common.c#L588-L595>`_
* `Linux 7.2-rc1 kernel/time/tick-broadcast.c：广播掩码初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/tick-broadcast.c#L1238-L1247>`_
* `Linux 7.2-rc1 kernel/time/tick-sched.c：全动态时钟滴答处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/tick-sched.c#L647-L685>`_
* `Linux 7.2-rc1 kernel/rcu/tree_nocb.h：RCU回调卸载初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/rcu/tree_nocb.h#L1285-L1348>`_
* `Linux 7.2-rc1 kernel/time/timer.c：逐CPU定时器基与软中断动作 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/timer.c#L2552-L2580>`_
* `Linux 7.2-rc1 kernel/rcu/srcutree.c：SRCU正常排队切换 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/rcu/srcutree.c#L2099-L2129>`_
* `Linux 7.2-rc1 kernel/time/hrtimer.c：CPU0高精度定时器基 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c#L2505-L2539>`_
* `Linux 7.2-rc1 kernel/softirq.c：小任务队列与软中断动作 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/softirq.c#L1048-L1061>`_
