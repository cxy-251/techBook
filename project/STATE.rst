项目状态
========

最后更新
--------

2026-07-15

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

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

最新三章：

#. ``LK-TCPDATA-182``：write(7,"hello",5)怎样把5字节排入client TCP write queue？
#. ``LK-TCPDATA-183``：PSH|ACK数据段怎样通过lo进入H并触发立即ACK？
#. ``LK-TCPDATA-184``：write怎样在ACK处理后返回5，并让read(8)取出hello？

进度
----

当前已经完成184章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

固定数据调用
------------

.. code-block:: c

   ssize_t written = write(7, "hello", 5);

   char buf[5];
   ssize_t received = read(8, buf, sizeof(buf));

固定条件：

::

   CPUs online            = CPU0 only
   network namespace      = N
   loopback device        = lo UP, MTU 65536
   listener fd            = 6
   listener endpoint      = 127.0.0.1:28080
   client fd              = 7, blocking, close-on-exec
   client endpoint        = 127.0.0.1:40000
   accepted fd            = 8, blocking, close-on-exec
   client/server state    = TCP_ESTABLISHED/TCP_ESTABLISHED
   client/server ISN      = C_ISN 0x13572468 / S_ISN 0x24681357
   write flags            = 0
   payload                = "hello", 5 bytes
   TCP_NODELAY/CORK       = disabled/disabled
   MSG_MORE/OOB/zerocopy  = disabled
   H initial ack ato      = 0
   H sk_rcvlowat          = 1
   failures/races         = none

完整控制流
----------

::

   write(7,"hello",5)
   → fd7 resolves F7/CS/C
   → sock_write_iter builds source iterator
   → inet_sendmsg dispatches to tcp_sendmsg
   → parent locks client C
   → tcp_sendmsg_locked allocates one skb
   → tcp_skb_entail sets seq=end_seq=C_ISN+1 and ACK
   → copy hello into skb page frag
   → C.write_seq and skb.end_seq become C_ISN+6
   → no MSG_MORE, so tcp_mark_push adds PSH
   → Nagle/autocork allow immediate transmit
   → tcp_write_xmit sends clone through ip_queue_xmit
   → original skb enters C retransmission tree
   → C.snd_nxt becomes C_ISN+6; snd_una remains C_ISN+1

   data clone
   → IPv4 output uses cached RTN_LOCAL route
   → dev_queue_xmit selects noqueue lo
   → loopback_xmit queues skb to CPU0 input backlog
   → NET_RX tcp_v4_rcv ehash lookup finds H
   → H is not user-owned, so tcp_rcv_established runs directly
   → queue five-byte skb on H.sk_receive_queue
   → H.rcv_nxt becomes C_ISN+6
   → tcp_data_ready exposes EPOLLIN on accepted fd8
   → first-data ato=0 enters quickack
   → H sends pure ACK seq=S_ISN+1 ack=C_ISN+6

   reverse ACK
   → loopback ehash lookup finds C
   → parent still owns C
   → tcp_add_backlog queues ACK on C.sk_backlog
   → tcp_sendmsg_locked returns copied=5
   → release_sock(C) drains ACK in process context
   → C.snd_una becomes C_ISN+6
   → original hello skb leaves retransmission tree
   → write returns 5

   read(8,buf,5)
   → fd8 resolves F8/AS/H
   → sock_read_iter and inet_recvmsg enter tcp_recvmsg
   → lock H; receive queue is already non-empty
   → no sk_wait_data and no schedule
   → copy five bytes to user buf
   → H.copied_seq becomes C_ISN+6
   → remove and free receive skb
   → tcp_cleanup_rbuf sees no scheduled ACK
   → read returns 5 with buf="hello"

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* last syscall/result：``read(8,buf,5)=5``；
* user buffer：``"hello"``；
* parent：``TASK_RUNNING``；
* write/read scheduler count：0/0；
* server fd 6：open、blocking、close-on-exec；
* listener ``L``：``TCP_LISTEN``，endpoint ``127.0.0.1:28080``；
* listener accept queue：empty，``sk_ack_backlog=0``；
* client fd 7：open、blocking、close-on-exec；
* client ``C``：``TCP_ESTABLISHED``；
* C tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* C ``snd_una=snd_nxt=write_seq=C_ISN+6``；
* C ``rcv_nxt=S_ISN+1``；
* C write queue、retransmission tree与socket backlog：empty；
* accepted fd 8：open、blocking、close-on-exec；
* accepted socket ``AS``：``SS_CONNECTED``；
* server child ``H``：``TCP_ESTABLISHED``；
* H tuple：``127.0.0.1:28080 ← 127.0.0.1:40000``；
* H ``rcv_nxt=copied_seq=C_ISN+6``；
* H ``snd_una=snd_nxt=S_ISN+1``；
* H receive queue：empty，readable bytes 0；
* C/H route、ehash与bind ownership：active；
* packet与CPU0 NET_RX backlog：empty；
* next runtime entry：``close(7)``。

关键边界
--------

#. fd 7是client发送端；fd 8是accepted server接收端。
#. 固定write flags为0，不启用MSG_MORE、OOB、nonblock、zerocopy或splice。
#. 一个skb承载5字节；sequence区间是 ``[C_ISN+1,C_ISN+6)``。
#. tcp_skb_entail先建立ACK空skb；copy推进write_seq与end_seq。
#. 没有MSG_MORE时PSH被设置；PSH不消耗sequence number。
#. 没有旧unacked data，因此Nagle与autocork不延迟segment。
#. 发送clone经lo进入receive；原始skb进入client retransmission tree。
#. established ehash查找命中H，不经过listener。
#. H未被用户task持有，data不进入H.sk_backlog。
#. H.rcv_nxt在入队时推进；copied_seq要到read时才推进。
#. 五字节满足默认sk_rcvlowat，使fd 8可读。
#. H的首个data初始化delayed-ACK engine并进入quickack，立即发送ACK。
#. parent持有C时反向ACK进入C.sk_backlog。
#. release_sock(C)处理ACK后清空original skb的重传身份。
#. write返回5不以peer application read为条件。
#. read开始前队列非空，因此blocking fd 8不睡眠。
#. read复制hello并移除receive skb；双方TCP连接保持ESTABLISHED。
#. quickack已完成，本次read cleanup不再发送ACK。
#. 下一批不得重新讲data delivery，应直接进入TCP active close。

下一任务
--------

::

   close(7)
   → fdtable removes F7 publication
   → final __fput enters tcp_close
   → C queues FIN at sequence C_ISN+6
   → FIN traverses IPv4 output and lo
   → H consumes FIN after receive queue is empty
   → H enters TCP_CLOSE_WAIT
   → accepted fd 8 becomes EOF-readable
   → ACK advances C toward TCP_FIN_WAIT2
   → later close(8) sends peer FIN
   → C enters TIME_WAIT and H completes LAST_ACK

开始前必须固定close到__fput的同步边界、FIN与ACK sequence、C/H state transition、fd 8 EOF callback、client orphan ownership、peer close与TIME_WAIT生命周期。

