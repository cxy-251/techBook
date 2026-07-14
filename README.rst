techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百六十一章：零超时epoll_wait怎样清除inotify的stale-ready item？ <docs/tracks/linux-kernel/161-zero-time-epoll-wait-removes-inotify-stale-ready-item.rst>`_
* `第一百六十二章：inotify_rm_watch怎样先排入IN_IGNORED再销毁mark？ <docs/tracks/linux-kernel/162-inotify-rm-watch-queues-ignored-and-destroys-mark.rst>`_
* `第一百六十三章：读取IN_IGNORED后，close怎样释放inotify group与eventpoll？ <docs/tracks/linux-kernel/163-read-ignored-and-final-close-free-inotify-eventpoll.rst>`_

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
   LK-INOTIFYCLOSE-161..LK-INOTIFYCLOSE-163

最新场景
--------

::

   zero-time epoll_wait re-polls empty inotify queue
   → stale-ready item removed and wait returns 0
   → inotify_rm_watch(6,1)
   → queue wd1 IN_IGNORED before removing wd from IDR
   → callback makes registration ready again
   → mark detaches from group and /work inode connector
   → zero-time epoll_wait returns EPOLLIN
   → read(6) returns one 16-byte IN_IGNORED record
   → EPOLL_CTL_DEL removes callback and epitem
   → close(6) destroys fsnotify group and waits mark SRCU reaper
   → close(7) releases empty eventpoll

最终fd 6/7均已关闭。wd 1、inotify mark、fsnotify group、inotify file与eventpoll file均已结束生命周期；``/work/new.txt``继续存在，全局anon_inodefs保持active。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
