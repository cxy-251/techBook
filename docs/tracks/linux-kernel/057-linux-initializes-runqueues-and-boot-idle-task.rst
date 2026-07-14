第五十七章：Linux 怎样建立 runqueue，并把 init_task 变成 CPU0 的 idle task？
============================================================================

第五十六章结束时，Maple Tree、text poking、ftrace 与早期 tracing 已经准备完成。

``start_kernel()`` 当前调用：

.. code-block:: c

   sched_init();

本章只追踪 ``sched_init()``，并停在它返回后、``radix_tree_init()`` 之前。

这是启动过程中的一个重要分界：内核从此拥有可工作的调度器数据结构，但当前控制流仍然没有切换到另一个任务。

调度器首先管理的不是“进程列表”
------------------------------

调度器真正直接操作的核心对象包括：

* ``task_struct``：可运行实体对应的任务；
* ``struct rq``：每个 CPU 一份的 runqueue；
* scheduling class：stop、deadline、real-time、fair、idle 等策略；
* class-specific queue：CFS、RT、deadline 等各自的数据结构；
* CPU mask、priority、load、clock 与 bandwidth 状态。

进程树、PID hash 或文件系统不是 ``sched_init()`` 的主要工作。

每个 possible CPU 都需要 runqueue
--------------------------------

内核定义：

.. code-block:: c

   DEFINE_PER_CPU_SHARED_ALIGNED(struct rq, runqueues);

第五十二章已经为每个 possible CPU 建立正式 per-CPU unit，所以 ``sched_init()`` 现在可以遍历 possible CPU，并初始化每个 ``struct rq``。

即使某个 AP 还没有启动，它的 runqueue 也必须提前存在。否则以后 AP 从 trampoline 进入 Linux 时，没有地方登记：

* 当前任务；
* idle task；
* runnable task 数量；
* CFS/RT/DL 队列；
* scheduler clock；
* load tracking；
* CPU hotplug 状态。

因此：

.. code-block:: text

   runqueue 已初始化

不等于：

.. code-block:: text

   对应 CPU 已 online

当前仍只有 CPU0 online。

runqueue lock 为什么从一开始就存在
---------------------------------

每个 runqueue 都有自己的锁，用来保护本 CPU 的调度状态。

后面这些动作都会依赖它：

* enqueue/dequeue task；
* wakeup；
* task migration；
* priority change；
* tick accounting；
* CPU hotplug；
* load balance。

``sched_init()`` 初始化 runqueue lock、clock state、load state、callback list、等待结构和各类计数器。

当前只有 CPU0 执行，几乎没有并发争用。提前建立锁仍然必要，因为同一套 runqueue 很快会被中断、其他 CPU 和 scheduler path 同时访问。

一个 runqueue 内部不是只有一条队列
--------------------------------

Linux 支持多个 scheduling class。

每个 CPU 的 ``struct rq`` 内部包含或关联：

``CFS runqueue``
   普通 fair task 使用。它根据 virtual runtime、权重和层级 task group 决定公平运行顺序。

``RT runqueue``
   ``SCHED_FIFO``、``SCHED_RR`` 等实时策略使用，按实时优先级组织任务。

``DL runqueue``
   ``SCHED_DEADLINE`` 使用，维护 runtime、deadline 与 period。

``idle class``
   没有其他 runnable task 时运行该 CPU 的 idle task。

可选的 ``sched_ext``、core scheduling、group scheduling 等配置还会增加额外状态。

``sched_init()`` 初始化这些 class-specific queue，使后续 task 可以按所属 class 入队。

当前没有普通可运行任务入队
------------------------

此时系统还没有：

* PID 1；
* ``kthreadd``；
* worker thread；
* 用户进程；
* AP idle task 的完整启动过程。

所以建立 CFS/RT/DL queue 并不表示其中已经装满任务。

当前最重要的任务仍是正在执行 ``start_kernel()`` 的 ``init_task``。

