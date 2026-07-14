第一百零三章：parent 的 wait4() 怎样读取 status 并最终回收 child？
===========================================================================

第一百零二章结束时，child已经成为 ``EXIT_ZOMBIE``，parent因 ``wait_chldexit`` wakeup重新变成runnable。现在scheduler再次选择parent，继续它尚未完成的：

.. code-block:: c

   wait4(child_pid, &status, 0, &rusage);

parent没有pending fatal signal，``status`` 与 ``rusage`` userspace buffers均映射、可写且稳定。

parent最初怎样睡进 wait4
------------------------

native x86-64 ``wait4`` 进入：

.. code-block:: text

   entry_SYSCALL_64
   → __x64_sys_wait4
   → kernel_wait4

固定参数形成：

.. code-block:: text

   wo_type   = PIDTYPE_PID
   wo_pid    = child PID object
   wo_flags  = WEXITED
   wo_stat   = 0
   wo_rusage = kernel rusage buffer

``do_wait()`` 把 ``wo->child_wait`` 加入：

.. code-block:: c

   current->signal->wait_chldexit

第一次调用 ``__do_wait()`` 时child仍活着，所以wait扫描确认“存在符合条件的child，但还没有可返回事件”，得到 ``-ERESTARTSYS``。parent没有signal需要处理，于是调用 ``schedule()`` 进入 ``TASK_INTERRUPTIBLE``。

上一章的child wakeup使这个schedule返回，``do_wait()`` 再次循环。

``__do_wait`` 怎样直接定位 child
--------------------------------

因为 ``wo_type=PIDTYPE_PID``，``__do_wait()`` 不需要遍历parent全部children，而是进入：

.. code-block:: text

   do_wait_pid
   → pid_task(wo_pid, PIDTYPE_TGID)
   → is_effectively_child
   → wait_consider_task

在 ``tasklist_lock`` read side保护下读取：

.. code-block:: text

   child->exit_state = EXIT_ZOMBIE
   child->exit_signal = SIGCHLD
   child is natural child of current parent

``eligible_child()`` 通过。没有ptrace，child没有其他thread，因此进入：

.. code-block:: c

   wait_task_zombie(wo, child);

谁取得 zombie 的回收所有权
--------------------------

多个parent线程理论上可能同时wait同一个child。``wait_task_zombie()`` 使用原子状态转换：

.. code-block:: c

   cmpxchg(&child->exit_state,
           EXIT_ZOMBIE,
           EXIT_DEAD);

固定parent成功把状态从 ``EXIT_ZOMBIE`` 改成 ``EXIT_DEAD``。从这一刻起，它取得唯一reaping ownership；其他waiter不能再次消费同一exit event。

``EXIT_DEAD`` 仍不表示所有内存已经同步释放。它表示zombie已经被某个waiter认领，可以开始 ``release_task()``。

rusage 为什么在 release_task 前读取
-----------------------------------

child的task/signal结构还保存：

* user/system CPU time；
* minor/major faults；
* voluntary/involuntary context switches；
* block I/O accounting；
* maximum RSS；
* 已回收后代的累计使用量。

``wait_task_zombie()`` 先把这些值累计进parent ``signal_struct`` 的child-accounting字段，并执行：

.. code-block:: c

   getrusage(child, RUSAGE_BOTH, wo->wo_rusage);

只有完成这些读取后，才可以删除child task结构。

raw status 怎样得到 ``0x2a00``
-----------------------------

单线程child在 ``synchronize_group_exit()`` 中设置过 ``SIGNAL_GROUP_EXIT``，因此wait路径读取：

.. code-block:: c

   status = child->signal->group_exit_code;

结果为：

.. code-block:: text

   wo->wo_stat = 0x00002a00

userspace宏解释为：

.. code-block:: c

   WIFEXITED(status)    == true
   WEXITSTATUS(status)  == 42
   WIFSIGNALED(status)  == false

raw status本身不是42；42位于高8位。

``release_task`` 删除哪些最后记录
---------------------------------

``wait_task_zombie()`` 在 ``EXIT_DEAD`` 路径调用：

.. code-block:: c

   release_task(child);

关键步骤包括：

