第一百七十六章：release_sock怎样处理SYN-ACK并让client发送最终ACK？
=============================================================

上一章停在blocking ``connect(7, 127.0.0.1:28080)`` 的第一次等待循环中。wait entry ``CW`` 已经挂到client socket的睡眠队列，parent仍持有client ``C`` 的用户锁，SYN-ACK只能暂存在 ``C.sk_backlog``：

::

   parent / CPU0 / kernel process context

   CS.state               = SS_CONNECTING
   C.sk_state             = TCP_SYN_SENT
   C.local                = 127.0.0.1:40000
   C.remote               = 127.0.0.1:28080
   C.snd_una              = C_ISN
   C.snd_nxt              = C_ISN + 1
   C.sk_backlog           = [SSYNACK]
   CW                     = installed on sk_sleep(C)

   SSYNACK.seq            = S_ISN
   SSYNACK.ack_seq        = C_ISN + 1
   SSYNACK.flags          = SYN | ACK

server侧仍保留 ``TCP_NEW_SYN_RECV`` request ``R``。它在server方向ehash中，request timer已启动，SYN阶段qlen/young为1/1，accept queue仍为空。

本章从：

::

   inet_wait_for_connect()
   → release_sock(C)

开始，追踪 ``release_sock`` 怎样同步消费SYN-ACK、让client进入 ``TCP_ESTABLISHED``、确认并清理原始SYN重传状态、触发connect wait wakeup，并构造最终ACK。为了把server侧request到child的转换留给下一章，本章停在最终ACK已经进入CPU0输入backlog、 ``NET_RX_SOFTIRQ`` pending，而 ``__dev_queue_xmit`` 尚未重新启用bottom halves的位置。

本章固定条件
------------

* 只有CPU0 online，parent保持当前执行者；
* client没有Fast Open data， ``sk_write_pending=0``；
* 没有signal、timeout、RST、checksum错误、路由失败或内存失败；
* SYN-ACK options与SYN协商结果一致：MSS 65495、SACK、timestamp、window scaling均有效；
* SYN-ACK timestamp固定为 ``TSval=S_TS0``、 ``TSecr=C_TS0``；
* client最终ACK不携带payload， ``seq=C_ISN+1``、 ``ack=S_ISN+1``；
* 最终ACK使用一个晚于 ``C_TS0`` 的client时间戳 ``C_TS1``，并回显 ``TSecr=S_TS0``；
* ECN、TFO、defer-accept、MD5、TCP-AO与MPTCP均关闭。

release_sock为什么先看socket backlog
-----------------------------------

``inet_wait_for_connect`` 的循环已经完成：

::

   DEFINE_WAIT_FUNC(CW, woken_wake_function)
   add_wait_queue(sk_sleep(C), &CW)

随后看到 ``C.sk_state=TCP_SYN_SENT``，执行：

::

   release_sock(C)

``release_sock`` 先取得 ``C.sk_lock.slock``，同时关闭local bottom halves：

::

   spin_lock_bh(&C.sk_lock.slock)

此时：

::

   C.sk_lock.owned = 1
   C.sk_backlog.tail != NULL

所以它不会直接释放ownership，而是先调用：

::

   __release_sock(C)

这个顺序很重要。用户锁保护的TCP状态不能在backlog仍含SYN-ACK时直接交给等待逻辑，否则parent可能先进入真正睡眠，再等待一个其实已经到达的状态变化。

__release_sock怎样取得SSYNACK
----------------------------

``__release_sock`` 把当前backlog链从socket上整体摘下：

::

   skb = C.sk_backlog.head
   C.sk_backlog.head = NULL
   C.sk_backlog.tail = NULL

随后：

::

   spin_unlock_bh(&C.sk_lock.slock)

这里释放的是内部spinlock，并重新允许bottom-half执行；逻辑上的socket用户ownership仍属于parent。producer可以继续向一个新的backlog链追加packet，而parent处理刚摘下的旧链。

本场景旧链只有一个skb：

::

   skb = SSYNACK
   next = NULL

处理入口由client socket协议设置的backlog receive回调决定：

::

   sk_backlog_rcv(C, SSYNACK)
   → tcp_v4_do_rcv(C, SSYNACK)
   → tcp_rcv_state_process(C, SSYNACK)

此时执行环境仍是parent的kernel process context，不是设备IRQ。它正在主动消费先前由NET_RX softirq放入socket backlog的packet。

TCP_SYN_SENT怎样进入专用状态机
------------------------------

``tcp_rcv_state_process`` 检查：

::

   C.sk_state = TCP_SYN_SENT

于是进入：

::

   tcp_rcv_synsent_state_process(C, SSYNACK, tcp_hdr(SSYNACK))

它先解析SYN-ACK options：

::

   peer MSS          = 65495
   SACK permitted    = true
   timestamp seen    = true
   TSval             = S_TS0
   TSecr             = C_TS0
   peer window scale = S_WS = 7

