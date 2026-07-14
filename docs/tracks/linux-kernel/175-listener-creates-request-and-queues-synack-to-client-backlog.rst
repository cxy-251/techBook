第一百七十五章：listener怎样创建request_sock并把SYN-ACK排入client backlog？
=================================================================

上一章结束时，CPU0正在NET_RX softirq中处理client SYN。精确地址listener lookup已经找到server ``L``：

::

   client C
       local  = 127.0.0.1:40000
       remote = 127.0.0.1:28080
       state  = TCP_SYN_SENT
       ehash  = active

   server L
       local  = 127.0.0.1:28080
       state  = TCP_LISTEN
       lhash2 = active

   received SYN XSYN
       seq = C_ISN = 0x13572468
       ack = 0
       flags = SYN

   tcp_v4_rcv
   → tcp_v4_do_rcv(L, XSYN)       # 本章入口

parent仍处在 ``connect(7, ...)`` syscall中，并持有client socket的用户锁。listener没有用户线程持锁，request queue与accept queue仍为空。

本章追踪listener解析SYN、创建并哈希 ``request_sock R``、发送SYN-ACK，以及回环SYN-ACK为何不能立刻处理client状态，而是先排入 ``C.sk_backlog``。叙事停在通用connect层即将调用 ``release_sock(C)`` 的位置。

本章固定：

* network namespace仍为 ``N``，只有CPU0 online；
* server fd 6监听 ``127.0.0.1:28080``，backlog为8；
* client fd 7使用 ``127.0.0.1:40000``，处于 ``TCP_SYN_SENT``；
* client SYN的MSS为65495，支持SACK、timestamp和window scaling；
* client option固定为 ``C_TS0=0x10203040``、 ``C_WS=7``；
* server为本连接选择 ``S_ISN=0x24681357``、 ``S_TS0=0x50607080``、 ``S_WS=7``；
* server SYN-ACK同样通告MSS 65495，并回显 ``TSecr=C_TS0``；
* SYN queue未满，accept queue未满，不启用syncookie、TCP Fast Open、defer-accept、ECN、MD5、TCP-AO或MPTCP；
* route、allocation、checksum、security、netfilter和XFRM均成功；
* SYN-ACK通过同一个 ``lo`` 和CPU0 backlog返回；
* 本章结束时三次握手尚未完成，没有server child，也没有accept queue entry。

tcp_v4_do_rcv怎样进入TCP_LISTEN状态处理
--------------------------------------

``tcp_v4_do_rcv`` 先完成policy与checksum检查。因为：

::

   L.sk_state = TCP_LISTEN

它处理可能的syncookie child；固定场景没有cookie，因此仍使用listener ``L``，再调用：

::

   tcp_rcv_state_process(L, XSYN)

``TCP_LISTEN`` 分支验证：

::

   ACK = 0
   RST = 0
   SYN = 1
   FIN = 0

因此不会发送RST或丢弃。该分支在RCU read-side critical section和bottom-half-disabled区域内调用：

::

   L.icsk_af_ops->conn_request(L, XSYN)
   → tcp_v4_conn_request(L, XSYN)
   → tcp_conn_request(&tcp_request_sock_ops,
                      &tcp_request_sock_ipv4_ops,
                      L,
                      XSYN)

此时执行环境仍是CPU0 NET_RX softirq，不会睡眠；后续request分配使用 ``GFP_ATOMIC``。

为什么本章不用syncookie
----------------------

``tcp_conn_request`` 首先检查SYN queue与accept queue压力。固定：

::

   inet_csk_reqsk_queue_is_full(L) = false
   sk_acceptq_is_full(L)           = false
   tcp_syncookies                  = normal fallback policy

因此：

::

   want_cookie = false

server将真实分配并保存request对象，而不是只把状态编码进SYN-ACK sequence number。

inet_reqsk_alloc怎样建立R
------------------------

路径执行：

::

   inet_reqsk_alloc(&tcp_request_sock_ops,
                    L,
                    attach_listener=true)
   → request_sock R

``R`` 的实际分配尺寸由：

::

   tcp_request_sock_ops.obj_size
   = sizeof(struct tcp_request_sock)

决定。它包含 ``request_sock``、 ``inet_request_sock`` 与TCP request字段的嵌套视图，不是完整 ``struct tcp_sock``。

因为 ``attach_listener=true``，分配路径先取得listener reference：

::

   R.rsk_listener = L
   sock_hold(L)

随后初始化：

::

   R.rsk_ops       = tcp_request_sock_ops
   req_to_sk(R).sk_prot = tcp_prot
   R.saved_syn     = NULL
   R.syncookie     = 0
   R.num_timeout   = 0
   R.num_retrans   = 0
   R.sk            = NULL

   req_to_sk(R).sk_state  = TCP_NEW_SYN_RECV
   req_to_sk(R).sk_family = AF_INET
   req_to_sk(R).sk_net    = N

