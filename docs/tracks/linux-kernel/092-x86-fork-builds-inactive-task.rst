第九十二章：x86-64 的 fork() 怎样创建一个尚不可运行的 task_struct？
=======================================================================

第九十一章已经结束独立的 O_SYNC write 场景。本章开始新的运行期实验，不假设它紧接着前一条系统调用执行。

固定场景如下：

.. code-block:: text

   userspace call      = native fork() syscall
   process             = single-threaded x86-64 userspace process
   scheduling policy   = SCHED_NORMAL
   parent mm           = private user mm
   fork flags          = 0
   child exit signal   = SIGCHLD
   ptrace/seccomp      = disabled for this scenario
   signals             = no pending or fatal signal
   namespaces/cgroups  = inherited; no new namespace or cgroup placement
   limits              = RLIMIT_NPROC, max_threads and PID space available
   failures            = no allocation, LSM, audit or scheduler failure

父进程包含一个普通 writable private anonymous VMA，其中某个 4 KiB anonymous folio 当前已经 present、writable、未被长期 pin。后续章节用它说明 fork 的 copy-on-write 建立过程。

本章追踪 native syscall 入口、``kernel_clone()`` 与 ``copy_process()`` 的前半段，停在新 task 已拥有独立 kernel stack、credentials 和 scheduler 基础状态，但尚未复制 files、fs、signals 和 mm 的位置。

syscall 57 怎样进入 ``__x64_sys_fork``
--------------------------------------

x86-64 syscall table规定：

.. code-block:: text

   RAX = 57 = __NR_fork

用户态执行 ``SYSCALL`` 后，CPU 进入 ``entry_SYSCALL_64``，切换到当前父进程的 kernel stack并构造 ``struct pt_regs``。``do_syscall_64()`` 最终通过 ``x64_sys_call()`` 选择：

.. code-block:: c

   __x64_sys_fork(regs)

本场景直接规定 native fork syscall，不从 glibc 是否用 ``clone()`` 或 ``clone3()`` 反推内核入口。

``SYSCALL_DEFINE0(fork)`` 固定了哪些语义
---------------------------------------

``kernel/fork.c`` 中的 fork wrapper构造：

.. code-block:: c

   struct kernel_clone_args args = {
       .exit_signal = SIGCHLD,
   };

未显式设置的字段为零。因此当前：

.. code-block:: text

   args.flags        = 0
   args.exit_signal  = SIGCHLD
   args.stack        = 0
   args.tls          = 0
   args.parent_tid   = NULL
   args.child_tid    = NULL
   args.pidfd        = NULL

这排除了普通 fork 中不存在的共享语义：

* 没有 ``CLONE_VM``；
* 没有 ``CLONE_FILES``；
* 没有 ``CLONE_FS``；
* 没有 ``CLONE_SIGHAND``；
* 没有 ``CLONE_THREAD``；
* 没有 ``CLONE_VFORK``；
* 没有 ``CLONE_NEW*``；
* 没有 parent/child TID 或 pidfd 返回地址。

所以 fork 创建的是新的进程与 thread-group leader，不是同一进程中的新线程。

``kernel_clone`` 为什么先计算 ptrace event
-----------------------------------------

``kernel_clone()`` 验证 exit signal合法，然后根据 flags判断应报告 ``PTRACE_EVENT_FORK``、``PTRACE_EVENT_CLONE`` 或 ``PTRACE_EVENT_VFORK``。

固定场景未被 ptrace，所以：

.. code-block:: text

   trace = 0

随后调用：

.. code-block:: c

   p = copy_process(NULL, 0, NUMA_NO_NODE, &args);

这里还没有 child PID 返回值。``copy_process()`` 的职责是构造一个完整但尚未启动的新 task；真正的 scheduler enqueue由 ``kernel_clone()`` 在它成功返回后完成。

``copy_process`` 先拒绝哪些非法组合
-----------------------------------

函数首先检查 clone flags之间的依赖，例如：

* ``CLONE_THREAD`` 必须配合 ``CLONE_SIGHAND``；
* ``CLONE_SIGHAND`` 必须配合 ``CLONE_VM``；
* 某些 new namespace与 shared state不能组合；
* pidfd、autoreap和 parent flags必须自洽。

当前 ``clone_flags=0``，这些组合检查全部自然通过。它们仍然重要，因为 ``fork()``、``clone()``、``clone3()`` 最终会共用同一个 ``copy_process()``。

为什么 fork 要暂存 multiprocess signals
---------------------------------------

新进程尚未加入 process tree 时，发送给整个进程组或多个进程的 signal可能与 fork并发。``copy_process()`` 在父进程 ``sighand->siglock`` 下，把一个临时节点加入：

.. code-block:: text

   current->signal->multiprocess

并重新计算 pending signals。这样 fork临界区内到达的 multiprocess signal可以在父子关系建立后按正确语义处理，而不会因为 child尚未可见而丢失。

固定父进程没有 pending signal，因此：

.. code-block:: c

   task_sigpending(current) == false

