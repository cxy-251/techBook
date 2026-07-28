第五十七章：Linux怎样建立运行队列并登记CPU0的空闲任务？
====================================================

第五十六章结束时，伙伴系统、SLUB、虚拟地址映射管理器和早期追踪条件已经建立。CPU0仍在内核态执行
``start_kernel()``，当前任务是静态 ``init_task``， ``IF=0``。 ``cpu_possible_mask`` 中的每个CPU
已经拥有每CPU存储，
但调度器尚未初始化。本章从：

.. code-block:: c

   sched_init();

开始，追踪到函数执行完毕，并包含紧随其后的中断状态检查。章节停在 ``radix_tree_init()`` 之前。
本章会为 ``cpu_possible_mask`` 中的所有CPU初始化运行队列，为CPU0公布当前任务和空闲任务，并将
``scheduler_running`` 设为1；它不会调用 ``schedule()``，也不会创建PID 1或PID 2。

调度类链接顺序是启动硬条件
--------------------------

``sched_init()`` 首先通过 ``BUG_ON`` 检查调度类在链接器段中的顺序：

.. code-block:: text

   stop > deadline > real-time > fair > idle

启用 ``CONFIG_SCHED_CLASS_EXT`` 时，还要满足 ``fair > ext > idle``。顺序不符会立即终止启动，
运行时不会重新排列这些对象。

随后， ``wait_bit_init()`` 初始化固定大小为256的 ``bit_wait_table``，为每个槽建立等待队列头。
这里只建立按地址和位编号散列的等待队列，没有任务入队，也没有发生睡眠。

根任务组与默认根域先建立
----------------------

按照组调度配置，内核为 ``root_task_group`` 初始化CFS带宽，并按需建立扩展调度组或RT调度实体与
运行队列指针数组。 ``init_defrootdomain()`` 初始化
``def_root_domain`` 的 ``span``、 ``online``、截止期限与实时调度相关掩码和优先级结构，然后把
``refcount`` 设为1。

``init_rootdomain()`` 的返回值在这里没有被检查。正常执行到本章出口要求其中的分配全部成功；
如果分配失败，源码没有可继续使用空根域的恢复路径，后面的 ``rq_attach_root()`` 也无法
建立有效关系。

启用 ``CONFIG_CGROUP_SCHED`` 时，函数创建 ``task_group`` 缓存，把 ``root_task_group`` 加入全局
链表，并通过 ``autogroup_init(&init_task)`` 建立启动任务的自动分组条件。这一步没有挂载
``cgroupfs``，也没有创建子控制组。

每个可能CPU先建立运行队列再连接根域
----------------------------------

``for_each_possible_cpu(i)`` 取得 ``cpu_rq(i)``，依次初始化原始自旋锁、运行任务计数、负载状态、
CFS、RT和DL队列，并按构建配置初始化组调度、NO_HZ、CPU热插拔、高精度调度时钟滴答、
输入输出等待、扩展调度、核心调度与缓存相关字段。

连接根域之前，函数先写入：

.. code-block:: text

   rq->sd       = NULL
   rq->rd       = NULL
   rq->cpu      = i
   rq->online   = 0
   rq->next_class = idle_sched_class

随后， ``rq_attach_root(rq, &def_root_domain)`` 在运行队列锁保护下为根域增加一份引用，把CPU
加入 ``def_root_domain.span``，并将 ``rq->rd`` 指向该根域。因此，所有可能CPU连接完成后，
正常路径上的 ``def_root_domain.refcount`` 为基础引用1再加可能CPU数量。

``rq_attach_root()`` 还检查 ``cpu_active_mask``。CPU0已经在早期启动中标记为活动状态，所以它立即执行
``set_rq_online(rq0)``：

.. code-block:: text

   rq0.online = 1
   CPU0加入def_root_domain.online

