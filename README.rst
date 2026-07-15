techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百七十九章：accept4怎样先预留fd 8并创建尚未graft的socket与file？ <docs/tracks/linux-kernel/179-accept4-reserves-fd-and-builds-unattached-socket-file.rst>`_
* `第一百八十章：inet_csk_accept怎样取出R/H并把child graft到accepted socket？ <docs/tracks/linux-kernel/180-inet-csk-accept-removes-child-and-grafts-socket.rst>`_
* `第一百八十一章：peer地址怎样写回用户态并最终发布close-on-exec fd 8？ <docs/tracks/linux-kernel/181-peer-address-copy-publishes-accepted-fd.rst>`_

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
   LK-TCPCONNECT-173..LK-TCPCONNECT-175
   LK-TCPHANDSHAKE-176..LK-TCPHANDSHAKE-178
   LK-TCPACCEPT-179..LK-TCPACCEPT-181

最新场景
--------

::

   accept4(6,&peer,&peer_len,SOCK_CLOEXEC)
   → FD_ADD先预留fd 8并设置close-on-exec bit
   → sock_alloc创建accepted socket AS与sockfs inode I8
   → sock_alloc_file创建blocking file F8，但fdtable.fd[8]仍为NULL
   → inet_csk_accept从accept queue移除R/H
   → listener sk_ack_backlog 1 → 0，R结束生命周期
   → sock_graft把H接到AS，AS进入SS_CONNECTED
   → inet_getname生成peer 127.0.0.1:40000
   → move_addr_to_user写回16字节sockaddr_in
   → fd_install发布F8到fd 8
   → accept4返回8

最终fd 6/7/8保持open。fd 8是blocking、close-on-exec的accepted TCP socket；listener accept queue为空。下一章从client fd 7执行 ``write(7,"hello",5)`` 开始。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、 ``project/STATE.rst``、章节目录和manifest。