fork继续执行。若此处发现需要处理的 signal，``copy_process()`` 会返回 ``-ERESTARTNOINTR``，不会产生半成品 child。

``dup_task_struct`` 实际复制了什么
---------------------------------

``copy_process()`` 首个核心分配是：

.. code-block:: c

   p = dup_task_struct(current, node);

它执行：

#. 分配新的 ``struct task_struct``；
#. 通过 ``arch_dup_task_struct()`` 复制父 task 的基础内容；
#. 分配独立 kernel stack；
#. 建立新的 stack reference/accounting；
#. 初始化 stack magic、stack canary和 architecture thread state；
#. 清除不应继承的 scheduler、work、BPF、fault-injection等临时状态。

复制整个 ``task_struct`` 只是构造起点。里面暂时复制过来的指针不能直接当作 child最终资源关系；后续 ``copy_files()``、``copy_mm()`` 等函数会按 clone flags分别替换、引用或复制它们。

此刻 parent与 child已经有两套：

.. code-block:: text

   task_struct
   kernel stack
   thread_struct storage

child仍未获得 PID，也没有进入全局 task list。

credentials 为什么不是简单共享父指针
-------------------------------------

普通 fork没有 ``CLONE_THREAD``。``copy_creds()`` 调用 ``prepare_creds()`` 创建新的 ``struct cred``，复制父进程当前 subjective credentials，再令：

.. code-block:: c

   p->cred = p->real_cred = get_cred(new);

UID、GID、capabilities和 user namespace语义被继承，但 parent与 child持有不同的 cred object。其内部引用的 user、user namespace等对象会通过引用计数继续共享。

普通 fork还不会继承独立 process keyring；thread keyring处理也与 ``CLONE_THREAD`` 路径不同。

随后内核增加该用户的 process count，并执行 ``RLIMIT_NPROC``、全局 ``max_threads`` 等限制检查。固定场景资源充足，所以继续。

复制出来的 task 为什么必须重新初始化
-----------------------------------

``copy_process()`` 清除父 task不应传递给 child的运行期状态，例如：

* ``PF_SUPERPRIV``、worker、idle与 affinity内部标记；
* pending signal queue；
* CPU time、context-switch和 I/O accounting；
* workqueue、task work、plug和 tracing transient state；
* child list、sibling list和 RCU bookkeeping。

同时设置：

.. code-block:: text

   PF_FORKNOEXEC = 1

它表示这个新 task由 fork产生，尚未完成 exec。fork与 exec是两套机制：fork复制当前 process image，exec稍后才可能替换 mm与用户寄存器映像。

``sched_fork`` 怎样阻止 child 提前运行
--------------------------------------

``sched_fork(clone_flags, p)`` 初始化 child的 scheduler entity：

* ``on_rq = 0``；
* runtime、vruntime、migration统计归零；
* priority从父进程正常优先级派生；
* 固定 ``SCHED_NORMAL`` child选择 ``fair_sched_class``；
* ``on_cpu = 0``；
* preemption count和调度器内部节点初始化。

最关键的状态是：

.. code-block:: c

   p->__state = TASK_NEW;

``TASK_NEW`` 保证普通 wakeup、signal或外部事件不能把这个半构造 task插入 runqueue。child在所有资源、PID、parent关系与 architecture register frame准备完成之前绝不能执行。

当前精确边界
------------

``copy_process()`` 接下来将依次进入资源复制阶段：

.. code-block:: c

   copy_files(clone_flags, p, args->no_files);

当前状态：

* 当前执行者：父进程；
* CPU mode：x86-64 CPL 0，syscall process context；
* parent：仍是当前 running task；
* child ``task_struct``：已分配；
* child kernel stack：已分配；
* child credentials：独立 cred object，身份语义继承；
* child scheduler class：fair；
* child state：``TASK_NEW``；
* child ``on_rq``：0；
* child PID：尚未分配；
* child files/fs/sighand/signal/mm：尚未完成正式复制；
* child page tables：尚未建立；
* child user register frame：尚未由 ``copy_thread()`` 完成；
* child global visibility：不可见；
* child可运行性：不可运行；
* parent fork返回值：尚未确定。

关键边界
--------

#. native x86-64 fork syscall number是 57；本场景不经过 clone wrapper。
#. ``flags=0`` 表示普通 fork不共享 mm、files、fs、sighand或 signal_struct。
#. ``dup_task_struct()`` 复制的是 task基础与 kernel stack，不是完整进程语义的终点。
#. credentials的身份值被继承，但普通 fork创建新的 cred object。
#. ``TASK_NEW`` 表示构造中且不可被普通 wakeup运行。
#. 此时既没有 PID publication，也没有 child return value。

资料
----

* `Linux 7.2-rc1 x86-64 syscall table <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/syscalls/syscall_64.tbl>`_
* `Linux 7.2-rc1 kernel/fork.c：fork、kernel_clone、copy_process 与 dup_task_struct <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c>`_
* `Linux 7.2-rc1 kernel/cred.c：copy_creds <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cred.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：sched_fork 与 TASK_NEW <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
