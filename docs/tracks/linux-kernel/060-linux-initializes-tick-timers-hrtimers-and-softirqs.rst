第六十章：Linux 怎样建立 tick、timer wheel、hrtimer 与 softirq？
================================================================

第五十九章结束时，Linux 已经建立 IRQ descriptor、x86 vector domain 和完整外部中断 gate，但 CPU0 的 IF 位仍关闭，也还没有可产生周期 tick 的 clock-event device。

``start_kernel()`` 接下来执行：

.. code-block:: c

   tick_init();
   rcu_init_nohz();
   timers_init();
   srcu_init();
   hrtimers_init();
   softirq_init();

本章追踪到 ``softirq_init()`` 返回，停在 ``vdso_setup_data_pages()`` 之前。

这一段建立的是软件时间队列和延迟执行入口。它先规定“时间事件以后怎样管理”，真正的 x86 PIT、HPET、Local APIC timer 或 TSC 初始化仍在后面。

clocksource、clock-event 和 tick 是三件事
--------------------------------------

时间系统中容易混淆的三个对象是：

.. code-block:: text

   clocksource
       → 回答“现在经过了多少时间”

   clock-event device
       → 在指定时间产生一次硬件事件

   tick layer
       → 使用 clock-event device 驱动 jiffies、调度统计和周期性内核工作

clocksource 是计数器，例如后续可能选择 TSC。clock-event device 是闹钟，例如 Local APIC timer、HPET comparator 或 PIT。tick 层位于二者之上，决定哪个 CPU 负责更新时间，并把硬件事件转成通用周期处理。

``tick_init()`` 只建立管理框架
----------------------------

``kernel/time/tick-common.c`` 中的实现很短：

.. code-block:: c

   void __init tick_init(void)
   {
       tick_broadcast_init();
       tick_nohz_init();
   }

它首先初始化 tick broadcast。

某些 CPU 进入深 idle 后，本地 timer 可能停止。broadcast 机制允许一个不会停止的全局设备替这些 CPU 安排唤醒事件。

随后 ``tick_nohz_init()`` 处理 NO_HZ 配置，使系统以后可以在 idle 或 full-dynticks 场景停止不必要的周期 tick。

当前固定命令行没有 ``nohz_full=``。这不影响通用 NO_HZ idle 基础存在，但不会在这里建立用户指定的 full-dynticks CPU 集合。

此时还没有 CPU0 tick device
--------------------------

``tick_init()`` 不会注册硬件 clock-event device，也不会立即设置：

.. code-block:: text

   tick_cpu_device[0].evtdev
   → Local APIC timer / HPET / PIT

第一次合适的 clock-event device 注册后，tick core 才会通过 ``tick_check_new_device()`` 选择它，并在初始 periodic 模式下安装 ``tick_handle_periodic`` 等处理器。

在此之前：

* ``tick_do_timer_cpu`` 仍处于 boot 选择状态；
* ``tick_next_period`` 尚未由正式 tick device 初始化；
* scheduler tick 不会自动到来；
* ``jiffies`` 不会因为当前这几条初始化调用自行增长。

``rcu_init_nohz()`` 处理 RCU callback offload
------------------------------------------

RCU 核心已经在第五十八章建立。当前 ``rcu_init_nohz()`` 进一步处理 NO_HZ 与 no-CB CPU 的关系。

在 Tree RCU 路径中，它检查：

* ``nohz_full`` 选出的 CPU；
* ``rcu_nocbs=`` 建立的 offload mask；
* ``CONFIG_RCU_NOCB_CPU_DEFAULT_ALL``；
* CPU possible mask 是否与用户配置一致。

若某些 CPU 被设为 no-CB CPU，普通 RCU callback 不再主要由该 CPU 自己处理，而会交给后续的 ``rcuo`` kthread 体系。

固定命令行没有 ``nohz_full=``、``isolcpus=`` 或 ``rcu_nocbs=``。若构建配置也没有要求默认全部 offload，``rcu_init_nohz()`` 在确认没有 no-CB 设置后直接返回。

即使配置了 offload，此时也只是建立 mask、callback list 标志和 kthread 分组关系。``rcuo`` kthread 仍要等内核线程环境可用后创建。

为什么 timer wheel 使用 jiffies
------------------------------

普通 ``struct timer_list`` 面向不要求纳秒精度的大量内核超时，例如：

* 驱动超时；
* 协议重传；
* 延迟清理；
* watchdog 检查；
* 缓存和连接生命周期。

它们以 jiffies 为主要时间单位。内核使用分层 timer wheel 把接近到期和远期 timer 分布在不同层级的 bucket 中，避免每个 tick 扫描全部 timer。

这种结构追求的是大量定时器的低管理开销，不是精确到某个纳秒立即执行。

