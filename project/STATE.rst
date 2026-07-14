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
   LK-TCPHANDSHAKE-176..LK-TCPHANDSHAKE-178

最新三章：

#. ``LK-TCPHANDSHAKE-176``：release_sock怎样处理SYN-ACK并让client发送最终ACK？
#. ``LK-TCPHANDSHAKE-177``：最终ACK怎样把request_sock替换成ESTABLISHED server child？
#. ``LK-TCPHANDSHAKE-178``：blocking connect为什么无需真正睡眠就返回0？

进度
----

当前已经完成178章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

   runtime relation       = continues chapters 170..175 TCP loopback active open
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
   client ISN             = C_ISN 0x13572468
   server ISN             = S_ISN 0x24681357
   client timestamp SYN   = C_TS0 0x10203040
   server timestamp       = S_TS0 0x50607080
   client final ACK TS    = C_TS1 > C_TS0
   client/server wscale   = 7 / 7
   MSS                    = 65495
   timestamps/SACK/WS     = enabled
   TFO/ECN/MD5/AO/MPTCP   = disabled
   defer accept           = disabled
   failures/races         = none
   connect scheduling     = none

本批完整控制流
--------------

::

   inet_wait_for_connect has installed CW
   → release_sock(C)
   → __release_sock detaches C.sk_backlog
   → sk_backlog_rcv(C,SYN-ACK)
   → tcp_v4_do_rcv
   → tcp_rcv_synsent_state_process
   → validate ACK=C_ISN+1
   → tcp_ack advances snd_una
   → remove original CSYN from retransmission tree
   → set rcv_nxt=S_ISN+1
   → apply MSS/SACK/timestamp/window-scale negotiation
   → tcp_finish_connect
   → C: TCP_SYN_SENT → TCP_ESTABLISHED
   → C.sk_state_change sets CW.WQ_FLAG_WOKEN
   → construct final ACK CACK
   → CACK seq=C_ISN+1, ack=S_ISN+1, ACK only
   → IPv4 output → dev_queue_xmit → loopback_xmit
   → queue CACK to CPU0 input backlog
   → rcu_read_unlock_bh runs pending NET_RX softirq

   tcp_v4_rcv(CACK)
   → ehash lookup finds TCP_NEW_SYN_RECV request R
   → tcp_check_req validates final ACK and receive window
   → tcp_v4_syn_recv_sock
   → tcp_create_openreq_child
   → inet_csk_clone_lock creates full child H
   → H starts in TCP_SYN_RECV
   → H tuple = 127.0.0.1:28080 ← 127.0.0.1:40000
   → H rcv_nxt=C_ISN+1
   → H snd_una=snd_nxt=write_seq=S_ISN+1
   → restore negotiated TCP options
   → __inet_inherit_port joins H to server bind/bind2 owners
   → inet_ehash_nolisten replaces R ehash identity with H
   → own_req=true
   → delete R request timer
   → request qlen/young 1/1 → 0/0
   → inet_csk_reqsk_queue_add reuses R as accept node
   → R.sk=H
   → accept head/tail=R/R
   → L.sk_ack_backlog 0 → 1
   → tcp_child_process feeds CACK to H
   → H: TCP_SYN_RECV → TCP_ESTABLISHED
   → L.sk_data_ready publishes accept readiness
   → NET_RX returns to client ACK output
   → finish SSYNACK backlog processing
   → C.sk_backlog.len=0
   → first release_sock releases C ownership

   wait_woken(CW,TASK_INTERRUPTIBLE,timeo)
   → sees WQ_FLAG_WOKEN
   → skips schedule_timeout
   → restores TASK_RUNNING and clears wake flag
   → lock_sock(C)
   → loop condition sees TCP_ESTABLISHED
   → remove CW from sk_sleep(C)
   → __inet_stream_connect sets CS.state=SS_CONNECTED
   → outer release_sock(C)
   → connect returns 0 to x86-64 userspace

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* last syscall/result：``connect(7,127.0.0.1:28080)=0``；
* parent：``TASK_RUNNING``；
* scheduler：本次connect wait没有调用 ``schedule_timeout``；
* wait entry ``CW``：已删除；
* ``CW.WQ_FLAG_WOKEN``：已清除；
* server fd 6：open、blocking、close-on-exec；
* server listener ``L``：``TCP_LISTEN``；
* server endpoint：``127.0.0.1:28080``；
* listener bind hash与lhash2：active；
* SYN request qlen/young：0/0；
* listener ``sk_ack_backlog=1``；
* accept queue：head/tail均为R；
* accept node ``R``：active， ``R.sk=H``；
* R的 ``TCP_NEW_SYN_RECV`` ehash身份：removed/replaced；
* R request timer：deleted；
* server child ``H``：``TCP_ESTABLISHED``；
* H tuple：``127.0.0.1:28080 ← 127.0.0.1:40000``；
* H established ehash：active；
* H bind/bind2 ownership：active；
* H ``snd_una=snd_nxt=S_ISN+1``；
* H ``rcv_nxt=C_ISN+1``；
* H ``sk_socket=NULL``；
* H sockfs inode/file/fd：none；
* client fd 7：open、blocking、close-on-exec；
* client ``CS``：``SS_CONNECTED``；
* client ``C``：``TCP_ESTABLISHED``；
* client tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* client bind/bind2 ownership：active，``SOCK_CONNECT_BIND`` set；
* client ehash：active；
* client dst：local route through ``lo``；
* client ``snd_una=snd_nxt=C_ISN+1``；
* client ``rcv_nxt=S_ISN+1``；
* client retransmission tree：empty；
* client socket backlog：empty；
* packet与CPU0 NET_RX backlog：empty；
* next runtime entry：``accept4(6,...,SOCK_CLOEXEC)``；
* next lowest free fd：8。

