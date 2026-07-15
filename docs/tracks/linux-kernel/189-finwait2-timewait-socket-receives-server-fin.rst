第一百八十九章：FIN_WAIT2 TW怎样接收server FIN并发送最终ACK？
========================================================

上一章停在server FIN已经加入CPU0输入backlog，而H的发送路径尚未重新启用bottom halves的位置：

::

   parent / CPU0 / close(8) kernel call stack

   server H
       state       = TCP_LAST_ACK
       snd_una     = S_ISN + 1
       snd_nxt     = S_ISN + 2
       write_seq   = S_ISN + 2
       rcv_nxt     = C_ISN + 7
       retrans q   = [HFIN-original]
       owned       = by parent

   HFIN clone
       seq         = S_ISN + 1
       end_seq     = S_ISN + 2
       ack_seq     = C_ISN + 7
       flags       = FIN | ACK
       queued      = CPU0 input backlog

   client TW
       tw_state    = TCP_TIME_WAIT
       tw_substate = TCP_FIN_WAIT2
       tw_rcv_nxt  = S_ISN + 1
       tw_snd_nxt  = C_ISN + 7

本章从：

::

   rcu_read_unlock_bh()

开始。HFIN会按client方向四元组命中轻量TW。 ``tcp_timewait_state_process`` 不会把它交给已经销毁的完整C，而是在 ``TCP_FIN_WAIT2`` 子状态下验证sequence、window、timestamp与FIN边界，把TW推进到真正 ``TCP_TIME_WAIT``，再由IPv4 time-wait ACK路径构造最终纯ACK。最终ACK回到server H时，parent仍持有H的用户锁，因此它只能进入 ``H.sk_backlog``。

本章固定条件
------------

* 只有CPU0 online，NET_RX嵌套在parent的close调用栈上执行；
* HFIN checksum、timestamp、window位置与FIN sequence均有效；
* ``HFIN.seq=S_ISN+1``、 ``HFIN.end_seq=S_ISN+2``；
* TW仍在ehash与death-row timer中，分配和引用均有效；
* TW没有PAWS拒绝、reuse冲突或并发timer到期；
* parent仍持有H的socket user ownership；
* 没有RST、SYN、新payload、丢包、filter拒绝或内存失败；
* TW发送的最终ACK固定记为 ``TACK``。

bottom halves重新启用时怎样处理HFIN
----------------------------------

H的 ``__dev_queue_xmit`` 执行：

::

   rcu_read_unlock_bh()

上一章的 ``loopback_xmit`` 已经把HFIN排入CPU0 input backlog并标记 ``NET_RX_SOFTIRQ`` pending。于是内核可以在返回 ``tcp_send_fin(H)`` 前运行：

::

   NET_RX_SOFTIRQ
   → net_rx_action
   → process_backlog
   → __netif_receive_skb
   → ip_rcv
   → ip_local_deliver
   → tcp_v4_rcv(HFIN)

执行环境暂时是CPU0 softirq context；parent没有离开runqueue，也没有发生task切换。

client方向lookup为什么返回TW
--------------------------

HFIN四元组为：

::

   source      = 127.0.0.1:28080
   destination = 127.0.0.1:40000

完整client C已经在第187章退出ehash。 ``__inet_lookup_skb`` 现在返回：

::

   TW tuple       = 127.0.0.1:40000 → 127.0.0.1:28080
   TW.tw_state    = TCP_TIME_WAIT
   TW.tw_substate = TCP_FIN_WAIT2

``tw_state`` 与普通 ``struct sock`` 的state位于兼容的common布局中，所以 ``tcp_v4_rcv`` 看到：

::

   sk->sk_state == TCP_TIME_WAIT

立即跳到：

::

   do_time_wait

它不会进入full socket的 ``bh_lock_sock``、 ``tcp_v4_do_rcv`` 或 ``tcp_rcv_state_process``。TW没有用户socket，也不存在用户task持有它的情况。

