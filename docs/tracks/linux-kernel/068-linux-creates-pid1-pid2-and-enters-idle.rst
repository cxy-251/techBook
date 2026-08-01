第六十八章：Linux 怎样创建 PID 1、PID 2，并让 PID 0 进入空闲循环？
========================================================================

第六十七章结束时，CPU0仍由 ``init_task``、 ``swapper/0``、PID 0执行
``start_kernel()``。控制组、任务统计和延迟记账已经按配置建立早期对象，ACPI只完成了当前
阶段允许的模式切换，系统中仍没有动态任务。下一条语句进入：

.. code-block:: c

   rest_init();

``rest_init()`` 首次把一条启动执行流分成三个任务：PID 0退出初始化主线并成为CPU0空闲任务，
PID 1接续可释放的内核初始化，PID 2成为内核线程创建者。三个任务何时首次取得CPU由调度决定，
所以本章按同步关系说明交接，不虚构固定的运行次序。

``rest_init()`` 必须成为独立且不返回的入口
-------------------------------------------

函数声明同时带有 ``noinline``、 ``__ref`` 和 ``__noreturn``：

.. code-block:: c

   static noinline void __ref __noreturn rest_init(void)

PID 1以后会释放初始化内存。若编译器把这个函数内联回 ``start_kernel()``，PID 1释放相关代码
时，PID 0可能还没有沿独立路径进入空闲循环。源码因此禁止内联，并明确PID 0不会从
``rest_init()`` 返回。 ``__ref`` 允许这段非初始化节代码引用启动期对象，同时接受这里刻意
安排的生命周期关系。

RCU先离开单任务启动特例
-----------------------

PID 0首先调用 ``rcu_scheduler_starting()``。函数检查当前是否仍只有一个在线CPU，以及是否
尚未发生上下文切换；异常状态只触发警告。它随后暂时保存并关闭本地中断，遍历RCU树，把每个
``rcu_node.gp_seq_needed`` 与 ``gp_seq`` 修正到全局序号，再恢复原来的中断状态。

最后，函数把 ``rcu_scheduler_active`` 从早期启动状态推进到
``RCU_SCHEDULER_INIT``。从这里开始，同步宽限期操作不再是启动期空操作，而采用由请求任务
推动的加速路径。这仍不是完整运行期RCU；稍后的 ``rcu_set_runtime_mode()`` 才完成下一次
阶段转换，也还没有因为本调用自动创建RCU线程。

第一个动态任务取得PID 1
-----------------------

PID 0接着执行：

.. code-block:: c

   pid = user_mode_thread(kernel_init, NULL, CLONE_FS);

``user_mode_thread()`` 把入口保存为 ``kernel_init``，并在调用者给出的 ``CLONE_FS`` 之外
加入 ``CLONE_VM | CLONE_UNTRACED``。它没有设置 ``kernel_thread()`` 使用的内核线程标志：
这个任务虽从内核函数开始运行，身份却是将来装入用户空间初始化程序的初始任务。

``kernel_clone()`` 调用 ``copy_process()`` 分配并连接任务对象。第六十五章已经确认动态PID
分配游标从1开始，当前又没有其他动态任务，所以持续启动路径中的第一个任务获得PID 1。函数在
返回数字PID之前调用 ``wake_up_new_task()``，PID 1从这一刻起已经可以被调度。

这里有一个必须保留的失败边界： ``user_mode_thread()`` 可以返回负错误值，但
``rest_init()`` 没有检查它。后面的 ``find_task_by_pid_ns()`` 结果被直接解引用，因此源码的
继续路径依赖PID 1创建成功这一启动不变量；不存在可以补写成正文的降级或重试分支。

PID 1暂时只能在CPU0运行
-----------------------

PID 0在RCU读侧临界区按刚得到的PID找到 ``task_struct``，设置
``PF_NO_SETAFFINITY``，再调用：

.. code-block:: c

   set_cpus_allowed_ptr(tsk, cpumask_of(smp_processor_id()));