为什么需要 root task group
-------------------------

启用 group scheduling 时，任务不只按个体参与调度，还会被组织进 cgroup 对应的 task group。

启动最初所有任务都归属于：

.. code-block:: text

   root_task_group

``sched_init()`` 为 root task group 建立各 CPU 对应的 CFS/RT 状态，并把它连接到每个 runqueue。

以后 cgroup 子系统可以在其下创建新的 task group，设置 CPU weight、quota、uclamp 等策略。

当前尚未挂载 cgroupfs，也没有用户空间配置 cgroup。这里建立的是调度层根对象。

实时与 deadline bandwidth 为什么现在初始化
-----------------------------------------

RT 和 DL task 若无限制占用 CPU，普通任务可能永久得不到运行。

调度器因此维护 bandwidth 控制，例如：

* RT period/runtime；
* DL bandwidth；
* per-runqueue runtime accounting；
* throttling 状态。

``sched_init()`` 根据构建配置和已经解析的内核参数建立全局默认 bandwidth，并初始化各 CPU 对应状态。

此时没有 RT/DL 用户任务，但约束必须在第一个此类任务出现前存在。

``init_task`` 为什么会成为 CPU0 idle task
----------------------------------------

这是本章最容易误解的地方。

当前正在执行的 ``init_task`` 不是未来的 PID 1。它是编译期静态创建的最早任务，也是 CPU0 的 boot idle task，通常显示为：

.. code-block:: text

   swapper/0
   PID 0

``sched_init()`` 最终为当前 CPU 调用类似：

.. code-block:: c

   init_idle(current, smp_processor_id());

当前 ``current`` 正是 ``init_task``，CPU 编号是 0。

``init_idle()`` 将它绑定到 CPU0，并建立：

* ``rq->idle = init_task``；
* ``rq->curr = init_task``；
* 任务 CPU affinity 只包含 CPU0；
* ``PF_KTHREAD`` / per-CPU task 属性；
* ``idle_sched_class``；
* idle preempt count；
* idle virtual-time/ftrace 状态。

所以当前调用链可以同时满足两件事：

.. code-block:: text

   init_task 正在执行 start_kernel()
   init_task 是 CPU0 未来没有其他任务时运行的 idle task

它现在还没有进入 idle loop，因为 ``start_kernel()`` 尚未结束。

PID 0、PID 1 和 PID 2 的关系
---------------------------

当前只有静态 boot task：

``PID 0``
   ``init_task`` / ``swapper/0``，最终成为 CPU0 idle task。

后面的 ``rest_init()`` 才创建：

``PID 1``
   ``kernel_init``，最终尝试执行用户态 init。

``PID 2``
   ``kthreadd``，负责创建和管理许多内核线程。

因此 ``sched_init()`` 完成时，PID 1 和 PID 2 都还不存在。

其他 CPU 的 idle task 为什么不在这里完成
--------------------------------------

所有 possible CPU 的 runqueue 都已初始化，但 AP 尚未进入 Linux。

非 boot CPU 的 idle task 会在后续 SMP bring-up 过程中创建或绑定。AP 进入 ``start_secondary()`` 后，才会使用对应 CPU 的：

* per-CPU unit；
* stack；
* GDT/IDT；
* runqueue；
* idle task；
* local APIC；
* CPU hotplug state。

所以当前只有 CPU0 的 idle/current 关系已经成为现实。

调度器时钟现在是否已经是最终时钟
--------------------------------

``sched_init()`` 会初始化 runqueue clock 和 load-accounting 基础，但完整 timekeeping、clocksource、clockevent 和 timer interrupt 尚未完成。

调度器早期可以使用架构提供的 ``sched_clock()`` 或已有时钟基础记录相对时间。

后面仍会执行：

.. code-block:: text

   tick_init
   timers_init
   hrtimers_init
   timekeeping_init
   time_init
   sched_clock_init

所以这里建立的是 scheduler 可工作的早期时钟接口，不是整个时间系统已经结束初始化。