其他应用处理器尚未进入活动状态，对应运行队列继续保持 ``online=0``。因此，初始化循环中短暂写入
``rq0.online=0`` 不能当作本章出口状态；可能CPU拥有运行队列也不等于相应CPU已经开始执行。

循环末尾通过 ``zalloc_cpumask_var_node()`` 为每个运行队列取得 ``scratch_mask``。未启用
``CONFIG_CPUMASK_OFFSTACK`` 时该操作使用内嵌掩码并总是成功；启用该配置时它可能分配失败，而
``sched_init()`` 没有检查返回值。正常出口因而以这些掩码分配成功为前提，源码没有在此提供降级路径。

``init_task`` 先取得调度状态和惰性TLB引用
----------------------------------------

运行队列循环结束后，内核设置 ``init_task`` 的负载权重和公平调度时间片。紧接着，
``mmgrab_lazy_tlb(&init_mm)`` 增加 ``init_mm`` 的惰性TLB引用，
``enter_lazy_tlb(&init_mm, current)`` 让当前内核任务使用该活动地址空间。
``init_task.mm`` 仍为 ``NULL``，它没有用户地址空间。

``set_kthread_struct(current)`` 为当前任务分配内核线程元数据；失败只产生警告。随后
``__sched_fork(0, current)`` 按新任务初始化路径重置当前任务的调度实体状态。这里没有复制
``task_struct``、分配PID或创建子任务。

``init_idle()`` 在两把锁下公布CPU0的空闲任务身份
----------------------------------------------

当前 ``smp_processor_id()`` 为0。 ``init_idle(current, 0)`` 先通过
``raw_spin_lock_irqsave(&idle->pi_lock, flags)`` 锁住任务，再取得CPU0的运行队列锁。两把锁保护下，
函数把任务状态设为 ``TASK_RUNNING``，记录 ``se.exec_start``，设置
``PF_KTHREAD | PF_NO_SETAFFINITY``，并把它登记为CPU0的每CPU内核线程。

启动阶段不需要通常的亲和性验证和迁移串行化，因此函数直接把允许CPU掩码收缩为CPU0，再在RCU
读侧区间写入任务所属CPU。随后公布四个关键字段：

.. code-block:: text

   rq0.idle          = init_task
   rq0.curr          = init_task
   init_task.on_rq   = TASK_ON_RQ_QUEUED
   init_task.on_cpu  = 1

释放运行队列锁和 ``pi_lock`` 后，函数在锁外设置空闲任务的抢占计数，将调度类改为
``idle_sched_class``，初始化函数图追踪和虚拟时间的空闲状态，并把任务名写成 ``swapper/0``。

同一个 ``init_task`` 仍在执行 ``start_kernel()``，同时已经成为CPU0没有其他可运行任务时使用的
空闲任务。它尚未进入 ``cpu_startup_entry()`` 的空闲循环；公布 ``rq0.curr`` 和 ``rq0.idle`` 也没有
触发任务切换。

调度器最后公布全局可用状态
--------------------------

启用通用SMP空闲线程支持时， ``idle_thread_set_boot_cpu()`` 把
``idle_threads[0]`` 指向当前任务；其他构建路径为空操作。随后，内核关闭CPU0的负载均衡推出状态，
初始化完全公平调度类和扩展调度类的全局部分、PSI与利用率钳制。

启用 ``CONFIG_PREEMPT_DYNAMIC`` 时， ``preempt_dynamic_init()`` 根据构建默认值以及第五十四章通过
``__setup("preempt=", ...)`` 解析的参数，在 ``none``、 ``voluntary``、 ``full`` 和可用的
``lazy`` 模式中确定一项。未给出最终 ``.config`` 和命令行时，本书不能写死具体模式。

最后， ``scheduler_running=1`` 表示调度器核心数据结构和入口可以使用。此时尚未建立完整SMP
调度域，没有调度器时钟滴答，也没有发生第一次上下文切换。

``start_kernel()`` 重新确认中断仍然关闭
-------------------------------------