``TCP_NEW_SYN_RECV`` 是request对象参与ehash lookup时使用的轻量状态。它不表示完整server child已经进入 ``TCP_SYN_RECV``。

SYN options怎样写入request
-------------------------

``tcp_parse_options`` 从XSYN读取：

::

   peer MSS          = 65495
   SACK permitted    = true
   timestamp seen    = true
   peer TSval        = C_TS0
   peer window scale = C_WS = 7

``tcp_openreq_init`` 把client身份和receive sequence写入R：

::

   tcp_rsk(R).rcv_isn = C_ISN
   tcp_rsk(R).rcv_nxt = C_ISN + 1

   R.mss              = 65495
   R.ts_recent        = C_TS0

   inet_rsk(R).tstamp_ok = 1
   inet_rsk(R).sack_ok   = 1
   inet_rsk(R).wscale_ok = 1
   inet_rsk(R).snd_wscale = C_WS

   inet_rsk(R).ir_rmt_port = htons(40000)
   inet_rsk(R).ir_num      = 28080

这里的 ``snd_wscale`` 保存peer通告的scale，供未来server child解释client发送窗口。server自己通告给client的scale稍后写入 ``rcv_wscale``，本场景固定为 ``S_WS=7``。

IPv4 request怎样取得地址与返回route
----------------------------------

``tcp_v4_route_req`` 先调用：

::

   tcp_v4_init_req(R, L, XSYN)

写入：

::

   inet_rsk(R).ir_loc_addr = 127.0.0.1
   inet_rsk(R).ir_rmt_addr = 127.0.0.1
   inet_rsk(R).ir_iif      = 0

listener没有绑定特定device，且本场景没有L3 master，因此request的bound-device identity仍为0。输入skb来自 ``lo``，route request仍会得到local reverse route：

::

   source      = 127.0.0.1:28080
   destination = 127.0.0.1:40000
   dst.dev     = lo
   route type  = RTN_LOCAL

security connection-request hook允许该请求，route lookup成功。

server ISN与receive window怎样固定
---------------------------------

没有syncookie，也没有TIME_WAIT-derived ISN，因此：

::

   tcp_v4_init_seq_and_ts_off(N, XSYN)
   → S_ISN     = 0x24681357
   → S_TS_OFF  = fixed scenario offset

写入：

::

   tcp_rsk(R).snt_isn = S_ISN

``tcp_openreq_init_rwin`` 根据listener receive buffer、MSS和window-scaling策略选择初始窗口，并固定：

::

   inet_rsk(R).rcv_wscale = S_WS = 7
   R.rsk_rcv_wnd          = server initial receive window

SYN与SYN-ACK中的16-bit window字段本身不做scale；scale只声明后续segment怎样解释window。

request为什么先进入ehash再发送SYN-ACK
-----------------------------------

普通非cookie路径调用：

::

   inet_csk_reqsk_queue_hash_add(L, R)

内部先执行：

::

   inet_ehash_insert(req_to_sk(R), NULL, &found_dup)

request使用完整四元组：

::

   local  = 127.0.0.1:28080
   remote = 127.0.0.1:40000

因此它与反向方向的client C落入各自按方向计算的ehash identity。未来client最终ACK到达server时，established lookup会先命中 ``TCP_NEW_SYN_RECV`` 的R，而不必再次只靠listener端口查找。

插入成功后建立request retransmission timer：

::

   R.timeout = tcp_timeout_init(req_to_sk(R))
   timer_setup(&R.rsk_timer, reqsk_timer_handler, TIMER_PINNED)
   mod_timer(..., jiffies + R.timeout)

然后在发布完整字段后设置：

::

   R.rsk_refcnt = 3

这三个引用用于当前调用路径、ehash可查找身份与timer生命周期。 ``tcp_conn_request`` 结束时会放掉当前调用路径的reference，留下两个长期reference。

最后更新listener request accounting：

::

   request queue qlen : 0 → 1
   request young      : 0 → 1

这里的request queue是SYN阶段accounting与ehash/timer体系，不是 ``rskq_accept_head`` 所代表的已完成连接FIFO。

SYN-ACK header怎样由R生成
------------------------

R已经可查找后，路径调用：

::

   tcp_v4_send_synack(L,
                      dst,
                      flow,
                      R,
                      TCP_SYNACK_NORMAL,
                      XSYN)

``tcp_make_synack`` 构造发送skb ``SSYNACK``：

::

   source port = htons(28080)
   dest port   = htons(40000)

   seq     = S_ISN
   ack_seq = C_ISN + 1

   SYN = 1
   ACK = 1

固定options为：

