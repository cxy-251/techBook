techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百八十八章：close(8)怎样撤销accepted fd并发送server FIN？ <docs/tracks/linux-kernel/188-close-accepted-fd-sends-server-fin.rst>`_
* `第一百八十九章：FIN_WAIT2 TW怎样接收server FIN并发送最终ACK？ <docs/tracks/linux-kernel/189-finwait2-timewait-socket-receives-server-fin.rst>`_
* `第一百九十章：最终ACK怎样结束H的LAST_ACK并让close(8)返回0？ <docs/tracks/linux-kernel/190-final-ack-destroys-last-ack-server-socket.rst>`_

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
   LK-TCPPEERCLOSE-188..LK-TCPPEERCLOSE-190

最新场景
--------

::

   close(8)
   → file_close_fd先撤销fd 8
   → fput_close_sync同步进入socket release与tcp_close
   → H进入TCP_LAST_ACK并发送HFIN S_ISN+1..S_ISN+2
   → IPv4 output与lo把HFIN送到client轻量TW
   → TW以FIN_WAIT2子状态验证精确peer FIN
   → tw_rcv_nxt推进到S_ISN+2，substate进入真正TCP_TIME_WAIT
   → TIME_WAIT timer从HFIN到达时重新计60秒
   → per-CPU control socket发送TACK ack S_ISN+2
   → TACK先进入仍被parent持有的H.sk_backlog
   → orphan close处理TACK并清除HFIN original
   → H完成TCP_LAST_ACK到TCP_CLOSE并销毁
   → close(8)返回0

最终fd 6保持open，fd 7/8已关闭。完整C与H都已销毁；client四元组仅由真正 ``TCP_TIME_WAIT`` 的轻量TW维护。下一入口是TW的60秒timer到期，随后再关闭listener fd 6。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、 ``project/STATE.rst``、章节目录和manifest。