``sched_init()`` 结束后， ``start_kernel()`` 立即执行：

.. code-block:: c

   if (WARN(!irqs_disabled(),
            "Interrupts were enabled *very* early, fixing it\n"))
       local_irq_disable();

如果任何早期初始化错误地打开了中断，内核先输出警告，再清除 ``IF``。如果中断原本关闭，
条件不成立。无论进入哪条路径，本章出口都可以确定 ``IF=0``。这项修复不会分派待处理设备中断；
``init_IRQ()`` 仍在后续章节。

本章结束状态
------------

* 当前执行者：CPU0上的 ``start_kernel()``，当前任务为 ``init_task/swapper/0``，PID为0；
* 精确位置： ``sched_init()`` 和中断状态检查已经结束， ``radix_tree_init()`` 尚未执行；
* CPU状态：x86-64内核态， ``IF=0``，只有CPU0在线且活动；
* ``def_root_domain.span``：包含所有可能CPU；
* ``def_root_domain.online``：包含CPU0，不包含尚未活动的应用处理器；
* ``def_root_domain.refcount``：基础引用1加每个已连接可能CPU的一份引用；
* CPU0运行队列： ``online=1``， ``curr`` 和 ``idle`` 都指向 ``init_task``；
* 其他可能CPU的运行队列：结构已经初始化并连接根域， ``online=0``，尚无本章创建的空闲任务；
* ``init_task``： ``TASK_RUNNING``、 ``on_rq=TASK_ON_RQ_QUEUED``、 ``on_cpu=1``，使用空闲调度类；
* ``init_mm``：当前任务持有惰性TLB引用，没有用户 ``mm_struct``；
* ``scheduler_running``：1；完整SMP调度拓扑与调度器时钟滴答尚未建立；
* 任务切换：本章没有调用 ``schedule()``；PID 1和 ``kthreadd`` / PID 2均不存在；
* 设备中断、应用处理器启动和初始内存盘：均未启用、执行或解包。

关键边界
--------

#. 运行队列初始化时写入 ``online=0``，但CPU0在连接根域时立即变为 ``online=1``。
#. ``def_root_domain.span`` 记录已连接CPU， ``online`` 只记录活动CPU，两份掩码不能混用。
#. 根域基础引用与每个运行队列持有的引用必须分别计数。
#. 可能CPU拥有运行队列不等于CPU已经在线，也不等于空闲任务已经创建。
#. ``__sched_fork(0, current)`` 只重置调度状态，不创建进程。
#. ``init_task`` 是PID 0的启动空闲任务，不是未来的PID 1 ``kernel_init``。
#. ``init_idle()`` 公布 ``curr`` 和 ``idle``，但不进入空闲循环，也不调用 ``schedule()``。
#. ``scheduler_running=1`` 不代表调度器时钟滴答、完整SMP拓扑或应用处理器已经可用。
#. 函数结束后的中断检查保证下一章入口处 ``IF=0``。

下一入口
--------

第058章从：

.. code-block:: c

   radix_tree_init();

开始，随后初始化后台工作CPU集合、早期工作队列、RCU、 ``kvfree_rcu`` 和追踪事件基础。

资料
----

* `Linux 7.2-rc1固定提交：sched_init及其后的中断检查 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1042-L1052>`_；
* `Linux 7.2-rc1固定提交：sched_init的调度类、根对象、运行队列和启动空闲任务顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c#L8915-L9108>`_；
* `Linux 7.2-rc1固定提交：rq_attach_root的引用、span和online处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/topology.c#L474-L515>`_；
* `Linux 7.2-rc1固定提交：set_rq_online更新运行队列与根域 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c#L8549-L8578>`_；
* `Linux 7.2-rc1固定提交：init_idle的锁与字段公布 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c#L8243-L8309>`_；
* `Linux 7.2-rc1固定提交：启动CPU空闲线程指针 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/smpboot.c#L21-L40>`_。