关键边界
--------

#. ``release_sock`` 先清空socket backlog，再释放socket用户ownership。
#. client SYN-ACK由parent process context通过 ``sk_backlog_rcv`` 消费。
#. ``tcp_ack`` 确认original SYN后消除其retransmission identity。
#. client sequence空间固定为 ``snd_una=snd_nxt=C_ISN+1`` 与 ``rcv_nxt=S_ISN+1``。
#. client ``TCP_ESTABLISHED`` 写入发生在socket API ``SS_CONNECTED`` 之前。
#. state-change wakeup通过 ``CW.WQ_FLAG_WOKEN`` 跨越 ``release_sock`` 与 ``wait_woken`` 的时序间隙。
#. final ACK通过 ``lo`` 重新进入CPU0 backlog，并可在 ``rcu_read_unlock_bh`` 时嵌套运行NET_RX。
#. final ACK按完整server方向四元组命中R。
#. R是轻量request；H是新分配的完整child。
#. child clone后先处于 ``TCP_SYN_RECV``，处理CACK后进入 ``TCP_ESTABLISHED``。
#. ``__inet_inherit_port`` 为H建立真实bind/bind2 owner关系。
#. ehash先从R切换到H，再把连接发布到accept queue。
#. SYN阶段qlen/young归零不代表accept queue为空。
#. 同一个R转为accept FIFO节点，保存 ``R.sk=H``，不能提前描述为释放。
#. H没有用户态socket/file/fd； ``accept4`` 才完成graft和fd发布。
#. listener ``sk_data_ready`` 发布连接可接受状态，本场景没有accept waiter。
#. ``wait_woken`` 看见提前设置的wake flag后不执行scheduler。
#. blocking API允许等待，不保证实际发生task switch。
#. ``connect()=0`` 与server尚未调用accept可以同时成立。
#. 下一批不得重新讲三次握手，应直接进入accept queue removal与fd 8发布。

下一任务
--------

::

   accept4(6,user_addr,user_addrlen,SOCK_CLOEXEC)
   → __sys_accept4_file resolves F6/S/L
   → tcp_accept checks non-empty accept queue
   → reqsk_queue_remove returns R and H
   → L.sk_ack_backlog 1 → 0
   → finish R accept-node lifetime
   → allocate accepted struct socket AS
   → inet_accept grafts H to AS
   → AS.state=SS_CONNECTED
   → create blocking close-on-exec sockfs file F8
   → reserve fd 8 and set close-on-exec fdtable bit
   → publish F8 with fd_install
   → copy peer sockaddr 127.0.0.1:40000
   → accept4 returns 8

开始前必须固定accept地址缓冲区、``SOCK_CLOEXEC``与blocking语义、queue removal时R/H引用、``sock_graft``写入H.sk_socket/sk_wq的位置、accepted socket file创建顺序、fd reserve/publish顺序与失败回滚边界。
