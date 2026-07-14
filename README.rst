techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百七十章：socket(AF_INET,SOCK_STREAM)怎样创建TCP endpoint并发布fd 6？ <docs/tracks/linux-kernel/170-inet-stream-socket-creates-tcp-endpoint-and-publishes-fd.rst>`_
* `第一百七十一章：bind(127.0.0.1:28080)怎样验证本地地址并占用TCP端口？ <docs/tracks/linux-kernel/171-bind-loopback-address-claims-tcp-port.rst>`_
* `第一百七十二章：listen(8)怎样建立空请求队列并把socket加入TCP监听哈希？ <docs/tracks/linux-kernel/172-listen-enters-tcp-listen-and-publishes-listener-hash.rst>`_

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
   LK-TCPLISTEN-170..LK-TCPLISTEN-172

最新场景
--------

::

   socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0)
   → create sockfs inode, struct socket and tcp_sock
   → select inet_stream_ops and tcp_prot
   → publish blocking close-on-exec fd 6
   → bind fd 6 to 127.0.0.1:28080
   → create TCP bind and bind2 buckets
   → keep socket in TCP_CLOSE without packet I/O
   → listen(fd 6, backlog 8)
   → initialize empty request/accept queue
   → TCP_CLOSE to TCP_LISTEN
   → insert listener into exact-address lhash2 bucket

最终fd 6保持open。server listener绑定 ``127.0.0.1:28080``，bind hash与listener hash均active；当前没有client、request socket、accepted child或skb。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、 ``project/STATE.rst``、章节目录和manifest。