do_time_wait先做哪些检查
----------------------

time-wait专用分支仍执行必要的入站检查：

::

   xfrm4_policy_check(NULL, XFRM_POLICY_IN, HFIN)
   tcp_v4_fill_cb(HFIN)
   tcp_checksum_complete(HFIN)

本场景全部通过，随后调用：

::

   tcp_timewait_state_process(TW, HFIN, tcp_hdr(HFIN), ...)

这里传入的是轻量 ``inet_timewait_sock``，不是曾经的client ``tcp_sock C``。函数只能依赖TW保留的四元组、receive window、sequence与timestamp等最小状态。

为什么tw_state已经TIME_WAIT却还要看substate
-----------------------------------------

TW的两个字段承担不同角色：

::

   TW.tw_state    = TCP_TIME_WAIT
   TW.tw_substate = TCP_FIN_WAIT2

``tw_state`` 表示对象由time-wait哈希与timer基础设施管理。 ``tw_substate`` 表示TCP协议尚未收到peer FIN。

因此 ``tcp_timewait_state_process`` 首先检查：

::

   READ_ONCE(TW.tw_substate) == TCP_FIN_WAIT2

条件成立，进入专门的FIN-WAIT-2轻量状态机。它需要区分合法peer FIN、重复ACK、越窗segment、新data与RST，而不能把所有packet都按最终TIME_WAIT处理。

timestamp与window为什么通过
--------------------------

HFIN携带协商后的timestamp：

::

   TSval = S_TS3
   TSecr = C_TS2

TW保存了先前从完整C复制并更新的timestamp状态。固定场景没有PAWS回退，所以：

::

   paws_reject = false

sequence window检查使用：

::

   HFIN.seq     = S_ISN + 1
   HFIN.end_seq = S_ISN + 2
   TW.tw_rcv_nxt = S_ISN + 1

HFIN从下一个期望sequence开始，FIN只占用一个sequence number，并落在TW保存的receive window内。路径不会发送out-of-window ACK，也不会丢弃packet。

为什么它不是duplicate ACK
------------------------

FIN_WAIT2轻量状态机会把以下情况作为不推进状态的重复ACK处理：

::

   ACK flag absent
   or end_seq does not advance beyond tw_rcv_nxt
   or end_seq == seq

HFIN满足：

::

   ACK flag present
   S_ISN + 2 > S_ISN + 1
   end_seq != seq

虽然payload长度为0，FIN让 ``end_seq`` 比 ``seq`` 大1。因此HFIN不是零sequence长度的纯ACK，状态机继续检查它是否是期望的peer FIN。

FIN边界为什么必须正好加一
-------------------------

轻量FIN_WAIT2对象已经失去完整receive queue，不能接收close之后的新应用data。代码要求：

::

   HFIN.fin = 1
   HFIN.end_seq == TW.tw_rcv_nxt + 1

本场景：

::

   S_ISN + 2 == (S_ISN + 1) + 1

条件成立。若packet携带新payload或FIN不在精确下一个sequence，路径会返回RST语义，而不是尝试为一个已经关闭的client恢复receive buffer。

TW怎样进入真正TCP_TIME_WAIT
--------------------------

合法HFIN触发：

::

   WRITE_ONCE(TW.tw_substate, TCP_TIME_WAIT)

现在：

::

   TW.tw_state    = TCP_TIME_WAIT
   TW.tw_substate = TCP_TIME_WAIT

两层状态终于一致。随后：

::

   twsk_rcv_nxt_update(TW, HFIN.end_seq, old_rcv_nxt)

把：

::

   TW.tw_rcv_nxt : S_ISN + 1 → S_ISN + 2

这表示client TCP已经接收server FIN占用的sequence number。

timestamp状态也更新为HFIN的 ``S_TS3``，并记录真正进入TIME_WAIT的时间戳。TW不建立receive skb，也没有 ``copied_seq``；client应用fd 7早已关闭，无需再向userspace暴露EOF。