``TSecr=C_TS0`` 能与原始SYN发送时间关联。本场景没有SYN重传，也没有PAWS失败。

ACK为什么有效
-------------

SYN-ACK携带：

::

   SEG.ACK = C_ISN + 1

client当前：

::

   SND.UNA = C_ISN
   SND.NXT = C_ISN + 1

状态机要求ACK严格前进于 ``snd_una``，并且不能超过 ``snd_nxt``：

::

   after(SEG.ACK, SND.UNA) = true
   after(SEG.ACK, SND.NXT) = false

所以ACK正好确认client SYN消耗的一个sequence number。

packet同时满足：

::

   RST = 0
   SYN = 1

因此不会进入reset、discard或simultaneous-open路径。

tcp_ack怎样结束client SYN的未确认状态
------------------------------------

路径调用：

::

   tcp_ack(C, SSYNACK, FLAG_SLOWPATH)

这一步把 ``snd_una`` 推进到：

::

   CTP.snd_una = C_ISN + 1

并从client retransmission tree中清理已经被确认的original ``CSYN``。本章固定没有其他未确认数据，因此处理后：

::

   client retransmission tree = empty
   packets_out                = 0
   original CSYN              = no longer outstanding
   SYN retransmission         = no longer pending

这里不是释放client socket，也不是删除client ehash identity。只消除了“主动SYN仍未被确认”的传输状态。

client怎样接受server sequence space
----------------------------------

SYN-ACK的server sequence number为：

::

   SEG.SEQ = S_ISN

SYN占用一个sequence number，所以client设置：

::

   CTP.rcv_nxt      = S_ISN + 1
   CTP.rcv_wup      = S_ISN + 1
   CTP.copied_seq   = S_ISN + 1
   CTP.rcv_mwnd_seq = rcv_wup + rcv_wnd

同时把SYN-ACK的16-bit window记录为初始send window，并应用协商得到的 ``S_WS``。SYN与SYN-ACK报文中的window字段本身不做scale；后续普通segment才按协商值解释。

timestamp协商成功后：

::

   CTP.rx_opt.tstamp_ok = 1
   CTP.rx_opt.ts_recent = S_TS0
   CTP.tcp_header_len   = sizeof(tcphdr) + timestamp option length

随后同步MSS与receive MSS状态。

tcp_finish_connect怎样发布TCP_ESTABLISHED
----------------------------------------

在sequence、window和option字段准备完成后，路径调用：

::

   tcp_finish_connect(C, SSYNACK)

其中最关键的状态写入是：

::

   tcp_set_state(C, TCP_ESTABLISHED)

client仍保留同一个四元组和ehash位置：

::

   127.0.0.1:40000 → 127.0.0.1:28080

这里只是把查找结果对应的完整client socket从 ``TCP_SYN_SENT`` 更新为 ``TCP_ESTABLISHED``。同时初始化：

* congestion-control transfer state；
* initial congestion window；
* send/receive buffer transfer state；
* receive-route cache；
* active-established security与BPF hook状态；
* fast-path预测字段。

本场景没有keepalive选项，也没有Fast Open额外状态。

state_change怎样标记CW已经被唤醒
-------------------------------

client进入 ``TCP_ESTABLISHED`` 后调用：

::

   C.sk_state_change(C)
   → sock_def_wakeup(...)
   → wake_up_interruptible_all(sk_sleep(C))

睡眠队列中已经存在 ``CW``，它使用：

::

   woken_wake_function

回调先执行memory barrier，再设置：

::

   CW.flags |= WQ_FLAG_WOKEN

parent当前仍是正在CPU0执行的同一个task，状态还是 ``TASK_RUNNING``，所以这里不需要把一个睡眠task重新加入runqueue。真正重要的是 ``WQ_FLAG_WOKEN`` 持久记录了state-change事件。下一次 ``wait_woken`` 即使发生在wakeup之后，也能看见该flag而跳过调度。

这一刻socket两层状态不同步仍是合法的：

::

   CS.state   = SS_CONNECTING
   C.sk_state = TCP_ESTABLISHED

通用socket层只有在 ``__inet_stream_connect`` 完成等待检查后，才把 ``CS.state`` 改为 ``SS_CONNECTED``。

为什么立即发送最终ACK
--------------------

固定场景满足：

::

   CTP.fastopen_req     = NULL
   CTP.syn_data         = false
   C.sk_write_pending   = 0
   defer_accept         = 0
   pingpong mode        = false

因此 ``tcp_rcv_synsent_state_process`` 不延迟第三次握手ACK，而调用：

::

   tcp_send_ack_reflect_ect(C, false)
   → tcp_send_ack(C)
   → __tcp_send_ack(C, CTP.rcv_nxt, ACK)

构造的最终ACK ``CACK`` 为：

::

   source      = 127.0.0.1:40000
   destination = 127.0.0.1:28080

   seq         = C_ISN + 1
   ack_seq     = S_ISN + 1
   flags       = ACK
   payload     = 0

   Timestamp   = TSval C_TS1, TSecr S_TS0

