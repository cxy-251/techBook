techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百零一章：_exit(42) 怎样进入 do_exit() 并释放进程运行资源？ <docs/tracks/linux-kernel/101-child-exit-tears-down-runtime-resources.rst>`_
* `第一百零二章：exit_notify() 怎样发送 SIGCHLD、唤醒 parent 并留下 zombie？ <docs/tracks/linux-kernel/102-exit-notify-wakes-parent-and-leaves-zombie.rst>`_
* `第一百零三章：parent 的 wait4() 怎样读取 status 并最终回收 child？ <docs/tracks/linux-kernel/103-parent-wait4-reaps-child.rst>`_

固定来源
--------

::

   x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

已经完成
--------

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097
   LK-EXEC-098..LK-EXEC-100
   LK-EXIT-101..LK-EXIT-103

最新场景
--------

::

   parent wait4(child_pid, &status, 0, &rusage)
   → child _exit(42)
   → do_exit / release runtime resources
   → EXIT_ZOMBIE / SIGCHLD / wake parent
   → wait_task_zombie
   → status = 0x2a00
   → WEXITSTATUS(status) = 42
   → release_task

parent返回child PID；child的process/PID关系已回收，最终task memory按reference count与RCU完成释放。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