为什么timer要从现在重新计60秒
-----------------------------

在FIN_WAIT2子状态中，先前timer防止peer永远不发送FIN。收到合法HFIN后，路径调用：

::

   inet_twsk_reschedule(TW, TCP_TIMEWAIT_LEN)

固定：

::

   TCP_TIMEWAIT_LEN = 60 * HZ

timer从真正收到peer FIN的当前时刻重新启动。这个阶段的目的包括让可能重传的peer FIN仍能命中TW并获得ACK，以及避免旧重复segment过早与未来同四元组连接混淆。

``tcp_timewait_state_process`` 最后返回：

::

   TCP_TW_ACK

表示IPv4层必须为HFIN发送ACK。

tcp_v4_timewait_ack怎样构造最终ACK
--------------------------------

``tcp_v4_rcv`` 的time-wait switch进入：

::

   tcp_v4_timewait_ack(TW, HFIN, TCP_TW_ACK)

它从TW读取：

::

   tcptw->tw_snd_nxt = C_ISN + 7
   tcptw->tw_rcv_nxt = S_ISN + 2

然后调用：

::

   tcp_v4_send_ack(...,
                   seq=C_ISN+7,
                   ack=S_ISN+2,
                   ...)

构造最终ACK ``TACK``：

::

   source      = 127.0.0.1:40000
   destination = 127.0.0.1:28080

   seq         = C_ISN + 7
   ack_seq     = S_ISN + 2
   flags       = ACK
   payload     = 0

   Timestamp   = current TW TSval, TSecr S_TS3

TACK确认HFIN占用的server sequence number。纯ACK不占用client sequence，也不需要retransmission tree。

为什么发送ACK不需要完整C
-----------------------

完整C已经销毁，TW也没有普通TCP send queue。 ``tcp_v4_send_ack`` 使用CPU0的per-CPU IPv4 TCP control socket和入站HFIN提供的反向地址信息，通过：

::

   ip_send_unicast_reply

发送TACK。TW只提供sequence、window、timestamp、mark、priority与绑定设备等必要字段。

所以time-wait对象足以完成可靠关闭中的最后ACK响应；保留完整 ``tcp_sock``、file或fd会浪费更多资源。

TACK怎样再次经过lo
------------------

``ip_send_unicast_reply`` 为反向本地路由建立IPv4输出，最终进入：

::

   dev_queue_xmit
   → __dev_queue_xmit
   → loopback_xmit(TACK, lo)
   → __netif_rx(TACK)

TACK加入CPU0 input backlog。当前NET_RX softirq仍在处理HFIN；固定budget足够，所以 ``process_backlog`` 在同一轮继续处理TACK：

::

   ip_rcv
   → ip_local_deliver
   → tcp_v4_rcv(TACK)

server方向ehash返回完整H：

::

   H.sk_state = TCP_LAST_ACK

为什么TACK只能进入H backlog
--------------------------

parent仍在 ``tcp_close(H)`` 中持有H的user ownership：

::

   sock_owned_by_user(H) = true

因此 ``tcp_v4_rcv`` 不直接运行H的LAST_ACK状态机，而调用：

::

   tcp_add_backlog(H, TACK)

结果：

::

   H.sk_backlog = [TACK]

此时 ``H.snd_una`` 仍为 ``S_ISN+1``， ``HFIN-original`` 仍在retransmission tree。TACK只有在parent稍后通过 ``__release_sock(H)`` 主动处理后，才会确认server FIN并结束LAST_ACK。

time-wait引用为什么可以释放
--------------------------

``tcp_v4_timewait_ack`` 发送完成后调用：

::

   inet_twsk_put(TW)

这只放掉本次ehash lookup取得的临时引用。TW仍由ehash、bind结构和新启动的60秒timer保持，不会在此处消失。

softirq随后返回原来的server FIN发送路径：