``timers_init()`` 初始化每个 possible CPU 的 timer base
----------------------------------------------------

``kernel/time/timer.c`` 中：

.. code-block:: c

   void __init timers_init(void)
   {
       init_timer_cpus();
       posix_cputimers_init_work();
       open_softirq(TIMER_SOFTIRQ, run_timer_softirq);
   }

``init_timer_cpus()`` 遍历每个 possible CPU，而不是只处理当前 online 的 CPU0。

每个 CPU 的 timer base 会获得：

* CPU 编号；
* raw spinlock；
* 当前 base clock，初始为 ``jiffies``；
* 下一到期位置；
* 分层 wheel 的 bucket；
* 当前运行 timer 和 idle 状态。

AP 尚未上线，但它们未来上线时需要直接拥有已经定义好的 per-CPU timer base。

为什么一个 CPU 有多种 timer base
------------------------------

Linux 6.12.95 会区分本地 pinned timer 与可迁移 timer 等 base。

核心区别是：

* pinned/local timer 必须由目标 CPU 自己执行；
* global 或可迁移 timer 可以在 NO_HZ idle 场景迁给仍活跃的 CPU；
* deferrable timer 可以在 CPU idle 时延后，不必单独唤醒 CPU。

这样做可以减少空闲 CPU 因普通后台 timer 被频繁唤醒，同时保留必须在指定 CPU 上运行的语义。

``TIMER_SOFTIRQ`` 连接 timer 到 softirq
------------------------------------

``open_softirq()`` 把：

.. code-block:: text

   TIMER_SOFTIRQ
       → run_timer_softirq()

登记到 softirq action table。

以后 tick interrupt 会调用 ``run_local_timers()``。当发现 timer wheel 已到期时，它只 raise ``TIMER_SOFTIRQ``，真正的 timer callback 在 softirq 阶段运行。

这把硬中断中的工作限制为：

* 更新必要状态；
* 判断是否有 timer 到期；
* 标记 softirq pending。

较长的 callback 不直接堆在最底层硬中断入口中执行。

当前注册 handler 不代表 softirq 已经发生
--------------------------------------

``open_softirq()`` 只是把函数指针写入 softirq vector。

当前：

* 没有周期 tick；
* IF 位仍关闭；
* 没有设备 IRQ 触发 timer path；
* ``ksoftirqd`` 内核线程尚未创建。

所以 timer softirq 的入口已存在，pending bit 通常仍为空，也没有异步 callback 正在运行。

SRCU 为什么在 timer 之后初始化
----------------------------

SRCU 是 Sleepable RCU。普通 RCU read-side critical section 不能随意睡眠，SRCU reader 可以睡眠，更适合：

* notifier chain；
* 设备和总线对象；
* 某些文件系统或网络对象；
* 需要长时间持有读侧引用的控制路径。

``srcu_init()`` 的源码明确要求它位于 RCU workqueue 创建和 timer 初始化之后，因为正常 ``call_srcu()`` 需要 queue delayed work。

该函数：

#. 根据 CPU 数量和配置决定 SRCU 使用 small 或 big 结构；
#. 把 ``srcu_init_done`` 设为 true；
#. 遍历早期 boot list；
#. 将启动阶段积累的 SRCU work 转交给 ``rcu_gp_wq``。

第五十八章的 early workqueue 允许排队，worker kthread 仍未运行。因此这里可以把 SRCU work 放入队列，真正执行仍要等待正式 workqueue 环境。

hrtimer 与普通 timer wheel 的区别
--------------------------------

hrtimer 使用 ``ktime_t`` 和纳秒时间基准，适合：

* 高精度超时；
* ``nanosleep``；
* POSIX high-resolution timer；
* scheduler 和实时任务需要的精确事件；
* clock-event device 的 oneshot 模式。

它通常用按到期时间排序的红黑树，而不是按 jiffies bucket 放入 timer wheel。

两者关系是：

.. code-block:: text

   timer_list
       → 大量、低成本、jiffies 粒度

   hrtimer
       → 高精度、ktime、按绝对到期时间排序

``hrtimers_init()`` 先准备 CPU0
-----------------------------

``kernel/time/hrtimer.c`` 执行：

.. code-block:: c

   hrtimers_prepare_cpu(smp_processor_id());
   hrtimers_cpu_starting(smp_processor_id());
   open_softirq(HRTIMER_SOFTIRQ, hrtimer_run_softirq);

它为当前 CPU0 初始化 hrtimer CPU base、各 clock base、锁、active queue 和到期状态，并把 CPU0 的 hrtimer 状态推进到 starting。

其他 CPU 将在各自的 CPU hotplug 启动路径中执行对应准备工作。

