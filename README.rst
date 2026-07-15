techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百八十五章：close(7)怎样撤销client fd并发送FIN？ <docs/tracks/linux-kernel/185-close-removes-client-fd-and-sends-fin.rst>`_
* `第一百八十六章：client FIN怎样让server H进入TCP_CLOSE_WAIT？ <docs/tracks/linux-kernel/186-client-fin-moves-server-to-close-wait.rst>`_
* `第一百八十七章：FIN ACK怎样完成client关闭并让read返回EOF？ <docs/tracks/linux-kernel/187-fin-ack-completes-client-close-and-read-returns-eof.rst>`_

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
   LK-TCPDATA-182..LK-TCPDATA-184
   LK-TCPCLOSE-185..LK-TCPCLOSE-187

最新场景
--------

::

   close(7)
   → file_close_fd先撤销fd 7
   → fput_close_sync同步进入socket release与tcp_close
   → C进入TCP_FIN_WAIT1并发送FIN C_ISN+6..C_ISN+7
   → IPv4 output与lo把FIN送到server child H
   → H.rcv_nxt推进到C_ISN+7并进入TCP_CLOSE_WAIT
   → RCV_SHUTDOWN与SOCK_DONE使fd 8 EOF-readable
   → quickack发送ACK C_ISN+7
   → ACK先进入仍被parent持有的C.sk_backlog
   → orphan close处理ACK并把C推进到TCP_FIN_WAIT2
   → 默认60秒边界建立tw_substate TCP_FIN_WAIT2的轻量TW
   → close(7)返回0
   → read(8,buf,1)消费FIN标记并返回0 EOF

最终fd 6与fd 8保持open，fd 7已关闭。client四元组由轻量TW以 ``TCP_FIN_WAIT2`` 子状态维护；H为 ``TCP_CLOSE_WAIT``，receive queue为空。下一章从server ``close(8)`` 开始。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、 ``project/STATE.rst``、章节目录和manifest。
