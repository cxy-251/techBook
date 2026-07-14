第一百零一章：_exit(42) 怎样进入 do_exit() 并释放进程运行资源？
==========================================================================

上一场景结束时，原 fork child 已经成功 exec 为静态程序 ``/bin/static-demo``，正在 CPL 3 执行。现在固定它调用：

.. code-block:: c

   _exit(42);

同时固定 parent 已经先执行：

.. code-block:: c

   wait4(child_pid, &status, 0, &rusage);

并在 ``wait_chldexit`` wait queue 上进入 ``TASK_INTERRUPTIBLE``。父子均为单线程；parent只有这一个child；没有ptrace、subreaper、``SA_NOCLDWAIT``、显式 ``SIG_IGN``、signal interruption或userspace copy fault。

``_exit`` 进入哪个 syscall
--------------------------

本场景使用native x86-64 ``exit`` syscall，而不是 ``exit_group``。对于单线程process，两者最终都结束整个process；源码入口仍然不同。

用户态执行 ``SYSCALL`` 后：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → x64_sys_call
   → __x64_sys_exit

``SYSCALL_DEFINE1(exit)`` 执行：

.. code-block:: c

   do_exit((error_code & 0xff) << 8);

因此用户给出的 ``42`` 被编码为传统wait status格式：

.. code-block:: text

   exit code argument = 42
   do_exit code       = 42 << 8
                      = 0x00002a00

低7位为0，表示不是由signal终止；高8位保存normal exit status。

为什么 ``do_exit`` 永远不会返回
-------------------------------

``do_exit(long code)`` 标记为 ``__noreturn``。一旦进入，当前task不会再回到static program，也不会走普通syscall return。

开始阶段：

.. code-block:: text

   synchronize_group_exit(current, 0x2a00)
   → signal->quick_threads--
   → 单线程组变成0
   → SIGNAL_GROUP_EXIT
   → signal->group_exit_code = 0x2a00

随后：

.. code-block:: text

   exit_signals(current)
   → PF_EXITING
   → 阻止新的普通工作继续附着到task

``current->exit_code`` 也被设置为 ``0x2a00``。wait路径稍后可从 ``signal->group_exit_code`` 或 ``task_struct.exit_code`` 取得同一个status。

退出为什么先完成accounting
--------------------------

在通知parent之前，``do_exit()`` 先完成：

.. code-block:: text

   acct_update_integrals
   → signal->live--
   → group_dead = true
   → acct_collect
   → taskstats_exit
   → trace_sched_process_exit
   → perf_event_exit_task

本场景child是thread group中最后且唯一的thread，所以 ``group_dead=true``。CPU time、minor/major faults、context switches和I/O accounting必须在parent被唤醒前稳定，否则parent的 ``wait4(..., &rusage)`` 可能读取到不完整结果。

``exit_mm`` 怎样拆掉新ELF地址空间
--------------------------------

``do_exit()`` 接着调用：

.. code-block:: c

   exit_mm();

进入时：

.. code-block:: text

   current->mm        = static-demo executable mm
   current->active_mm = same mm

``exit_mm()`` 在mmap lock和task lock保护下执行关键状态转换：

.. code-block:: c

   current->mm = NULL;
   enter_lazy_tlb(mm, current);
   mm_update_next_owner(mm);
   mmput(mm);

``current->mm = NULL`` 表示task已经不再拥有userspace address space。``mmput()`` 在最后一个mm user引用消失时释放：

* ELF text/data file-backed VMAs；
* BSS、heap和user stack VMAs；
* page-table pages与PTE mappings；
* entry text folio的mapping reference；
* anonymous pages与相关rmap/memcg引用。

这不是把整个 ``task_struct`` 释放。退出中的task仍在其kernel stack上继续执行 ``do_exit()``。

parent的mm是fork时创建的独立对象，不会因为child ``exit_mm()`` 被修改。

files 与 fs 状态在哪里释放
--------------------------

地址空间之后，``do_exit()`` 依次调用：

.. code-block:: text

   exit_sem
   → exit_shm
   → exit_files
   → exit_fs
   → exit_nsproxy_namespaces
   → exit_task_work
   → exit_thread

``exit_files(current)`` 把 ``current->files`` 取走并减少 ``files_struct`` 引用。child在fork时已有独立fd table；exec仅关闭了fd 5，剩余fd entries现在全部由exit关闭。

对应fd可能仍与parent引用同一个 ``struct file``。child关闭自己的entry只减少引用计数；只要parent仍有引用，open file description及其file offset继续存在。

``exit_fs()`` 释放child的 ``fs_struct``，包括root和current working directory path引用。namespace对象、task work和architecture thread state也按各自生命周期退出。

退出资源与zombie信息必须分开
----------------------------

到这里，child已经失去：

.. code-block:: text

   userspace mm
   fd table
   fs_struct
   executable mappings
   namespace task reference
   architecture userspace thread state

仍然保留：

.. code-block:: text

   task_struct
   PID/TGID identity
   parent/child list linkage
   signal_struct中的exit/accounting结果
   exit_code = 0x2a00
   kernel stack，直到最后schedule away

保留这些最小对象是为了让parent稍后读取child PID、status和rusage。zombie不是“完整进程仍占着所有内存”，而是“运行资源已拆除，只保留可等待的死亡记录”。

当前精确边界
------------

``do_exit()`` 即将调用：

.. code-block:: c

   exit_notify(current, group_dead);

当前状态：

* current task：static-demo child；
* CPU mode：CPL 0，exit syscall process context；
* exit code：``0x2a00``；
* ``PF_EXITING``：已设置；
* ``group_dead``：true；
* ``current->mm``：NULL；
* executable mm：已由 ``mmput`` 释放；
* ``current->files``：已释放，剩余child fds已关闭；
* ``current->fs``：已释放；
* parent：仍在 ``wait4`` 中睡眠；
* child ``exit_state``：尚未设置为 ``EXIT_ZOMBIE``；
* SIGCHLD：尚未发送；
* child task/PID：仍然存在；
* parent尚不能完成回收。

关键边界
--------

#. ``_exit(42)`` 向wait接口保存的是 ``0x2a00``。
#. ``do_exit()`` 不会普通返回用户态。
#. accounting在唤醒parent前完成。
#. ``exit_mm`` 清除userspace地址空间，不释放 ``task_struct``。
#. child与parent共享的 ``struct file`` 仅减少child一侧引用。
#. zombie只需保留identity、status与accounting，不保留完整运行资源。

资料
----

* `Linux 7.2-rc1 kernel/exit.c：exit syscall、do_exit 与 exit_mm <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/exit.c>`_
* `Linux 7.2-rc1 fs/file.c：exit_files 与 files_struct释放 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
* `Linux 7.2-rc1 fs/fs_struct.c：exit_fs 与 fs_struct释放 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/fs_struct.c>`_
