项目状态
========

最后更新
--------

2026-07-14

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

最新三章：

#. ``LK-TCPCONNECT-173``：client connect怎样选择loopback路由、自动端口并进入TCP_SYN_SENT？
#. ``LK-TCPCONNECT-174``：tcp_connect怎样构造SYN并通过lo命中server listener？
#. ``LK-TCPCONNECT-175``：listener怎样创建request_sock并把SYN-ACK排入client backlog？

进度
----

当前已经完成175章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

固定场景
--------

::

   runtime relation       = continues chapters 170..172 TCP listener
   CPUs online            = CPU0 only
   network namespace      = N
   loopback device        = lo UP, MTU 65536
   loopback address       = 127.0.0.1/8
   server fd              = 6
   server endpoint        = 127.0.0.1:28080
   server state           = TCP_LISTEN
   listen backlog         = 8
   client fd              = 7
   client endpoint        = 127.0.0.1:40000
   remote endpoint        = 127.0.0.1:28080
   ip_local_port_range    = 32768..60999
   client ISN             = C_ISN 0x13572468
   server ISN             = S_ISN 0x24681357
   client timestamp       = C_TS0 0x10203040
   server timestamp       = S_TS0 0x50607080
   client/server wscale   = 7 / 7
   MSS                    = 65495
   timestamps/SACK/WS     = enabled
   TFO/ECN/MD5/AO/MPTCP   = disabled
   failures/races         = none

完整控制流
----------

::

   client socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
   → reuse AF_INET TCP creation path
   → publish blocking close-on-exec fd 7
   → CS.state=SS_UNCONNECTED; C.sk_state=TCP_CLOSE

   connect(7,127.0.0.1:28080)
   → __sys_connect copies sockaddr_in
   → inet_stream_connect locks C
   → tcp_v4_connect validates AF_INET destination
   → ip_route_connect selects RTN_LOCAL route and lo
   → route selects source address 127.0.0.1
   → tcp_set_state(C,TCP_SYN_SENT)
   → inet_hash_connect scans ephemeral range
   → fixed scenario chooses local port 40000
   → create CTB/CTB2 and set SOCK_CONNECT_BIND
   → insert client C into ehash
   → commit local/remote tuple and dst
   → secure sequence function yields C_ISN

   tcp_connect(C)
   → tcp_connect_init derives PMTU, MSS, receive window and scale
   → allocate original SYN skb CSYN
   → seq=C_ISN; end_seq=C_ISN+1
   → queue CSYN in retransmission tree
   → send clone XSYN through tcp_transmit_skb
   → ip_queue_xmit builds IPv4 header
   → dev_queue_xmit selects lo
   → loopback_xmit orphans clone and calls __netif_rx
   → CPU0 backlog raises NET_RX softirq
   → IPv4 local delivery enters tcp_v4_rcv
   → ehash direction does not match client C
   → exact-address listener lookup finds L

   tcp_v4_do_rcv(L,XSYN)
   → TCP_LISTEN branch calls tcp_v4_conn_request
   → no syncookie or queue overflow
   → inet_reqsk_alloc creates request R
   → R.state=TCP_NEW_SYN_RECV and holds listener reference
   → parse MSS/SACK/timestamp/window-scale options
   → R records C_ISN and rcv_nxt=C_ISN+1
   → fixed server sequence is S_ISN
   → inet_csk_reqsk_queue_hash_add inserts R into ehash
   → arm request retransmission timer
   → set rsk_refcnt to 3, then caller put leaves 2
   → request qlen/young become 1/1
   → tcp_v4_send_synack builds seq=S_ISN, ack=C_ISN+1
   → SYN-ACK traverses IPv4 output and lo
   → reverse ehash lookup finds client C
   → parent owns C, so tcp_add_backlog queues SYN-ACK

   return to client connect path
   → tcp_connect commits snd_nxt=C_ISN+1 and arms SYN timer
   → tcp_v4_connect returns 0
   → CS.state becomes SS_CONNECTING
   → inet_wait_for_connect installs wait entry CW
   → stop immediately before release_sock(C)

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 kernel process context；
* current syscall：blocking ``connect(7,127.0.0.1:28080)``；
* parent：``TASK_RUNNING``，尚未schedule；
* client socket user lock：由parent持有；
* connect wait entry ``CW``：已经加入 ``sk_sleep(C)``；
* server fd 6：open、blocking、close-on-exec；
* server ``L``：``TCP_LISTEN``；
* server endpoint：``127.0.0.1:28080``；
* server bind hash与listener lhash2：active；
* client fd 7：open、blocking、close-on-exec；
* client ``CS``：``SS_CONNECTING``；
* client ``C``：``TCP_SYN_SENT``；
* client tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* client bind/bind2 ownership：active，``SOCK_CONNECT_BIND`` set；
* client ehash：active；
* client dst：local route through ``lo``；
* client retransmission tree：contains original CSYN；
* client SYN retransmission timer：armed；
* client ``snd_una=C_ISN``、``snd_nxt=C_ISN+1``；
* client socket backlog：contains one SYN-ACK；
* request ``R``：``TCP_NEW_SYN_RECV``；
* request tuple：``127.0.0.1:28080 ← 127.0.0.1:40000``；
* request ehash：active；
* request timer：armed；
* request ``rsk_refcnt=2``；
* request qlen/young：1/1；
* accept queue：empty；
* full server child：none；
* final ACK：not sent；
* next runtime entry：``release_sock(C)``。

