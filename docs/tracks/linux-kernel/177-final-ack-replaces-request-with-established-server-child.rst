第一百七十七章：最终ACK怎样把request_sock替换成ESTABLISHED server child？
==================================================================

上一章停在client最终ACK已经由 ``loopback_xmit`` 放入CPU0输入backlog，而 ``__dev_queue_xmit`` 尚未重新启用bottom halves的位置：

::

   client C
       state       = TCP_ESTABLISHED
       local       = 127.0.0.1:40000
       remote      = 127.0.0.1:28080
       snd_una     = C_ISN + 1
       rcv_nxt     = S_ISN + 1

   final ACK CACK
       seq         = C_ISN + 1
       ack_seq     = S_ISN + 1
       flags       = ACK
       queued      = CPU0 input backlog

   server request R
       state       = TCP_NEW_SYN_RECV
       local       = 127.0.0.1:28080
       remote      = 127.0.0.1:40000
       ehash       = active
       timer       = armed

本章从：

::

   rcu_read_unlock_bh()

开始。它允许pending ``NET_RX_SOFTIRQ`` 在CPU0立即运行。最终ACK将命中R，创建完整server child ``H``，把ehash中的request identity替换为H，停止request timer、清除SYN阶段计数，再把同一个R作为accept FIFO节点保存 ``R.sk=H``。最后H处理CACK并进入 ``TCP_ESTABLISHED``。

本章固定没有reuseport迁移、syncookie、defer-accept、accept queue overflow、allocation失败或并发ACK竞态。

bottom halves重新启用时为什么立即进入NET_RX
------------------------------------------

``__dev_queue_xmit`` 的output路径结束时执行：

::

   rcu_read_unlock_bh()

之前 ``loopback_xmit`` 已经调用 ``__netif_rx(CACK)``，并为CPU0 backlog NAPI标记 ``NET_RX_SOFTIRQ`` pending。当前只有CPU0 online，bottom halves重新启用后，内核可以在返回 ``tcp_send_ack`` 之前运行：

::

   NET_RX_SOFTIRQ
   → net_rx_action
   → process_backlog
   → __netif_receive_skb
   → ip_rcv
   → ip_local_deliver
   → tcp_v4_rcv(CACK)

这仍是parent的内核调用栈上嵌套的softirq执行，不涉及task切换。

server方向ehash为什么先找到R
---------------------------

CACK四元组为：

::

   source      = 127.0.0.1:40000
   destination = 127.0.0.1:28080

``tcp_v4_rcv`` 调用：

::

   __inet_lookup_skb(...,
                     source=40000,
                     dest=28080)

server方向ehash中当前公开的是：

::

   req_to_sk(R).sk_state = TCP_NEW_SYN_RECV

所以lookup先返回R，而不是listener L。listener只负责端口级和地址级监听查找；完成SYN-ACK后，具体四元组已经由request接管。

lookup临时取得R的引用，随后进入专用分支：

::

   if (sk->sk_state == TCP_NEW_SYN_RECV) {
       req = inet_reqsk(sk)
       sk  = req->rsk_listener
   }

本场景 ``R.rsk_listener=L``，listener仍是 ``TCP_LISTEN``。路径额外持有L，完成policy、checksum与filter检查，然后调用：

::

   tcp_check_req(L, CACK, R, fastopen=false, ...)

tcp_check_req怎样验证第三次握手ACK
--------------------------------

CACK首先通过ACK sequence验证：

::

   CACK.ack_seq = S_ISN + 1
   tcp_rsk(R).snt_isn + 1 = S_ISN + 1

两者相等，所以它确认server SYN-ACK消耗的一个sequence number。

receive sequence也有效：

::

   CACK.seq = C_ISN + 1
   tcp_rsk(R).rcv_nxt = C_ISN + 1

CACK没有payload， ``end_seq=seq``，位于R记录的receive window内。它没有RST或SYN，只带ACK。

本场景：

::

   rskq_defer_accept = 0

因此不会因为“只有ACK没有data”而延迟创建child。所有检查通过后， ``tcp_check_req`` 进入：

::

   child = L.icsk_af_ops->syn_recv_sock(...)
         → tcp_v4_syn_recv_sock(L, CACK, R, ...)

为什么child不是在原request上扩容
-------------------------------

``request_sock`` 是SYN阶段的紧凑对象，尺寸和字段均不同于完整 ``tcp_sock``。内核不会把R原地扩展，而是分配新的完整socket对象 ``H``：

::

   tcp_create_openreq_child(L, R, CACK)
   → inet_csk_clone_lock(L, R, GFP_ATOMIC)
   → H

``H`` 从listener默认配置克隆，但立即重建连接专属字段。它没有用户态 ``struct socket``、sockfs file或fd：

::

   H.sk_socket = NULL
   H.sk_wq     = NULL

所以此刻“建立了server child”不等于 ``accept()`` 已经发布新fd。

inet_csk_clone_lock怎样建立child身份
-----------------------------------

clone路径先清除listener专属的bind指针副本：

::

   H.icsk_bind_hash  = NULL
   H.icsk_bind2_hash = NULL