.. code-block:: text

   pidfs_exit
   → cgroup_task_release
   → tasklist_lock write side
   → ptrace_release_task
   → __exit_signal
   → 从global task list / parent children list / PID links解除
   → proc_flush_pid
   → exit credential namespace references
   → free_pids
   → release_thread
   → flush pending signal queues
   → put_task_struct_rcu_user

``__exit_signal()`` 汇总最后的thread accounting并执行process unhash。``free_pids()`` 释放task持有的PID links；parent wait代码自己通过 ``find_get_pid`` 持有的临时 ``struct pid`` reference会在 ``kernel_wait4()`` 返回前由 ``put_pid()`` 释放。

``put_task_struct_rcu_user()`` 可能通过 ``call_rcu()`` 延迟最终 ``task_struct`` memory free。原因是其他CPU上的RCU reader可能仍持有无锁观察引用。

所以：

.. code-block:: text

   wait成功认领child
   → child从可查process关系中消失
   → task_struct最终内存可能稍后RCU回收

两者不必发生在同一条机器指令上。

status 与 rusage 怎样复制回 userspace
------------------------------------

``wait_task_zombie()`` 返回child PID。``do_wait()``：

.. code-block:: text

   parent state → TASK_RUNNING
   → remove_wait_queue(wait_chldexit)
   → return child PID

``kernel_wait4()`` 接着：

.. code-block:: c

   put_user(wo.wo_stat, stat_addr);

把 ``0x2a00`` 写入userspace ``status``。syscall wrapper再把kernel ``struct rusage`` 复制到userspace ``rusage``。

固定copy全部成功，最终syscall return value是：

.. code-block:: text

   parent RAX = child PID

注意返回值不是exit status。返回值标识“哪个child被回收”；status通过pointer参数返回。

parent 返回用户态后的对象状态
-----------------------------

syscall exit经过正常：

.. code-block:: text

   syscall_exit_to_user_mode
   → SYSRETQ 或 IRETQ
   → parent CPL 3

用户态观察：

.. code-block:: text

   wait4 return value = child PID
   status             = 0x2a00
   WEXITSTATUS        = 42
   rusage             = child completed accounting

内核对象状态：

.. code-block:: text

   child mm/files/fs       = 早已释放
   child exit_state        = 已从 ZOMBIE 转为 DEAD并回收
   child process-list link = 已删除
   child parent-list link  = 已删除
   child PID links         = 已释放
   child task_struct       = 已put，最终free受RCU/refcount约束
   parent children list    = 不再包含该child

同一child再次执行 ``wait4(child_pid, ...)`` 将不再得到exit event；在没有其他符合条件child时会返回 ``-ECHILD``。

当前精确状态
------------

* current executor：parent；
* CPU mode：x86-64 CPL 3；
* ``wait4`` return：child PID；
* userspace ``status``：``0x2a00``；
* decoded exit status：42；
* userspace ``rusage``：已填充；
* parent ``wait_chldexit`` entry：已移除；
* child zombie：已被消费；
* child task/PID process visibility：已删除；
* child最终task memory：由reference count/RCU完成释放；
* parent mm/files/process identity：继续存在；
* fork → COW → exec → exit → wait生命周期场景：complete；
* next runtime scenario：unselected。

关键边界
--------

#. ``wait4`` 返回child PID，exit status通过pointer写回。
#. ``EXIT_ZOMBIE → EXIT_DEAD`` 使用cmpxchg保证只被一个waiter认领。
#. rusage与status必须在 ``release_task`` 前读取。
#. ``release_task`` 删除process/PID关系，最终task_struct free可能受RCU延迟。
#. ``0x2a00`` 才是raw wait status；42是 ``WEXITSTATUS`` 解码结果。
#. child在wait前已经释放重资源，wait负责消费死亡记录并完成身份回收。

资料
----

* `Linux 7.2-rc1 kernel/exit.c：do_wait、wait_task_zombie、kernel_wait4 与 release_task <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/exit.c>`_
* `Linux 7.2-rc1 include/uapi/linux/wait.h：wait options与status接口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/uapi/linux/wait.h>`_
* `Linux 7.2-rc1 include/linux/pid.h：struct pid引用与PID lookup <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/pid.h>`_
