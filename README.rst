techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百五十五章：reap之后的pidfd为什么让epoll_wait返回EPOLLIN|EPOLLHUP？ <docs/tracks/linux-kernel/155-post-reap-pidfd-delivers-epollhup.rst>`_
* `第一百五十六章：EPOLL_CTL_DEL怎样拆除pidfd callback与epitem？ <docs/tracks/linux-kernel/156-epoll-del-detaches-pidfd-callback.rst>`_
* `第一百五十七章：close()怎样释放pidfs inode、旧struct pid与eventpoll？ <docs/tracks/linux-kernel/157-final-close-frees-pidfd-pid-identity-and-eventpoll.rst>`_

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
   LK-PIDFDCLOSE-155..LK-PIDFDCLOSE-157

最新场景
--------

::

   post-reap epoll_wait(..., 0)
   → pidfd_poll sees no task linkage
   → deliver EPOLLIN|EPOLLHUP
   → level-triggered epitem remains ready
   → EPOLL_CTL_DEL removes callback and epitem
   → close(6) prunes pidfs dentry and evicts pidfs inode
   → final pid references release exit metadata and old struct pid
   → close(7) releases empty eventpoll

最终fd 6/7均已关闭。旧child task、pidfd file、pidfs dentry/inode、旧 ``struct pid``、exit metadata、epitem与eventpoll均已退出活动对象图；全局pidfs mount和anon_inodefs继续存在。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
