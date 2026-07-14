techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百六十七章：EPOLL_CTL_DEL怎样从persistent-ready Unix socket拆除callback与epitem？ <docs/tracks/linux-kernel/167-epoll-del-detaches-unix-socket-callback-and-ready-item.rst>`_
* `第一百六十八章：close(6)怎样释放socket A，却让dead SA继续被peer reference保持？ <docs/tracks/linux-kernel/168-close-first-unix-socket-notifies-peer-and-keeps-dead-socket-referenced.rst>`_
* `第一百六十九章：close(7)与close(8)怎样释放两端Unix socket和空eventpoll？ <docs/tracks/linux-kernel/169-close-second-unix-socket-and-eventpoll-final-teardown.rst>`_

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
   LK-UNIXSOCK-164..LK-UNIXSOCK-166
   LK-UNIXSOCKCLOSE-167..LK-UNIXSOCKCLOSE-169

最新场景
--------

::

   persistent-ready fd 6 remains after peer SHUT_WR and EOF read
   → EPOLL_CTL_DEL removes socket wait callback P and epitem I
   → F6.f_ep becomes NULL; EP refcount 2→1
   → close(6) releases socket A file and sockfs VFS objects
   → SA becomes orphan/dead, TCP_CLOSE and SHUTDOWN_MASK
   → peer SB gains full SHUTDOWN_MASK and HUP semantics
   → SA remains alive because unix_peer(SB) still holds it
   → close(7) clears unix_peer(SB) and drops the final SA peer reference
   → SA and SB complete unix_sock_destructor teardown
   → close(8) releases empty eventpoll; EP storage is RCU-deferred

最终fd 6/7/8均已关闭。两个Unix socket、两份sockfs file与eventpoll均退出活动对象图；全局sockfs和anon_inodefs继续active。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、 ``project/STATE.rst``、章节目录和manifest。