::

   MSS            = 65495
   SACK permitted = yes
   Timestamp      = TSval S_TS0, TSecr C_TS0
   Window scale   = S_WS = 7

``ack_seq=C_ISN+1`` 明确确认client SYN消耗的一个sequence number。SYN-ACK自身也将消耗server sequence space中的一个位置，但当前仍只保存在R的 ``snt_isn`` 与重传状态中，没有完整server ``tcp_sock``。

SYN-ACK怎样再次经过lo
--------------------

IPv4 request send路径执行：

::

   __tcp_v4_send_check(SSYNACK,
                       127.0.0.1,
                       127.0.0.1)

   ip_build_and_send_pkt(SSYNACK,
                         L,
                         saddr=127.0.0.1,
                         daddr=127.0.0.1,
                         ...)

随后仍经过：

::

   ip_local_out
   → ip_output
   → dev_queue_xmit
   → loopback_xmit
   → __netif_rx
   → enqueue_to_backlog(CPU0)

没有物理IRQ或DMA。SYN-ACK被加入CPU0 backlog，并继续保持 ``NET_RX_SOFTIRQ`` pending。

``tcp_v4_send_synack`` 返回后， ``tcp_conn_request`` 对R执行：

::

   reqsk_put(R)

所以：

::

   R.rsk_refcnt : 3 → 2

R继续由ehash与timer保持；listener reference也继续由R持有。

当前net_rx_action为什么可以继续处理SYN-ACK
-----------------------------------------

CPU0当前本来就在 ``net_rx_action`` / backlog NAPI中处理XSYN。 ``loopback_xmit`` 把SSYNACK追加到同一CPU backlog后，只要quota与time budget未耗尽， ``process_backlog`` 可以在同一次softirq中继续取出它。

XSYN的listener处理完成后：

::

   tcp_conn_request → 0
   tcp_rcv_state_process consumes XSYN
   tcp_v4_do_rcv(L, XSYN) → 0

receive loop随后取得SSYNACK并再次进入：

::

   ip_rcv
   → ip_local_deliver
   → tcp_v4_rcv(SSYNACK)

SYN-ACK lookup为什么命中client C
-------------------------------

SSYNACK方向为：

::

   source      = 127.0.0.1:28080
   destination = 127.0.0.1:40000

``__inet_lookup_established`` 使用该方向的destination作为local endpoint，正好匹配上一章已插入ehash的client C：

::

   C local  = 127.0.0.1:40000
   C remote = 127.0.0.1:28080
   C state  = TCP_SYN_SENT

因此不再查listener，直接取得C的reference。

为什么SYN-ACK不能立刻推进client状态
---------------------------------

``tcp_v4_rcv`` 对非listener full socket执行：

::

   bh_lock_sock_nested(C)

但parent从进入 ``inet_stream_connect`` 起一直持有C的用户锁。此时：

::

   sock_owned_by_user(C) = true

softirq不能在用户拥有的socket上直接运行 ``tcp_v4_do_rcv(C, SSYNACK)``，否则会与connect路径并发修改同一TCP状态。它改为：

::

   tcp_add_backlog(C, SSYNACK)
   → sk_add_backlog(C, SSYNACK, limit)

固定memory accounting允许入队，因此：

::

   C.sk_backlog.head = SSYNACK
   C.sk_backlog.tail = SSYNACK
   C.sk_backlog.len  > 0

client仍保持：

::

   C.sk_state = TCP_SYN_SENT

SYN-ACK的TCP option、ACK与sequence尚未由 ``tcp_rcv_synsent_state_process`` 消费。它只是从CPU receive backlog转移到client socket backlog。

softirq返回后tcp_connect怎样完成发送侧提交
-----------------------------------------

SSYNACK排入C backlog后，NET_RX softirq结束，CPU0返回原来的SYN发送调用链。 ``tcp_transmit_skb`` 对client SYN成功返回， ``tcp_connect`` 随后提交：

::

   CTP.snd_nxt    = CTP.write_seq
                  = C_ISN + 1
   CTP.pushed_seq = C_ISN + 1

并增加active-open统计，设置SYN retransmission timer：

::

   tcp_reset_xmit_timer(C,
                        ICSK_TIME_RETRANS,
                        C.icsk_rto,
                        false)

原始CSYN仍在client retransmission tree；即使SYN-ACK已经到达socket backlog，connect路径尚未处理它，所以timer仍按 ``TCP_SYN_SENT`` 状态存在。

通用connect层何时写SS_CONNECTING
-------------------------------

控制流返回：

::

   tcp_connect(C)       → 0
   tcp_v4_connect(C)    → 0
   __inet_stream_connect

协议connect成功启动后，通用层才写：

::

   CS.state = SS_CONNECTING

此时两层状态为：

::

   CS.state   = SS_CONNECTING
   C.sk_state = TCP_SYN_SENT