动态抢占模型在这里最后确定
--------------------------

若启用 ``CONFIG_PREEMPT_DYNAMIC``，内核可以根据构建默认值或 ``preempt=`` 命令行，在不同抢占模型间选择：

.. code-block:: text

   none
   voluntary
   full
   lazy（架构/配置支持时）

``preempt_dynamic_init()`` 通过 static call 或 static key 选择：

* ``cond_resched()`` 是否实际进入调度；
* ``preempt_schedule()`` 是否启用；
* IRQ 返回时是否检查抢占；
* lazy preemption 是否生效。

第五十一章建立的 static call/key 机制和第五十六章准备的 text poking，使这些热点路径可以切换而不在每次调用中支付普通函数指针开销。

``scheduler_running`` 表示什么
-----------------------------

``sched_init()`` 尾部把 scheduler 标记为已经初始化。

它表示调度器核心数据结构和关键入口已经可用，后面的内核代码可以安全建立 wait queue、设置 task state，并在允许的上下文调用调度路径。

它不表示：

* 当前立刻发生了一次 ``schedule()``；
* timer interrupt 已开始驱动抢占；
* 中断已经开启；
* AP 已上线；
* load balancing topology 已完整建立；
* worker/kernel thread 已开始运行。

完整 SMP scheduling domain 要等非 boot CPU bring-up 附近的 ``sched_init_smp()``。

为什么 ``start_kernel()`` 立即检查 IRQ 状态
-----------------------------------------

``sched_init()`` 返回后，源码执行：

.. code-block:: c

   if (WARN(!irqs_disabled(),
            "Interrupts were enabled *very* early, fixing it\n"))
       local_irq_disable();

这说明调度器初始化允许执行复杂代码和配置回调，但整个启动协议仍要求 external IRQ 保持关闭。

若某个错误路径过早打开 IRQ，内核发出警告并重新关闭，避免尚未初始化的 IRQ/timer 子系统开始异步执行。

本章结束时调度器能做什么
----------------------

此时已经具备：

* 每个 possible CPU 的 runqueue；
* scheduling class queue；
* root task group；
* RT/DL bandwidth 基础；
* CPU0 idle/current 关系；
* scheduler core locks 与 accounting 状态；
* 选定的抢占模型。

尚未具备：

* IRQ 驱动的 scheduler tick；
* AP runqueue 真正投入运行；
* 完整 SMP load-balancing domain；
* 普通内核线程；
* 第一次显式任务切换。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``sched_init()`` 和 IRQ-disabled sanity check 已完成，``radix_tree_init()`` 尚未调用；
* CPU：只有 CPU0 online；
* current：``init_task`` / ``swapper/0`` / PID 0；
* CPU0 runqueue：已建立，``rq->curr`` 与 ``rq->idle`` 指向当前 boot idle task；
* possible CPU runqueue：均已初始化；
* scheduling class：基础状态已建立；
* scheduler：核心数据结构可用；
* interrupts：仍关闭；
* scheduler tick：尚未启动；
* AP：尚未收到 INIT/SIPI；
* PID 1 / PID 2：尚未创建；
* initramfs：尚未解包。

下一条控制流是：

.. code-block:: c

   radix_tree_init();

随后 Linux 将建立 housekeeping、early workqueue、RCU 和 trace event 基础，并走到正式 IRQ 初始化入口。

资料
----

* `Linux 6.12.95 init/main.c：sched_init 调用及 IRQ 状态检查 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 kernel/sched/core.c：sched_init、runqueue 与 init_idle <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
* `Linux 6.12.95 kernel/sched/sched.h：struct rq 与 scheduler 内部结构 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/sched.h>`_
* `Linux 6.12.95 include/linux/init_task.h：静态 init_task 定义 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/init_task.h>`_
* `Linux scheduler 文档入口 <https://github.com/gregkh/linux/tree/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/scheduler>`_