techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百七十三章：client connect怎样选择loopback路由、自动端口并进入TCP_SYN_SENT？ <docs/tracks/linux-kernel/173-client-connect-selects-loopback-route-and-ephemeral-port.rst>`_
* `第一百七十四章：tcp_connect怎样构造SYN并通过lo命中server listener？ <docs/tracks/linux-kernel/174-tcp-syn-traverses-loopback-and-finds-listener.rst>`_
* `第一百七十五章：listener怎样创建request_sock并把SYN-ACK排入client backlog？ <docs/tracks/linux-kernel/175-listener-creates-request-and-queues-synack-to-client-backlog.rst>`_

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

最新场景
--------

::

   server fd 6: 127.0.0.1:28080 TCP_LISTEN
   → client socket publishes blocking close-on-exec fd 7
   → local route selects 127.0.0.1 and lo
   → connect autobinds 127.0.0.1:40000
   → client enters TCP_SYN_SENT and ehash
   → tcp_connect builds SYN with C_ISN
   → SYN traverses IPv4 output and loopback receive
   → exact-address lhash2 finds server listener
   → listener allocates TCP_NEW_SYN_RECV request R
   → R enters ehash, arms request timer and raises qlen to 1
   → server sends SYN-ACK with S_ISN
   → SYN-ACK traverses lo and is queued in client C.sk_backlog

最终fd 6/7保持open。client仍为 ``SS_CONNECTING/TCP_SYN_SENT``，parent持有client socket lock并已经安装connect wait entry；request R在ehash中，accept queue仍为空。下一章从 ``release_sock(C)`` 处理SYN-ACK开始。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、 ``project/STATE.rst``、章节目录和manifest。
