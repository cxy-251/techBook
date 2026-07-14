techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百四十九章：零超时epoll_wait() 怎样清理timerfd的stale-ready item？ <docs/tracks/linux-kernel/149-zero-time-epoll-wait-removes-timerfd-stale-ready-item.rst>`_
* `第一百五十章：EPOLL_CTL_DEL 怎样拆除timerfd callback与epitem？ <docs/tracks/linux-kernel/150-epoll-del-detaches-timerfd-callback.rst>`_
* `第一百五十一章：close() 怎样释放timerfd与eventpoll并结束两套RCU生命周期？ <docs/tracks/linux-kernel/151-final-close-frees-timerfd-and-eventpoll.rst>`_

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

最新场景
--------

::

   epoll_wait(7, events2, 1, 0)
   → re-poll timerfd after expiration count was consumed
   → remove stale-ready epitem and return 0
   → epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → detach callback from timerfd wait queue
   → erase epitem and drop eventpoll refcount 2 → 1
   → close(6) cancels inactive hrtimer and queues timerfd ctx for RCU free
   → close(7) drains empty eventpoll and queues eventpoll for RCU free

最终fd 6/7均已关闭。callback同步释放；epitem、timerfd ctx与eventpoll退出活动对象图，其storage由各自RCU callback回收。全局 ``anon_inode_inode`` 与 ``anon_inode_mnt`` 继续存在。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