此时 ``smp_processor_id()`` 是0，因此PID 1的允许CPU集合暂时只有CPU0。应用处理器尚未启动，
SMP调度域也没有建立；这项限制防止初始化任务在相关迁移机制完整以前改变CPU。第六十九章的
``sched_init_smp()`` 会根据非隔离维护CPU重新设置范围并清除该标志。

设置亲和性不代表PID 1现在立刻运行。 ``wake_up_new_task()`` 只使它具备被选择的条件；PID 0
尚未执行本函数末尾的显式调度，而且构建的抢占方式仍可能影响PID 1是否更早获得CPU。

PID 0恢复自己的默认NUMA内存策略
-------------------------------

创建PID 2之前，当前执行者仍是PID 0。 ``numa_default_policy()`` 对 ``current`` 调用
``do_set_mempolicy(MPOL_DEFAULT, 0, NULL)``，撤销更早启动阶段为了初始化内存而使用的临时交错
策略。这个操作改变的是PID 0当前内存策略，不是为PID 1迁移既有页面；禁用NUMA时，对应入口
不产生实质变化。

第二个动态任务取得PID 2并成为 ``kthreadd``
------------------------------------------

随后，PID 0执行：

.. code-block:: c

   pid = kernel_thread(kthreadd, NULL, NULL, CLONE_FS | CLONE_FILES);

``kernel_thread()`` 在给出的文件系统上下文和文件表共享标志之外加入
``CLONE_VM | CLONE_UNTRACED``，把入口设为 ``kthreadd``，并明确设置内核线程标志。因为PID 1
已经占用第一个动态编号，持续路径中的第二次分配得到PID 2。

``kernel_clone()`` 同样在返回前唤醒PID 2。PID 0随后在RCU读侧临界区找到它，并把指针发布到
全局 ``kthreadd_task``。源码对第二次创建也没有检查负返回值；后续路径同样把成功创建PID 2
作为启动不变量。

PID 2何时真正进入 ``kthreadd()`` 并不由这几行决定。它取得CPU后才会把任务名改成
``kthreadd``、忽略信号、设置所有有内存节点、建立控制组内核线程关系，然后在
``kthread_create_list`` 为空时睡眠。当前可以确定的是任务与全局指针已经发布，不能断言上述
循环一定已经执行。

完成量封住PID 1与PID 2之间的依赖
--------------------------------

两个任务都创建后，PID 0把：

.. code-block:: c

   system_state = SYSTEM_SCHEDULING;
   complete(&kthreadd_done);

依次写入。新的系统状态允许启用 ``might_sleep()`` 和 ``smp_processor_id()`` 等运行期检查。
``complete()`` 则发布“PID 2已经创建且 ``kthreadd_task`` 已可见”这一事实。

PID 1的入口 ``kernel_init()`` 第一件事就是
``wait_for_completion(&kthreadd_done)``。若自愿抢占配置使PID 1提前运行，它会停在完成量上；
若它在完成量发布以后才首次运行，等待会直接通过。两条时序都保证PID 1进入
``kernel_init_freeable()`` 前能够请求创建内核线程。

完成量只证明PID 2对象和全局指针已经建立，不证明PID 2已经运行到主循环。内核线程创建请求
可以先进入队列，再由PID 2取得CPU后处理。

第一次显式调度没有规定PID 1和PID 2的先后
----------------------------------------

PID 0接着调用 ``schedule_preempt_disabled()``。该辅助函数在进入时要求抢占计数为1；它先允许
抢占而不立即检查重新调度，调用 ``schedule()``，调度返回后重新禁止抢占。源码注释要求启动
空闲任务至少执行一次调度，以便新任务真正开始推进。

此时运行队列中可以同时存在PID 1和PID 2。优先级、唤醒位置和构建选择共同影响调度结果，
``rest_init()`` 没有指定谁必须先运行。可以确定的只有同步关系：

* PID 1在完成量发布前不能越过 ``kernel_init()`` 的等待；
* PID 2可以在PID 1之前或之后首次运行；
* PID 0从第一次调度恢复后，不再继续执行普通启动初始化。

