第一百零二章：exit_notify() 怎样发送 SIGCHLD、唤醒 parent 并留下 zombie？
================================================================================

第一百零一章结束时，child已经释放mm、files、fs等运行资源，但task/PID和exit status仍然存在。现在进入：

.. code-block:: c

   exit_notify(current, true);

本场景parent已经阻塞在：

.. code-block:: c

   wait4(child_pid, &status, 0, &rusage);

它的 ``wait_opts`` 已挂到 ``parent->signal->wait_chldexit``，parent状态是 ``TASK_INTERRUPTIBLE``。

``exit_notify`` 为什么持有 tasklist_lock
--------------------------------------

parent/child关系、children list、ptrace关系和 ``exit_state`` 都属于process-tree全局结构。``exit_notify()`` 先取得：

.. code-block:: c

   write_lock_irq(&tasklist_lock);

固定child没有自己的children、ptrace关系或subreaper分支，所以 ``forget_original_parent()`` 不需要重新挂接其他task。

随后执行最关键的状态写入：

.. code-block:: c

   current->exit_state = EXIT_ZOMBIE;

从这一刻起，wait扫描可以把child识别为可回收的zombie。

``EXIT_ZOMBIE`` 与 ``TASK_DEAD`` 不是同一个字段
---------------------------------------------

Linux同时保存两类状态：

.. code-block:: text

   task->__state / task state
   → scheduler是否允许task继续运行

   task->exit_state
   → parent、ptrace和wait路径看到的死亡生命周期

``EXIT_ZOMBIE`` 表示child已退出但尚未被parent回收。稍后 ``do_task_dead()`` 会让scheduler永远切走当前task；这不等于立即把 ``exit_state`` 改成 ``EXIT_DEAD``。

为什么本场景不会 autoreap
-------------------------

``exit_notify()`` 对普通thread-group leader调用：

.. code-block:: c

   autoreap = do_notify_parent(current, SIGCHLD);

``do_notify_parent()`` 只有在parent显式把SIGCHLD设为 ``SIG_IGN``、设置 ``SA_NOCLDWAIT``，或其他特殊autoreap条件成立时返回true。

本场景固定：

.. code-block:: text

   SIGCHLD disposition = default
   SA_NOCLDWAIT        = absent
   ptrace              = absent

因此：

.. code-block:: text

   autoreap = false
   child exit_state remains EXIT_ZOMBIE

默认SIGCHLD行为与显式 ``SIG_IGN`` 在child reaping语义上不能混为一谈。

SIGCHLD 的 siginfo 怎样形成
---------------------------

``do_notify_parent()`` 根据child状态构造 ``kernel_siginfo``：

.. code-block:: text

   si_signo = SIGCHLD
   si_code  = CLD_EXITED
   si_pid   = child PID as seen in parent pid namespace
   si_uid   = child uid as seen by parent
   si_status= 42
   si_utime / si_stime = child accumulated CPU time

因为 ``exit_code=0x2a00`` 的低7位为0，所以它是normal exit：

.. code-block:: c

   info.si_code = CLD_EXITED;
   info.si_status = exit_code >> 8;  /* 42 */

signal notification中的 ``si_status=42`` 与wait4写入的raw integer ``0x2a00`` 是两种不同表示。

parent 为什么会从 wait4 睡眠中醒来
----------------------------------

``do_notify_parent()`` 在parent的 ``sighand->siglock`` 下完成signal generation，然后无条件调用：

.. code-block:: c

   __wake_up_parent(child, parent);

该函数执行：

.. code-block:: c

   __wake_up_sync_key(&parent->signal->wait_chldexit,
                      TASK_INTERRUPTIBLE, child);

wait queue上的callback是 ``child_wait_callback()``。它通过 ``pid_child_should_wake()`` 检查当前wait条件。parent等待明确的 ``child_pid``，key正是退出的child，因此匹配成功：

.. code-block:: text

   child_wait_callback
   → default_wake_function
   → try_to_wake_up(parent)
   → parent becomes runnable

signal delivery与 ``wait_chldexit`` wakeup是相关但独立的两件事。即使讨论signal disposition，也不能省略直接waitqueue wake。

为什么child此时仍不能释放 task_struct
-------------------------------------

parent被唤醒后需要访问：

* child PID；
* ``exit_state``；
* ``exit_code`` 与 ``group_exit_code``；
* CPU time、fault和I/O accounting；
* uid与rusage数据。

所以 ``exit_notify()`` 只把child发布为zombie，不调用普通成功路径的 ``release_task()``。

child 怎样停止占用 CPU
----------------------

``exit_notify()`` 返回后，``do_exit()`` 完成少量尾部清理：

.. code-block:: text

   proc_exit_connector
   → release memory policy / I/O context / temporary buffers
   → exit_task_stack_account
   → exit_rcu
   → lockdep_free_task
   → do_task_dead

``do_task_dead()`` 把当前task置于scheduler的dead状态并调用schedule。context switch选择另一个runnable task；退出中的child永远不会从该schedule返回。

child的kernel execution已经停止，但以下记录继续存在：

.. code-block:: text

   task_struct
   PID objects
   signal_struct exit accounting
   parent children-list entry
   exit_state = EXIT_ZOMBIE

zombie不在runqueue上，不消耗正常CPU调度时间，也没有userspace mm。

parent 和 child 的并发边界
-------------------------

``do_notify_parent()`` 在持有tasklist/signal相关锁时先完成：

.. code-block:: text

   publish EXIT_ZOMBIE
   → stabilize exit status/accounting
   → wake parent

因此parent一旦从wait queue醒来并取得 ``tasklist_lock``，就能观察到完整zombie状态。不会出现parent先醒来、却只看到一半exit信息的正常路径。

当前精确边界
------------

当前系统状态：

* child userspace execution：永久结束；
* child scheduler state：dead，不再运行；
* child ``exit_state``：``EXIT_ZOMBIE``；
* child PID/task_struct：仍保留；
* child mm/files/fs：已经释放；
* child raw wait status：``0x2a00``；
* SIGCHLD info：``CLD_EXITED``、status 42；
* autoreap：false；
* parent：已由 ``wait_chldexit`` wakeup变为runnable；
* parent wait syscall：尚未返回；
* child尚未 ``release_task``；
* PID尚未从process/PID索引中删除。

下一入口是parent再次运行 ``do_wait()`` 循环，并在 ``__do_wait()`` 中发现这个zombie。

关键边界
--------

#. ``EXIT_ZOMBIE`` 是wait生命周期状态，不等同于scheduler的task state。
#. 默认SIGCHLD disposition不触发本场景autoreap。
#. ``si_status=42`` 与raw wait status ``0x2a00`` 表示层次不同。
#. parent wakeup通过 ``wait_chldexit`` waitqueue完成，不应只写成“收到SIGCHLD”。
#. zombie已经释放mm/files，不在runqueue上。
#. ``task_struct`` 和PID必须保留到wait/reap。

资料
----

* `Linux 7.2-rc1 kernel/exit.c：exit_notify、child wait queue 与 do_task_dead调用点 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/exit.c>`_
* `Linux 7.2-rc1 kernel/signal.c：do_notify_parent 与 SIGCHLD siginfo <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/signal.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：do_task_dead与最终调度切换 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