随后登记：

.. code-block:: text

   HRTIMER_SOFTIRQ
       → hrtimer_run_softirq()

某些 hrtimer callback 可以在 hardirq 路径运行，另一些会被标记为 soft 模式并在 HRTIMER softirq 中执行。PREEMPT_RT 配置还会进一步改变默认投递上下文。

为什么 hrtimer 仍不能真正精确唤醒
------------------------------

hrtimer queue 已建立，不代表硬件已经能在任意纳秒位置产生中断。

高精度模式还需要：

* 合适的高精度 clocksource；
* 支持 oneshot 的 clock-event device；
* tick layer 切换到 oneshot/highres；
* CPU IF 位打开。

当前这些条件尚未全部满足，因此这里只是建立软件管理结构和回调入口。

``softirq_init()`` 补齐 tasklet softirq
------------------------------------

``kernel/softirq.c:softirq_init()`` 遍历 possible CPU，初始化：

* 普通 tasklet 链表；
* high-priority tasklet 链表。

然后登记：

.. code-block:: text

   TASKLET_SOFTIRQ
       → tasklet_action()

   HI_SOFTIRQ
       → tasklet_hi_action()

timer 和 hrtimer 的 softirq handler 已在各自初始化函数中登记，``softirq_init()`` 主要补齐 tasklet 两个 vector 和 per-CPU queue tail。

softirq 是执行上下文，不是独立线程
--------------------------------

softirq pending 通常可以在以下位置处理：

* 从硬中断退出时；
* 显式调用 softirq 处理路径时；
* pending 工作过多时由 ``ksoftirqd/N`` 接手。

当前 ``ksoftirqd/0`` 尚未创建，因为 PID 2 ``kthreadd`` 都还不存在。

所以此时应描述为：

.. code-block:: text

   softirq vector and per-CPU queues are initialized

不能描述为：

.. code-block:: text

   softirq threads are already running

本章建立了怎样的时间软件链
------------------------

本章结束后，软件关系已经形成：

.. code-block:: text

   future clock-event interrupt
       → tick handler
       → update jiffies / process time
       → inspect timer and hrtimer queues
       → raise TIMER_SOFTIRQ or HRTIMER_SOFTIRQ
       → run callbacks in softirq context

当前链条的硬件起点仍为空。x86 实际 timer device、初始 wall clock 和 clocksource 还没有在本章完成。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``softirq_init()`` 已返回，``vdso_setup_data_pages()`` 尚未调用；
* CPU：只有 CPU0 online；
* IRQ gates：已经安装；
* interrupts：IF 位仍关闭，``early_boot_irqs_disabled`` 仍为 true；
* tick core：broadcast 与 NO_HZ 管理框架已建立；
* CPU0 clock-event device：尚未在当前路径注册；
* scheduler tick：尚未开始；
* timer wheel：所有 possible CPU 的 timer base 已建立；
* TIMER softirq：handler 已登记；
* SRCU：进入正常 queue-delayed-work 模式，早期 work 可转入 RCU workqueue；
* hrtimer：CPU0 base 与 HRTIMER softirq 已建立；
* tasklet：普通和 high-priority per-CPU queue 已建立；
* ksoftirqd：尚未创建；
* jiffies：当前初始化调用本身不会让它周期增长；
* AP、initramfs、PID 1、PID 2：均未开始。

下一条控制流是：

.. code-block:: c

   vdso_setup_data_pages();

下一章建立 VDSO/VVAR 数据页和通用 timekeeping。x86 ``time_init()`` 还会揭示一个重要边界：真正的 PIT、HPET、TSC 与最终中断模式初始化被延后到 ``late_time_init()``。

资料
----

* `Linux 6.12.95 init/main.c：tick、timer、SRCU、hrtimer、softirq 与 timekeeping 顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 kernel/time/tick-common.c：tick broadcast、NO_HZ 与 tick device 管理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/tick-common.c>`_
* `Linux 6.12.95 kernel/rcu/tree_nocb.h：rcu_init_nohz 与 no-CB callback offload <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/rcu/tree_nocb.h>`_
* `Linux 6.12.95 kernel/time/timer.c：per-CPU timer base、timer wheel 与 TIMER softirq <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/timer.c>`_
* `Linux 6.12.95 kernel/rcu/srcutree.c：SRCU sizing、boot list 与 delayed work <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/rcu/srcutree.c>`_
* `Linux 6.12.95 kernel/time/hrtimer.c：CPU hrtimer base 与 HRTIMER softirq <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
* `Linux 6.12.95 kernel/softirq.c：tasklet queues、softirq vector 与 ksoftirqd 路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/softirq.c>`_
* `Linux timer wheel 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/timers/timers-howto.rst>`_