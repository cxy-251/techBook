项目状态
========

最后更新
--------

2026-07-14

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097
   LK-EXEC-098..LK-EXEC-100
   LK-EXIT-101..LK-EXIT-103

最新三章：

#. ``LK-EXIT-101``：_exit(42) 怎样进入 do_exit() 并释放进程运行资源？
#. ``LK-EXIT-102``：exit_notify() 怎样发送 SIGCHLD、唤醒 parent 并留下 zombie？
#. ``LK-EXIT-103``：parent 的 wait4() 怎样读取 status 并最终回收 child？

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

已完成的运行期实验
------------------

#. cold-miss ``read(fd, buf, 4096)``；
#. ext4 ``O_SYNC write(fd, buf, 4096)``；
#. native x86-64 ``fork()``；
#. child private-anonymous COW write fault；
#. child static ELF ``execve()``；
#. child ``_exit(42)`` 与 parent ``wait4()`` 回收。

exit/wait 固定场景
------------------

::

   parent call         = wait4(child_pid, &status, 0, &rusage)
   parent initial state= sleeping TASK_INTERRUPTIBLE on wait_chldexit
   child call          = _exit(42)
   threading           = parent and child single-threaded
   child set           = parent has only this child
   SIGCHLD             = default disposition; no explicit SIG_IGN or SA_NOCLDWAIT
   ptrace/subreaper    = disabled
   userspace buffers   = status and rusage mapped, writable and stable
   failure policy      = no signal interruption or copy fault

完整控制流
----------

::

   parent wait4
   → kernel_wait4 / do_wait
   → child still live
   → parent sleeps on wait_chldexit

   child _exit(42)
   → __x64_sys_exit
   → do_exit(0x2a00)
   → PF_EXITING / accounting finalized
   → exit_mm
   → exit_files / exit_fs / namespace and thread cleanup
   → exit_notify
   → EXIT_ZOMBIE
   → do_notify_parent
   → SIGCHLD: CLD_EXITED, si_status=42
   → wake parent wait_chldexit
   → do_task_dead / schedule away forever

   parent resumes do_wait
   → do_wait_pid
   → wait_consider_task
   → wait_task_zombie
   → cmpxchg EXIT_ZOMBIE to EXIT_DEAD
   → collect rusage and raw status 0x2a00
   → release_task
   → unlink process, parent-child and PID relations
   → put_user(status) / copy rusage
   → wait4 returns child PID

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU mode：x86-64 CPL 3；
* ``wait4`` return：child PID；
* userspace ``status``：``0x2a00``；
* ``WIFEXITED(status)``：true；
* ``WEXITSTATUS(status)``：42；
* userspace ``rusage``：已填充；
* parent waitqueue entry：已移除；
* child mm/files/fs：已释放；
* child zombie：已消费；
* child process/PID visibility：已删除；
* child task memory：最终释放受reference count与RCU约束；
* parent children list：不再包含该child；
* process lifecycle场景：complete；
* next runtime scenario：unselected。

关键边界
--------

#. ``_exit(42)`` 形成raw wait status ``0x2a00``。
#. child在成为zombie前已释放mm/files等重资源。
#. 默认SIGCHLD不等于显式 ``SIG_IGN``，本场景不会autoreap。
#. waitqueue wakeup不能只概括为“发送SIGCHLD”。
#. ``EXIT_ZOMBIE``、scheduler dead state和 ``EXIT_DEAD`` 是不同阶段。
#. ``wait4`` 返回PID，status通过pointer返回。
#. ``release_task`` 删除process/PID关系，最终task memory可能延迟到RCU grace period。

下一任务
--------

当前没有已选定场景。后续可选择新的独立主线，例如：

::

   anonymous mmap / page fault / reclaim / swap
   或
   socket / TCP send / receive
   或
   scheduler preemption / context switch

开始前必须重新固定用户态入口、对象状态、缓存状态、并发关系与失败策略。