随后从R复制四元组：

::

   H.local address  = inet_rsk(R).ir_loc_addr = 127.0.0.1
   H.local port     = inet_rsk(R).ir_num      = 28080
   H.remote address = inet_rsk(R).ir_rmt_addr = 127.0.0.1
   H.remote port    = inet_rsk(R).ir_rmt_port = 40000

并设置：

::

   H.sk_state = TCP_SYN_RECV

listener具有 ``SOCK_RCU_FREE``，child不继承该listener销毁语义：

::

   sock_reset_flag(H, SOCK_RCU_FREE)

child自己的accept queue字段被清零，防止把listener queue错误复制给普通连接。

tcp_create_openreq_child怎样恢复sequence状态
-------------------------------------------

R保存了两端ISN。child据此建立完整TCP状态：

::

   HTP.rcv_nxt    = C_ISN + 1
   HTP.rcv_wup    = C_ISN + 1
   HTP.copied_seq = C_ISN + 1

   HTP.snd_una    = S_ISN + 1
   HTP.snd_nxt    = S_ISN + 1
   HTP.write_seq  = S_ISN + 1
   HTP.pushed_seq = S_ISN + 1

这表示最终ACK已经确认server SYN-ACK；child没有未确认的SYN sequence。

R中保存的MSS、SACK、timestamp、window-scale、receive window与初始路由相关状态也复制到H。固定：

::

   HTP.rx_opt.tstamp_ok = 1
   HTP.rx_opt.sack_ok   = 1
   snd_wscale/rcv_wscale = 7/7
   HTP.rx_opt.ts_recent = C_TS1

``tcp_create_openreq_child`` 最终增加passive-open统计，但H此时仍处于 ``TCP_SYN_RECV``，并且内部socket lock保持锁定，等待CACK再次进入完整状态机。

child怎样继承server端口所有权
----------------------------

``tcp_v4_syn_recv_sock`` 为H取得返回client的local route并设置capabilities，随后调用：

::

   __inet_inherit_port(L, H)

listener L已经拥有：

::

   bind bucket  TB  for port 28080
   bind2 bucket TB2 for 127.0.0.1:28080

H的local port和local address与listener一致，因此复用同一TB/TB2，并通过：

::

   inet_bind_hash(H, TB, TB2, 28080)

把H加入TB2 owners。H拥有自己的bind节点；它不是借用一个未记录的listener字段。

这里不会把H加入listener lhash2。H是具体四元组连接，只参与established ehash。

inet_ehash_nolisten怎样替换R
---------------------------

接着执行：

::

   inet_ehash_nolisten(H, req_to_sk(R), &found_dup_sk)

第二个参数明确指定要被替换的request identity。固定没有重复child与竞争，返回：

::

   own_req = true

效果是：

::

   before:
       server-direction ehash → req_to_sk(R), TCP_NEW_SYN_RECV

   after:
       server-direction ehash → H, TCP_SYN_RECV

R不再承担四元组lookup身份。后续相同四元组packet会找到H。

这个替换必须发生在accept queue入队之前。否则新packet可能仍找到R，或在child尚未可查时落回listener路径。

request timer与SYN阶段计数怎样拆除
--------------------------------

``tcp_check_req`` 随后进入：

::

   inet_csk_complete_hashdance(L, H, R, own_req=true)

先调用：

::

   inet_csk_reqsk_queue_drop(R.rsk_listener, R)

由于ehash identity已经被H替换，核心任务是同步删除R的request retransmission timer及其timer reference。随后：

::

   reqsk_queue_removed(&L.icsk_accept_queue, R)

把SYN阶段accounting更新为：

::

   request qlen  : 1 → 0
   request young : 1 → 0

注意这里名称仍是 ``icsk_accept_queue``，其中同时包含SYN阶段计数与完成连接FIFO；两个概念必须分开观察。

R为什么继续存在于accept queue
----------------------------

hashdance不会马上释放R。它调用：

::

   inet_csk_reqsk_queue_add(L, R, H)

在 ``rskq_lock`` 下写入：

::

   R.sk      = H
   R.dl_next = NULL

   rskq_accept_head = R
   rskq_accept_tail = R

并执行：

::

   sk_acceptq_added(L)

所以：

::

   L.sk_ack_backlog : 0 → 1

这里的R已经不再是ehash中的 ``TCP_NEW_SYN_RECV`` endpoint，而是accept FIFO的包装节点。它把listener的完成连接队列链接到完整child H。R会在未来 ``accept()`` 从队列移除时再结束这一用途。

因此本章结束后同时成立：

::

   SYN request qlen = 0
   accept backlog   = 1

二者不是矛盾。

tcp_child_process怎样让H进入ESTABLISHED
--------------------------------------

``tcp_v4_rcv`` 得到H后调用：

::

   tcp_child_process(L, H, CACK)

H的socket lock仍由clone路径持有，初始状态是：

::

   H.sk_state = TCP_SYN_RECV

因为没有用户owner，路径直接执行：

::

   tcp_rcv_state_process(H, CACK)

ACK检查再次在完整child上运行。它确认：