PID 0永久进入CPU0空闲循环
-------------------------

第一次显式调度返回PID 0时，抢占再次处于禁止状态。它立即调用：

.. code-block:: c

   cpu_startup_entry(CPUHP_ONLINE);

该函数为当前任务设置 ``PF_IDLE``，执行体系结构空闲准备，把CPU0推进到
``CPUHP_ONLINE`` 对应的空闲热插拔状态，然后永久循环 ``do_idle()``。空闲循环根据
``need_resched()``、无滴答状态和CPU空闲驱动决定轮询或进入硬件空闲；需要切换任务时，它在
RCU读侧临界区之外执行 ``schedule_idle()``。

因此，PID 0不是“完成 ``rest_init()`` 后返回调用者”，而是把自己的永久角色从启动执行者
切换成CPU0空闲任务。初始化主线从此属于PID 1。

本章结束状态
------------

::

   初始化主线执行者    = PID 1；已越过kthreadd_done并到达kernel_init_freeable()
   下一入口            = kernel_init_freeable()
   CPU模式             = x86-64长模式，CPL0
   system_state        = SYSTEM_SCHEDULING
   CPU在线且活动       = 仅CPU0
   PID 0               = swapper/0；永久位于CPU0空闲路径
   PID 1               = kernel_init；暂时限制在CPU0，尚未装入用户空间程序
   PID 2               = kthreadd对象已经创建并发布；首次运行时刻不固定
   kthreadd_done       = 已完成
   kthreadd_task       = 指向PID 2
   RCU                 = RCU_SCHEDULER_INIT；尚未进入完整运行期模式
   首次显式调度        = 已执行
   应用处理器          = 尚未启动
   SMP调度域           = 尚未建立
   普通工作线程        = 尚未由第069章的workqueue_init()成批建立
   当前根              = 仍为可变rootfs；最终ext4磁盘根尚未挂载
   初始内存盘          = 尚未解包

关键边界
--------

* ``rcu_scheduler_starting()`` 进入 ``RCU_SCHEDULER_INIT``，不是完整运行期RCU；
* ``user_mode_thread()`` 与 ``kernel_thread()`` 都通过任务复制路径分配并唤醒任务，持续路径
  依次得到PID 1和PID 2；
* 两次创建结果均未由 ``rest_init()`` 检查，继续执行依赖创建成功，源码没有恢复路径；
* PID 1在SMP调度域建立前带有 ``PF_NO_SETAFFINITY``，允许CPU集合只有CPU0；
* ``kthreadd_done`` 保证PID 1继续前能看到PID 2已经发布，不保证PID 2已经进入主循环；
* 第一次显式调度不规定PID 1和PID 2谁先运行；
* ``rest_init()`` 不返回，PID 0永久成为CPU0空闲任务，PID 1接续初始化主线。

下一入口
--------

下一章从PID 1执行 ``kernel_init_freeable()`` 开始。它将开放启动期受限的内存分配标志，建立
首批工作线程，准备并尝试启动应用处理器，再依据最终在线CPU集合建立SMP调度域和工作队列
拓扑。

资料
----

* `rest_init()的完整交接
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L660-L718>`_
* `RCU进入调度器初始化阶段
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/rcu/tree.c#L4648-L4673>`_
* `kernel_clone()分配、唤醒并发布数字PID
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c#L2694-L2791>`_
* `kernel_thread()与user_mode_thread()的参数差异
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c#L2794-L2824>`_
* `numa_default_policy()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mempolicy.c#L3388-L3392>`_
* `kernel_init()的完成量等待
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1539-L1549>`_
* `kthreadd()建立上下文并处理创建队列
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/kthread.c#L787-L822>`_
* `schedule_preempt_disabled()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c#L7375-L7385>`_
* `CPU空闲循环与cpu_startup_entry()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/idle.c#L273-L388>`_
* `cpu_startup_entry()设置永久空闲角色
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/idle.c#L448-L455>`_