::

   NET_RX_SOFTIRQ returns
   → rcu_read_unlock_bh returns
   → __dev_queue_xmit(HFIN) continues
   → tcp_send_fin(H) continues

本章结束状态
------------

* current executor：parent调用栈上刚完成CPU0 NET_RX softirq；
* task schedule：没有发生；
* fd 8：已从fdtable撤销，close系统调用尚未返回；
* ``H.sk_state=TCP_LAST_ACK``；
* H socket ownership：仍由parent持有；
* ``HTP.snd_una=S_ISN+1``；
* ``HTP.snd_nxt=HTP.write_seq=S_ISN+2``；
* HFIN original：仍在H retransmission tree；
* HFIN receive clone：已由TW消费；
* ``TW.tw_state=TCP_TIME_WAIT``；
* ``TW.tw_substate=TCP_TIME_WAIT``；
* ``TW.tw_rcv_nxt=S_ISN+2``；
* ``TW.tw_snd_nxt=C_ISN+7``；
* TW timer：从HFIN到达时重新启动60秒；
* TACK：已加入 ``H.sk_backlog``；
* ``TACK.seq=C_ISN+7``、 ``TACK.ack_seq=S_ISN+2``；
* network packet backlog：empty；
* next entry： ``tcp_send_fin(H)`` 返回， ``__tcp_close`` 进入zero-timeout收尾并处理H backlog。

关键边界
--------

#. client完整C已经销毁；HFIN按四元组命中轻量TW。
#. ``tw_state=TCP_TIME_WAIT`` 标识对象类型， ``tw_substate=TCP_FIN_WAIT2`` 标识仍在等待peer FIN。
#. time-wait接收分支不进入full socket用户锁与receive queue路径。
#. 合法HFIN必须在window内、通过PAWS，并精确覆盖 ``tw_rcv_nxt..tw_rcv_nxt+1``。
#. FIN payload长度为0，sequence长度为1，所以不会被当作duplicate pure ACK。
#. FIN_WAIT2轻量对象不接收新的应用data；异常新data会触发RST语义。
#. 收到HFIN后 ``tw_substate`` 才进入真正 ``TCP_TIME_WAIT``。
#. ``tw_rcv_nxt`` 推进到 ``S_ISN+2``，TW不建立receive skb或copied_seq。
#. 真正TIME_WAIT timer从peer FIN到达时重新计60秒。
#. TACK由per-CPU control socket发送，不需要恢复完整client C。
#. TACK是 ``seq=C_ISN+7``、 ``ack=S_ISN+2`` 的纯ACK。
#. parent持有H时，TACK只能进入 ``H.sk_backlog``，LAST_ACK尚未结束。

下一入口
--------

下一章从server FIN发送返回后继续：

::

   tcp_send_fin(H) returns
   → sk_stream_wait_close(H, timeout=0)
   → sock_orphan(H)
   → __release_sock(H)
   → sk_backlog_rcv(H, TACK)

TACK会确认 ``S_ISN+2``，清除HFIN original。 ``TCP_LAST_ACK`` 分支随后调用 ``tcp_done(H)``，H进入 ``TCP_CLOSE``；close路径释放accepted socket、file与sockfs inode，并让 ``close(8)`` 返回0。

资料
----

* `Linux 7.2-rc1 net/core/dev.c：NET_RX softirq与process_backlog <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/dev.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_ipv4.c：do_time_wait与tcp_v4_timewait_ack <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_ipv4.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_minisocks.c：FIN_WAIT2轻量状态机 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_minisocks.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_timewait_sock.c：time-wait timer重新调度 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_timewait_sock.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_output.c：time-wait ACK的TCP输出辅助路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_output.c>`_
* `Linux 7.2-rc1 net/core/sock.c：H用户锁与tcp_add_backlog <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_
* `Linux 7.2-rc1 drivers/net/loopback.c：最终ACK的loopback发送 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/net/loopback.c>`_
