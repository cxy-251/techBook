techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百八十二章：write(7,"hello",5)怎样把5字节排入client TCP write queue？ <docs/tracks/linux-kernel/182-client-write-queues-five-byte-tcp-segment.rst>`_
* `第一百八十三章：PSH|ACK数据段怎样通过lo进入H并触发立即ACK？ <docs/tracks/linux-kernel/183-loopback-data-reaches-server-child-and-triggers-ack.rst>`_
* `第一百八十四章：write怎样在ACK处理后返回5，并让read(8)取出hello？ <docs/tracks/linux-kernel/184-client-write-returns-and-server-read-consumes-hello.rst>`_

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

最新场景
--------

::

   write(7,"hello",5)
   → tcp_sendmsg_locked复制5字节并建立ACK|PSH skb
   → tcp_write_xmit发送clone，原始skb进入retransmission tree
   → IPv4 output与lo把data送到server child H
   → H.rcv_nxt推进到C_ISN+6，receive queue得到hello
   → fd 8变为可读
   → first-data quickack发送ACK C_ISN+6
   → ACK先进入仍被parent持有的C.sk_backlog
   → release_sock(C)处理ACK并清空client retransmission tree
   → write返回5
   → read(8,buf,5)无等待复制hello并清空H receive queue
   → read返回5

最终fd 6/7/8保持open。C与H仍为TCP_ESTABLISHED；双方数据队列、retransmission tree与socket backlog为空。下一章从client close(7)开始。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、 ``project/STATE.rst``、章节目录和manifest。

