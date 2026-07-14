techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百六十四章：socketpair怎样建立双向Unix stream并让parent阻塞在epoll_wait？ <docs/tracks/linux-kernel/164-unix-socketpair-registers-with-epoll-and-blocks-parent.rst>`_
* `第一百六十五章：helper写入hello时，Unix stream skb怎样唤醒epoll并让read返回5？ <docs/tracks/linux-kernel/165-unix-stream-write-wakes-epoll-and-read-consumes-skb.rst>`_
* `第一百六十六章：shutdown(SHUT_WR)怎样让peer收到EPOLLRDHUP并让read返回EOF？ <docs/tracks/linux-kernel/166-unix-stream-shutdown-wakes-rdhup-and-read-returns-eof.rst>`_

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

最新场景
--------

::

   socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, sv) → fd 6/7
   → two unbound Unix stream sockets become mutual peers
   → epoll_create1(EPOLL_CLOEXEC) → fd 8
   → EPOLL_CTL_ADD watches fd 6 for EPOLLIN|EPOLLRDHUP
   → parent blocks on eventpoll wait queue
   → helper write(7,"hello",5) queues one skb on fd 6 receive queue
   → socket callback wakes parent
   → epoll_wait returns EPOLLIN and read(6) returns 5 bytes
   → parent re-enters epoll_wait and clears stale-ready membership
   → helper shutdown(7,SHUT_WR)
   → fd 7 gains SEND_SHUTDOWN; peer fd 6 gains RCV_SHUTDOWN
   → epoll_wait returns EPOLLIN|EPOLLRDHUP
   → read(6) returns EOF 0

最终fd 6/7/8仍然open。两端保持peer关系与 ``TCP_ESTABLISHED`` 协议状态；fd 7写方向已half-close，fd 6 receive方向持久处于 ``RCV_SHUTDOWN``，所以level-triggered registration持续ready。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、 ``project/STATE.rst``、章节目录和manifest。