``CACK`` 不进入client retransmission tree。纯ACK不消耗新的sequence number，也不需要作为可重传数据保留。

最终ACK怎样再次进入lo
--------------------

发送路径仍然使用client缓存的local route：

::

   tcp_transmit_skb
   → ip_queue_xmit
   → ip_local_out
   → ip_output
   → dev_queue_xmit
   → __dev_queue_xmit

``__dev_queue_xmit`` 用 ``rcu_read_lock_bh`` 关闭bottom halves，随后选择无队列软件设备 ``lo``：

::

   dev_hard_start_xmit
   → loopback_xmit(CACK, lo)
   → __netif_rx(CACK)
   → enqueue_to_backlog(CACK, CPU0)

结果：

::

   CPU0 input_pkt_queue contains CACK
   NET_RX_SOFTIRQ pending
   no hardware IRQ
   no DMA
   no physical NIC queue

为什么本章停在rcu_read_unlock_bh之前
-----------------------------------

``__dev_queue_xmit`` 发送完成后即将执行：

::

   rcu_read_unlock_bh()

该操作重新启用bottom halves。由于CPU0已经有pending ``NET_RX_SOFTIRQ``，内核可以在这里立即运行接收softirq，再继续返回到 ``tcp_send_ack``。

所以本章选择的精确边界是：

::

   CACK has been queued to CPU0 backlog
   NET_RX_SOFTIRQ is pending
   __dev_queue_xmit has not executed rcu_read_unlock_bh yet

这样client主动建立与final ACK构造属于本章；server request到child的转换从下一章的 ``rcu_read_unlock_bh`` 开始。

本章结束状态
------------

* current executor：parent；
* CPU/mode：CPU0，x86-64 kernel process context；
* call stack： ``release_sock(C) → __release_sock → tcp_v4_do_rcv → tcp_rcv_synsent_state_process → tcp_send_ack → __dev_queue_xmit``；
* parent state：``TASK_RUNNING``，没有schedule；
* ``CW.flags``：包含 ``WQ_FLAG_WOKEN``；
* ``CS.state=SS_CONNECTING``；
* ``C.sk_state=TCP_ESTABLISHED``；
* client tuple与ehash：保持active；
* ``CTP.snd_una=CTP.snd_nxt=C_ISN+1``；
* ``CTP.rcv_nxt=S_ISN+1``；
* original CSYN：已被确认并从retransmission tree清除；
* client SYN retransmission：不再pending；
* client旧backlog链中的SSYNACK：正在被处理，尚未返回到 ``__release_sock``；
* final ACK ``CACK``：已加入CPU0 input backlog；
* ``CACK.seq=C_ISN+1``、 ``CACK.ack_seq=S_ISN+1``；
* server request ``R``：仍为 ``TCP_NEW_SYN_RECV``；
* request ehash/timer：仍active；
* request qlen/young：仍为1/1；
* server child：none；
* accept queue：empty；
* next entry： ``rcu_read_unlock_bh()`` 触发CPU0 NET_RX处理CACK。

关键边界
--------

#. ``release_sock`` 在释放socket ownership前同步处理已有backlog。
#. ``__release_sock`` 摘下backlog链后暂时释放内部spinlock；逻辑socket ownership仍属于parent。
#. client SYN-ACK在process context通过 ``sk_backlog_rcv`` 进入TCP receive状态机。
#. SYN-ACK ACK正好确认 ``C_ISN+1``，original SYN不再是未确认传输。
#. ``TCP_ESTABLISHED`` 先写入TCP协议层； ``SS_CONNECTED`` 仍要等待通用connect层收尾。
#. ``sk_state_change`` 对同一个正在运行的parent仍会设置 ``CW.WQ_FLAG_WOKEN``。
#. wakeup flag用于消除“事件发生在wait_woken之前”的竞态，不要求task此前真的睡眠。
#. 最终ACK是纯ACK，不进入retransmission tree，也不推进client send sequence。
#. local ACK仍经过完整IPv4 output与loopback device receive路径。
#. 本章没有创建server child，也没有修改listener accept queue。

下一入口
--------

下一章从：

::

   __dev_queue_xmit
   → rcu_read_unlock_bh()
   → run pending NET_RX_SOFTIRQ on CPU0
   → tcp_v4_rcv(CACK)

开始。server方向ehash会先找到 ``TCP_NEW_SYN_RECV`` request ``R``；合法最终ACK随后触发完整server child创建、ehash替换和accept queue入队。

资料
----

* `Linux 7.2-rc1 net/core/sock.c：release_sock与__release_sock <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_input.c：TCP_SYN_SENT与tcp_rcv_synsent_state_process <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_input.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_output.c：最终ACK构造与发送 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_output.c>`_
* `Linux 7.2-rc1 net/core/dev.c：loopback output与bottom-half重新启用边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/dev.c>`_
* `Linux 7.2-rc1 kernel/sched/wait.c：WQ_FLAG_WOKEN协议 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/wait.c>`_
