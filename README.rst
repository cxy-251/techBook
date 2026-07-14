techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百五十二章：pidfd_open() 怎样建立pidfs file并让epoll_wait监视child？ <docs/tracks/linux-kernel/152-pidfd-open-registers-child-with-epoll.rst>`_
* `第一百五十三章：child _exit(42) 怎样通过pid->wait_pidfd唤醒epoll_wait？ <docs/tracks/linux-kernel/153-child-exit-wakes-pidfd-epoll-waiter.rst>`_
* `第一百五十四章：waitid(P_PIDFD) 怎样读取退出状态并回收child？ <docs/tracks/linux-kernel/154-waitid-pidfd-reaps-child-after-epoll-event.rst>`_

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
   LK-OPEN-104..LK-OPEN-106
   LK-DELALLOC-107..LK-DELALLOC-109
   LK-UNLINK-110..LK-UNLINK-112
   LK-SLEEP-113..LK-SLEEP-115
   LK-SIGNAL-116..LK-SIGNAL-118
   LK-PIPE-119..LK-PIPE-121
   LK-PIPECLOSE-122..LK-PIPECLOSE-124
   LK-FUTEX-125..LK-FUTEX-127
   LK-EVENTFD-128..LK-EVENTFD-130
   LK-EVENTFDCLOSE-131..LK-EVENTFDCLOSE-133
   LK-EPOLL-134..LK-EPOLL-136
   LK-EPOLLCLOSE-137..LK-EPOLLCLOSE-139
   LK-SIGNALFD-140..LK-SIGNALFD-142
   LK-SIGNALFDCLOSE-143..LK-SIGNALFDCLOSE-145
   LK-TIMERFD-146..LK-TIMERFD-148
   LK-TIMERFDCLOSE-149..LK-TIMERFDCLOSE-151
   LK-PIDFD-152..LK-PIDFD-154

最新场景
--------

::

   parent pidfd_open(child_pid, 0) -> fd 6
   → pidfs inode pins the child's struct pid
   → epoll_create1(EPOLL_CLOEXEC) -> fd 7
   → EPOLL_CTL_ADD attaches callback to pid->wait_pidfd
   → parent blocks in epoll_wait
   → child _exit(42) enters EXIT_ZOMBIE
   → do_notify_pidfd queues the epitem and wakes parent
   → epoll_wait returns {EPOLLIN, data=0x50494436}
   → waitid(P_PIDFD, 6, ..., WEXITED, NULL) returns 0
   → siginfo reports CLD_EXITED and status 42
   → child is reaped and numeric PID becomes reusable

最终fd 6/7与registration仍active。child task已经回收，pidfs inode仍保持旧 ``struct pid``，因此pidfd不会因数字PID复用而指向新进程。level-triggered epitem仍在ready list；下一次pidfd poll将报告 ``EPOLLIN|EPOLLHUP``。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
