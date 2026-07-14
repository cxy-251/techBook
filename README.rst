techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百五十八章：inotify怎样建立目录watch并让parent阻塞在epoll_wait？ <docs/tracks/linux-kernel/158-inotify-watch-registers-with-epoll-and-blocks-parent.rst>`_
* `第一百五十九章：helper创建并关闭new.txt时，fsnotify怎样排入两条inotify事件？ <docs/tracks/linux-kernel/159-fsnotify-queues-create-and-close-write-events.rst>`_
* `第一百六十章：parent怎样从epoll event读取两条inotify_event记录？ <docs/tracks/linux-kernel/160-epoll-returns-inotify-and-read-consumes-two-records.rst>`_

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
   LK-INOTIFY-158..LK-INOTIFY-160

最新场景
--------

::

   inotify_init1(IN_CLOEXEC) -> fd 6
   → inotify_add_watch(/work, IN_CREATE|IN_CLOSE_WRITE) -> wd 1
   → epoll_create1(EPOLL_CLOEXEC) -> fd 7
   → EPOLL_CTL_ADD attaches callback to group notification_waitq
   → parent blocks on eventpoll wait queue
   → helper creates, writes and closes /work/new.txt through fd 8
   → fsnotify queues IN_CREATE then IN_CLOSE_WRITE
   → callback marks one epitem ready and wakes parent
   → epoll_wait returns {EPOLLIN,data=0x494E4F36}
   → read(6) returns two 32-byte records, total 64 bytes

最终fd 6/7、watch wd 1与epoll registration仍active。inotify queue已经为空；level-triggered epitem仍暂留ready list，等待下一次re-poll清除stale-ready状态。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