blocking socket的send timeout不是0，因此通用层不会返回 ``-EINPROGRESS`` 给用户，而是进入等待连接完成的路径。

inet_wait_for_connect怎样先安装wait entry
----------------------------------------

``__inet_stream_connect`` 看到 ``TCP_SYN_SENT``，调用：

::

   inet_wait_for_connect(C, timeo, writebias=0)

它先建立wait entry ``CW``：

::

   DEFINE_WAIT_FUNC(CW, woken_wake_function)
   add_wait_queue(sk_sleep(C), &CW)

然后进入while循环。此刻检查仍看到：

::

   C.sk_state = TCP_SYN_SENT

下一条关键调用是：

::

   release_sock(C)

``release_sock`` 将释放用户锁，并同步处理刚才排入 ``C.sk_backlog`` 的SSYNACK。由于CW已经挂入socket wait queue，处理SYN-ACK时的state-change wakeup不会丢失。

本章停在 ``release_sock(C)`` 执行之前，不提前写client ESTABLISHED、最终ACK、server child或connect返回。

本章结束状态
------------

* current executor：parent；
* CPU/mode：CPU0，x86-64 kernel process context；
* current syscall：blocking ``connect(7,127.0.0.1:28080)``；
* parent state：``TASK_RUNNING``，尚未调用 ``wait_woken`` 或schedule；
* client socket lock：仍由parent持有；
* client wait entry ``CW``：已加入 ``sk_sleep(C)``；
* ``CS.state=SS_CONNECTING``；
* ``C.sk_state=TCP_SYN_SENT``；
* client tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* client bind/bind2 ownership与ehash：active；
* original CSYN：仍在client retransmission tree；
* client SYN retransmission timer：armed；
* ``CTP.snd_una=C_ISN``；
* ``CTP.snd_nxt=C_ISN+1``；
* client socket backlog：contains one SSYNACK；
* SSYNACK：``seq=S_ISN``、 ``ack=C_ISN+1``、 ``SYN|ACK``；
* server listener L：仍为 ``TCP_LISTEN``；
* request socket R：``TCP_NEW_SYN_RECV``，已在server-direction ehash；
* R tuple：``127.0.0.1:28080 ← 127.0.0.1:40000``；
* R request timer：armed；
* ``R.rsk_refcnt=2``；
* listener request qlen/young：1/1；
* listener accept queue：empty；
* full server child：none；
* next entry：``release_sock(C)`` 处理SSYNACK。

关键边界
--------

#. 普通SYN在listener端分配真实 ``tcp_request_sock``；syncookie路径不会保留同样的request对象。
#. request的 ``TCP_NEW_SYN_RECV`` 与完整child的 ``TCP_SYN_RECV`` 是不同对象阶段。
#. R保存client ISN、options、地址与端口，并持有listener reference。
#. request先进入ehash并启动timer，之后才发送SYN-ACK，避免最终ACK到达时没有可查对象。
#. ``rsk_refcnt=3`` 覆盖当前调用、ehash和timer；调用结束put后留下2。
#. SYN request qlen增加到1不等于accept queue已有child。
#. SYN-ACK按 ``S_ISN`` 发送，并确认 ``C_ISN+1``。
#. 同一CPU的loopback receive可以在一次NET_RX softirq中继续处理新排入的SYN-ACK。
#. SYN-ACK按反向四元组命中client C，而不是server listener。
#. parent持有client socket lock时，softirq只能把SYN-ACK排进C backlog。
#. ``SS_CONNECTING`` 在协议connect启动成功后才写入；TCP此时仍为 ``TCP_SYN_SENT``。
#. blocking connect先安装CW，再释放socket lock，避免state-change wakeup丢失。
#. 本章结束时parent尚未真正睡眠，三次握手也尚未完成。

下一入口
--------

下一章从：

::

   release_sock(C)
   → __release_sock(C)
   → tcp_v4_do_rcv(C, SSYNACK)
   → tcp_rcv_synsent_state_process

开始。SYN-ACK将使client进入 ``TCP_ESTABLISHED`` 并发送最终ACK；最终ACK回到server后，R才会被替换为完整child并加入accept queue。随后 ``wait_woken`` 可立即观察已经发生的wakeup，blocking ``connect()`` 才返回0。

资料
----

* `Linux 7.2-rc1 net/ipv4/tcp_input.c：TCP_LISTEN状态、tcp_conn_request与request初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_input.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_connection_sock.c：inet_reqsk_alloc、request ehash/timer/refcount与queue accounting <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_connection_sock.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_ipv4.c：tcp_v4_conn_request、tcp_v4_send_synack与client receive backlog分派 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_ipv4.c>`_
* `Linux 7.2-rc1 net/ipv4/af_inet.c：SS_CONNECTING、inet_wait_for_connect与wait entry顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
