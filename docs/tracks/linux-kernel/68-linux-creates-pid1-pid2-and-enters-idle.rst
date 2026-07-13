第六十八章：Linux 怎样创建 PID 1、PID 2，并让 PID 0 进入 idle loop？
====================================================================

第六十七章结束时，``start_kernel()`` 的同步初始化已经完成。CPU0 仍由 ``init_task`` / ``swapper/0`` / PID 0 占用，PID allocator、task cache、scheduler runqueue、timer、RCU、VFS 和 cgroup 等基础都已存在，但系统中还没有普通新任务，也没有发生第一次正常调度。

下一条控制流是：

.. code-block:: c

   rest_init();

``rest_init()`` 是启动链中第一次真正改变执行环境的入口。它创建 PID 1 和 PID 2，允许 scheduler 开始正常工作，并让 PID 0 从“一直执行启动代码的任务”转变为 CPU0 的永久 idle task。

``rest_init()`` 为什么不是普通 ``__init`` 函数
--------------------------------------------

源码把它声明为：

.. code-block:: c

   static noinline void __ref __noreturn rest_init(void)

这里有三个重要属性：

* ``noinline``：防止编译器把代码内联回 ``start_kernel()``；
* ``__ref``：允许它引用启动期代码，同时避免 section mismatch；
* ``__noreturn``：PID 0 进入 idle loop 后不会返回 ``start_kernel()``。

PID 1 会继续执行并最终释放 ``__init`` 内存。如果 PID 0 的 idle 路径仍依赖可能被释放的 ``start_kernel()`` 栈上返回链，就会产生竞态。因此 ``rest_init()`` 必须成为独立、不会返回的控制入口。

RCU 从启动特例切入 scheduler 阶段
--------------------------------

``rest_init()`` 首先调用：

.. code-block:: c

   rcu_scheduler_starting();

在此之前，RCU 已有层级、per-CPU 数据和 callback 基础，但系统始终只有 PID 0 沿单条启动路径运行。``rcu_scheduler_starting()`` 告诉 RCU：正常 scheduler、context switch 和 idle quiescent state 即将出现。

它不是创建 RCU kthread，也不是立刻完成一个 grace period。它完成的是状态切换：后续 RCU 可以把任务切换、CPU idle 和用户态边界纳入正常 quiescent-state 判断。

``user_mode_thread(kernel_init)`` 创建 PID 1
-----------------------------------------

源码必须先创建 init task：

.. code-block:: c

   pid = user_mode_thread(kernel_init, NULL, CLONE_FS);

``user_mode_thread()`` 最终构造 ``kernel_clone_args``：

.. code-block:: c

   flags = CLONE_FS | CLONE_VM | CLONE_UNTRACED
   fn = kernel_init
   fn_arg = NULL

随后进入：

.. code-block:: text

   user_mode_thread()
   → kernel_clone()
   → copy_process()
   → alloc_pid()
   → wake_up_new_task()

初始 PID namespace 尚未分配过普通 PID，``alloc_pid()`` 从 1 开始，因此这个任务取得 PID 1。

为什么函数名带 ``user_mode``，任务却先执行内核函数
-------------------------------------------------

PID 1 此刻还没有用户态指令、用户栈和 ELF 映像。新任务第一次获得 CPU 时，从内核入口 ``kernel_init()`` 开始执行。

``user_mode_thread`` 表示这个任务不是永久 ``PF_KTHREAD`` 内核线程；它被设计为稍后通过 ``kernel_execve()`` 装入 ``/init``、``/sbin/init`` 等用户程序。真正切入用户态发生在成功 exec 之后，不发生在 ``user_mode_thread()`` 返回时。

PID 1 为什么暂时只能运行在 CPU0
-----------------------------

``user_mode_thread()`` 会把新任务放入 runqueue。此时 AP 尚未 online，SMP scheduler topology 也没有完成。``rest_init()`` 随即找到 PID 1 的 ``task_struct``：

.. code-block:: c

   tsk->flags |= PF_NO_SETAFFINITY;
   set_cpus_allowed_ptr(tsk, cpumask_of(smp_processor_id()));

因此 PID 1 暂时只能运行在当前 boot CPU。

这个限制不是永久 CPU affinity 策略。后面的 ``sched_init_smp()`` 完成 non-isolated CPU mask 和 scheduler domains 后，会重新设置 init task 的可运行 CPU 集合。

``numa_default_policy()`` 清理 PID 0 的启动期策略
----------------------------------------------

创建 PID 2 之前，PID 0 调用 ``numa_default_policy()``。前面的 NUMA 初始化可能让启动任务暂时携带显式 memory policy；这里恢复默认策略，避免后续内核线程无意继承只为 early boot 服务的 policy 对象。

这不会把内存重新搬迁，也不会改变已分配页所在 node。它改变的是以后分配和继承时使用的 policy 基线。

``kernel_thread(kthreadd)`` 创建 PID 2
-----------------------------------

接下来执行：

.. code-block:: c

   pid = kernel_thread(kthreadd, NULL, NULL,
                       CLONE_FS | CLONE_FILES);

``kernel_thread()`` 同样进入 ``kernel_clone()``，并额外设置：

.. code-block:: text

   CLONE_VM
   CLONE_UNTRACED
   kthread = 1