关键边界
--------

#. client创建复用第170章的对象创建路径，本章只新增fd 7与独立tcp_sock C。
#. ``ip_route_connect``先选择local route与source address，local port随后由``inet_hash_connect``确定。
#. source port 40000是固定随机状态下的结果，不是Linux API保证。
#. connect自动端口加入bind/bind2并设置``SOCK_CONNECT_BIND``，与用户显式bind锁不同。
#. client在SYN发出前已经加入ehash，供反向SYN-ACK查找。
#. original CSYN留在TCP retransmission tree；device层发送clone XSYN。
#. local route仍经过IP output、device output、``loopback_xmit``与NET_RX receive。
#. 单CPUloopback可以在``connect()``发送路径内嵌套运行NET_RX softirq。
#. SYN按目的地址和端口命中server的具体地址lhash2。
#. 普通SYN建立真实request R；syncookie分支不会保留相同对象。
#. ``TCP_NEW_SYN_RECV`` request不是完整的server child。
#. request在发送SYN-ACK前先进入ehash并启动timer。
#. request qlen为1时accept queue仍为空。
#. parent持有client socket lock时，SYN-ACK只能进入``C.sk_backlog``。
#. ``SS_CONNECTING``与``TCP_SYN_SENT``属于不同层，可以同时存在。
#. wait entry CW先安装，之后才释放socket lock，避免处理backlog时的wakeup丢失。
#. 第175章尚未完成握手，不允许提前写client ESTABLISHED、server child或connect返回。
#. 单章末尾只记录本章状态，不再加入“本批三章总结”。

下一任务
--------

::

   release_sock(C)
   → __release_sock drains SYN-ACK from C.sk_backlog
   → tcp_rcv_synsent_state_process validates ACK and options
   → client C enters TCP_ESTABLISHED
   → remove/ack original SYN retransmission state
   → send final ACK through lo
   → server ehash lookup finds request R
   → tcp_check_req creates full server child
   → child inherits listener bind ownership and tuple
   → replace request hash identity with child
   → child enters TCP_ESTABLISHED
   → add child to listener accept queue
   → state-change/data-ready wakeups become visible
   → wait_woken observes wake flag without necessarily scheduling
   → connect(7,...) returns 0

开始前必须固定``release_sock`` backlog顺序、client final ACK sequence、request引用删除、child bind继承与ehash替换、accept queue计数、wakeup flag以及parent是否真正调用scheduler。