::

   CACK.ack_seq = HTP.snd_nxt = S_ISN + 1

没有Fast Open request，所以初始化passive-established transfer状态，然后：

::

   tcp_set_state(H, TCP_ESTABLISHED)

更新后的关键sequence为：

::

   HTP.snd_una = S_ISN + 1
   HTP.snd_nxt = S_ISN + 1
   HTP.rcv_nxt = C_ISN + 1

H没有 ``struct socket`` 和用户wait queue，因此H自己的 ``sk_state_change`` 不会唤醒一个尚不存在的accept fd。

listener为什么收到data_ready
----------------------------

``tcp_child_process`` 保存了进入前状态：

::

   state = TCP_SYN_RECV

处理后检测到：

::

   H.sk_state = TCP_ESTABLISHED
   H.sk_state != state

于是调用：

::

   L.sk_data_ready(L)

这让listener的poll/accept wait queue观察到新连接，并支持SIGIO语义。本场景没有另一个task阻塞在 ``accept()``，所以没有新的task被唤醒；readiness只被记录为可观察状态。

最后：

::

   bh_unlock_sock(H)

释放child内部lock。 ``tcp_v4_rcv`` 放掉临时child与listener引用并返回。

softirq返回到哪里
----------------

CPU0 ``NET_RX_SOFTIRQ`` 处理完CACK后返回被打断的output路径：

::

   __dev_queue_xmit
   → tcp_send_ack
   → tcp_rcv_synsent_state_process
   → tcp_v4_do_rcv(C, SSYNACK)
   → __release_sock(C)

本章停在softirq完成、即将继续这个返回链的位置。client connect等待逻辑仍未执行 ``wait_woken``。

本章结束状态
------------

* current executor：parent的调用栈上刚完成CPU0 NET_RX softirq；
* task schedule：没有发生；
* client ``C``：``TCP_ESTABLISHED``；
* client ``CS``：仍为 ``SS_CONNECTING``；
* ``CW.flags``：包含 ``WQ_FLAG_WOKEN``；
* client original SYN：已确认，不在retransmission tree；
* final ACK CACK：已被server消费；
* server listener ``L``：``TCP_LISTEN``；
* server child ``H``：完整 ``tcp_sock``， ``TCP_ESTABLISHED``；
* H tuple：``127.0.0.1:28080 ← 127.0.0.1:40000``；
* H established ehash：active；
* H bind/bind2 ownership：继承到listener的28080地址端口bucket；
* H ``sk_socket=NULL``，尚无sockfs file与fd；
* R ehash identity：removed/replaced；
* R request timer：deleted；
* request qlen/young：0/0；
* R accept-node：active， ``R.sk=H``；
* accept queue head/tail：R/R；
* ``L.sk_ack_backlog=1``；
* listener readiness：已通过 ``L.sk_data_ready`` 发布；
* next entry：返回 ``tcp_send_ack``，继续完成 ``__release_sock(C)`` 与 ``wait_woken``。

关键边界
--------

#. 最终ACK先通过server方向ehash找到 ``TCP_NEW_SYN_RECV`` request，不重新走listener端口查找。
#. request验证ACK sequence、receive sequence与window后才允许创建child。
#. 完整child是新分配的 ``tcp_sock``，不是在R上原地扩容。
#. child从listener克隆默认配置，从R恢复四元组、sequence和协商options。
#. child没有 ``struct socket``、file或fd；只有accept才会把它graft到用户可见socket。
#. ``__inet_inherit_port`` 给child建立真实bind/bind2 owner节点。
#. ``inet_ehash_nolisten`` 先用H替换R的ehash身份，再进行queue转换。
#. SYN阶段qlen归零与accept backlog增加是两个独立accounting变化。
#. R没有立刻释放；它转为accept FIFO节点并保存 ``R.sk=H``。
#. H处理同一个final ACK后才从 ``TCP_SYN_RECV`` 进入 ``TCP_ESTABLISHED``。
#. listener ``sk_data_ready`` 发布accept readiness；本场景没有accept waiter需要调度。
#. client的blocking connect仍未返回， ``CS.state`` 仍为 ``SS_CONNECTING``。

下一入口
--------

下一章从softirq返回后的client调用栈继续：

::

   tcp_send_ack returns
   → tcp_rcv_synsent_state_process returns
   → __release_sock(C) clears backlog
   → release_sock(C) releases ownership
   → wait_woken(CW, TASK_INTERRUPTIBLE, timeo)

``CW.WQ_FLAG_WOKEN`` 已经设置，所以parent无需真正进入scheduler即可完成blocking connect。

资料
----

* `Linux 7.2-rc1 net/ipv4/tcp_ipv4.c：TCP_NEW_SYN_RECV lookup与tcp_v4_syn_recv_sock <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_ipv4.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_minisocks.c：tcp_check_req、child创建与tcp_child_process <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_minisocks.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_connection_sock.c：clone、hashdance与accept queue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_connection_sock.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_hashtables.c：child端口继承与ehash <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_hashtables.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_input.c：TCP_SYN_RECV到TCP_ESTABLISHED <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_input.c>`_