PID 1 已占用编号 1，因此新的 ``struct pid`` 取得编号 2。随后 ``rest_init()`` 通过 ``find_task_by_pid_ns()`` 保存：

.. code-block:: c

   kthreadd_task = ...;

PID 2 是正式的 ``kthreadd``。它进入循环，等待 ``kthread_create_list`` 中的请求，并代表内核创建后续 worker、watchdog 和其他 kthread。

PID 1 为什么必须先创建，PID 2 又必须先准备好
----------------------------------------

顺序必须满足两个约束：

#. init task 必须成为初始 PID namespace 的 PID 1；
#. PID 1 后续 initcall 可能请求创建 kthread，届时 ``kthreadd`` 必须已经存在。

所以 Linux 先创建 PID 1，再创建 PID 2。同时 PID 1 的 ``kernel_init()`` 一开始执行：

.. code-block:: c

   wait_for_completion(&kthreadd_done);

即使 scheduler 在 PID 2 完全登记前先运行了 PID 1，PID 1 也只能睡在 completion 上，不会提前进入依赖 kthreadd 的初始化路径。

``SYSTEM_SCHEDULING`` 表示什么
----------------------------

PID 1、PID 2 都已创建后，PID 0 设置：

.. code-block:: c

   system_state = SYSTEM_SCHEDULING;

从此 ``might_sleep()``、``smp_processor_id()`` 等调试检查可以按正常调度环境工作。

它不表示所有 CPU 已启动，也不表示 scheduler topology 已完成。当前仍只有 CPU0 online。这个状态只说明系统已经越过“只有 boot task、不能按正常规则睡眠和调度”的最早阶段。

completion 放行 PID 1
---------------------

随后执行：

.. code-block:: c

   complete(&kthreadd_done);

如果 PID 1 已在 ``wait_for_completion()`` 睡眠，这里会把它唤醒；如果 PID 1 尚未运行，completion 计数会保留，使它以后调用 wait 时立即通过。

completion 只保证 kthreadd 的 task 已创建并可被引用。PID 2 是否已经运行到自己的无限循环，取决于 scheduler 的实际选择。

PID 0 第一次主动进入 scheduler
----------------------------

``rest_init()`` 接下来执行：

.. code-block:: c

   schedule_preempt_disabled();

这是 boot idle task 第一次主动调用正常 scheduler。runqueue 上已有 PID 1 和 PID 2，scheduler 可以选择其中一个运行。

这里不能声称固定先运行 PID 1 或 PID 2。优先级、wake-up 时序和配置会影响第一次选择；源码只保证二者已创建，并通过 ``kthreadd_done`` 保证 PID 1 不会越过依赖边界。

PID 0 进入永久 idle loop
-----------------------

当 PID 0 再次获得 CPU 后，``rest_init()`` 继续：

.. code-block:: c

   cpu_startup_entry(CPUHP_ONLINE);

``cpu_startup_entry()``：

* 给当前任务设置 ``PF_IDLE``；
* 执行 architecture idle prepare；
* 把 CPU0 的 hotplug 状态推进到 online idle；
* 永久循环调用 ``do_idle()``。

``do_idle()`` 在没有 runnable task 时进入 poll、``hlt``、``mwait`` 或 cpuidle state；出现 timer interrupt、IPI 或新的 runnable task 时退出 idle 并调用 ``schedule_idle()``。

PID 0 没有退出
------------

PID 0 进入 idle 不等于它结束。每个 online CPU 都需要一个 idle task。当没有其他任务可运行时，scheduler 把 CPU 切回对应 idle task；有任务需要运行时，idle task 再让出 CPU。

因此 PID 0 从此仍永久存在，只是不再负责继续执行 Linux 初始化主线。

本章结束后的执行环境
------------------

本章结束时可以确认：

.. code-block:: text

   PID 0  swapper/0
          → 已完成第一次 schedule
          → 进入 cpu_startup_entry()/do_idle()

   PID 1  kernel_init
          → 已创建
          → 等待或已经通过 kthreadd_done
          → 将继续 kernel_init_freeable()

   PID 2  kthreadd
          → 已创建
          → 处理内核线程创建请求

当前机器状态：

* CPU0 是唯一 online CPU；
* PID 0 已成为 CPU0 的正常 idle task；
* PID 1 与 PID 2 已真实存在；
* scheduler 已开始正常选择 runnable task；
* ``system_state = SYSTEM_SCHEDULING``；
* RCU 已进入 scheduler-aware 启动阶段；
* PID 1 仍在内核态，尚未 exec 用户程序；
* AP 尚未收到本内核发出的启动序列；
* initramfs 尚未解包；
* root filesystem 尚未挂载。

后续主线不再跟随 PID 0。下一执行者是 PID 1：

.. code-block:: c

   kernel_init()
       wait_for_completion(&kthreadd_done);
       kernel_init_freeable();

资料
----

* `Linux 7.2-rc1 init/main.c：rest_init、kernel_init 与首次调度 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 kernel/fork.c：kernel_clone、kernel_thread 与 user_mode_thread <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c>`_
* `Linux 7.2-rc1 kernel/kthread.c：kthreadd 主循环 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/kthread.c>`_
* `Linux 7.2-rc1 kernel/sched/idle.c：cpu_startup_entry 与 do_idle <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/idle.c>`_
* `Linux 7.2-rc1 kernel/rcu/tree.c：rcu_scheduler_starting <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/rcu/tree.c>`_