第一百七十四章：tcp_connect怎样构造SYN并通过lo命中server listener？
=============================================================

上一章结束时，client已经具有完整连接身份，但尚未分配SYN：

::

   fd 7 → F7 → client socket CS → tcp_sock CTP

   CS.state          = SS_UNCONNECTED
   C.sk_state        = TCP_SYN_SENT
   local endpoint    = 127.0.0.1:40000
   remote endpoint   = 127.0.0.1:28080
   bind ownership    = CTB / CTB2
   ehash membership  = active
   dst               = local route through lo
   CTP.write_seq     = C_ISN = 0x13572468

parent仍持有client socket lock，并在 ``tcp_v4_connect`` 中调用：

::

   tcp_connect(C)

本章追踪普通SYN的构造、重传状态、IPv4输出、loopback注入和TCP listener lookup。叙事边界停在 ``tcp_v4_do_rcv(L, syn_skb)`` 即将让listener处理SYN的位置；request socket在下一章才创建。

本章固定：

* client与server都在network namespace ``N``，只有CPU0 online；
* local route的 ``dst.dev=lo``，MTU为65536，IPv4 advertised MSS固定为65495；
* ``tcp_timestamps=1``、 ``tcp_sack=1``、 ``tcp_window_scaling=1``；
* client SYN固定携带MSS 65495、SACK-permitted、timestamp与window-scale option；
* client timestamp值记为 ``C_TS0=0x10203040``，window scale固定为 ``C_WS=7``；
* ECN、AccECN、TCP Fast Open、MD5、TCP-AO、MPTCP与自定义BPF header option均关闭；
* IPv4 TTL固定为64，不使用IP option；
* netfilter local-out/post-routing hooks均ACCEPT，不发生XFRM、qdisc排队、RPS重定向、drop或allocation failure；
* loopback SYN在CPU0当前执行流中进入NET_RX softirq；没有硬件IRQ、DMA或物理网卡。

tcp_connect_init怎样从dst建立发送参数
-------------------------------------

``tcp_connect`` 先执行BPF connect callback；固定场景没有程序附着。随后确认IPv4 header可以由已缓存route重建，再调用：

::

   tcp_connect_init(C)

该函数读取上一章提交的dst：

::

   dst.dev = lo
   dst_mtu = 65536

IPv4最大packet length会限制route advertised MSS，因此本章固定：

::

   CTP.advmss = 65495

即：

::

   65535 - sizeof(struct iphdr) - sizeof(struct tcphdr)
   = 65535 - 20 - 20
   = 65495

loopback device MTU虽为65536，IPv4 total length字段仍只有16位，不能把TCP MSS写成65496。

``tcp_connect_init`` 继续初始化：

* ``tcp_header_len``，包含启用的timestamp option长度；
* PMTU与MSS cache；
* 初始receive window和window clamp；
* client receive window scale ``C_WS``；
* ``snd_una``、 ``snd_nxt``、 ``snd_up`` 与 ``write_seq`` 的初始关系；
* initial retransmission timeout；
* retransmission、SACK与outstanding packet accounting。

当前还没有收到peer窗口，因此：

::

   CTP.snd_wnd = 0
   CTP.snd_una = C_ISN
   CTP.snd_nxt = C_ISN

SYN skb怎样取得C_ISN
--------------------

普通路径分配一个stream skb：

::

   tcp_stream_alloc_skb(C, C.sk_allocation, force_schedule=true)
   → SYN skb CSYN

然后：

::

   tcp_init_nondata_skb(CSYN,
                        C,
                        seq=C_ISN,
                        flags=TCPHDR_SYN)

SYN没有应用数据，但TCP SYN flag消耗一个sequence number。初始control block为：

::

   TCP_SKB_CB(CSYN).seq     = C_ISN
   TCP_SKB_CB(CSYN).end_seq = C_ISN + 1
   TCP_SKB_CB(CSYN).flags   = SYN

``tcp_connect_queue_skb`` 把CSYN计入socket发送内存与outstanding packet accounting，并推进：

::

   CTP.write_seq = C_ISN + 1
   CTP.packets_out = 1

随后CSYN进入TCP retransmission tree。这里保存的是可用于超时重传的原始发送对象；真正下送网络栈时， ``tcp_transmit_skb`` 会发送可修改的clone。

SYN header怎样写入options
------------------------

固定未启用Fast Open，因此：

::

   tcp_transmit_skb(C, CSYN, clone_it=1, ...)

发送clone记为 ``XSYN``。TCP输出层为它建立header：

::

   source port = htons(40000)
   dest port   = htons(28080)
   seq         = htonl(C_ISN)
   ack         = 0
   SYN         = 1
   ACK         = 0

固定TCP options为：

::

   MSS            = 65495
   SACK permitted = yes
   Timestamp      = TSval C_TS0, TSecr 0
   Window scale   = C_WS = 7

header length由这些options决定，并保持4-byte alignment。client没有应用数据，所以IP payload只包含TCP header与options。

``tcp_ecn_send_syn`` 在本场景不会设置ECN negotiation flags。TCP checksum使用IPv4 pseudo-header与TCP header计算；loopback仍遵守正常checksum语义，不因“目标是自己”跳过TCP协议格式。

为什么原始CSYN必须留在重传树
---------------------------

SYN发送成功不等于连接已经确认。原始CSYN继续由client socket持有：

::

   C.tcp_rtx_queue contains CSYN

如果后续没有有效SYN-ACK，retransmission timer会重新发送它。发送clone XSYN可以在IP/device层被修改和消费，而不会破坏TCP保留的sequence与option重传状态。

IPv4 header怎样使用已缓存local route
------------------------------------

TCP IPv4 operation分派：

::

   C.icsk_af_ops->queue_xmit
   → ip_queue_xmit(C, XSYN, flow)
   → __ip_queue_xmit

``__ip_queue_xmit`` 从client dst cache取得上一章的route，不需要重新选择source address或端口。它在XSYN前压入IPv4 header：

::

   version  = 4
   ihl      = 5
   saddr    = 127.0.0.1
   daddr    = 127.0.0.1
   protocol = IPPROTO_TCP
   ttl      = 64
   total length = IPv4 header + TCP SYN header/options

并设置：

::

   XSYN.dev      = lo
   XSYN.protocol = ETH_P_IP
   XSYN.dst      = local route dst

随后：

::

   ip_local_out
   → NF_INET_LOCAL_OUT
   → dst_output
   → ip_output
   → NF_INET_POST_ROUTING
   → ip_finish_output

固定hooks全部ACCEPT，packet身份没有被NAT、mark、TOS或route policy改写。

为什么local route仍经过device output
-----------------------------------

目标地址属于本机并不意味着TCP直接调用server listener。IP输出仍进入正常device发送入口：

::

   ip_finish_output
   → ip_finish_output2
   → dev_queue_xmit(XSYN)

local route的neighbor/output处理最终选择 ``lo``。loopback是一个真实的 ``struct net_device``，只是它没有物理介质和DMA ring。

``lo`` 使用noqueue/direct transmit语义，最终进入：

::

   lo.netdev_ops->ndo_start_xmit
   → loopback_xmit(XSYN, lo)

loopback_xmit为什么会orphan发送clone
-----------------------------------

``loopback_xmit`` 首先处理timestamp，然后：

::

   skb_orphan(XSYN)

这会清除发送clone对client socket的ownership/accounting关联。它不删除TCP retransmission tree中的原始CSYN；两者是不同skb身份。

随后确保dst拥有安全reference：

::

   skb_dst_force(XSYN)

再把device-output skb转换为receive语义：

::

   XSYN.protocol = eth_type_trans(XSYN, lo)

没有真正的Ethernet frame上线路。loopback只是让同一个skb转入本机receive队列。

__netif_rx怎样把SYN排到CPU0 backlog
----------------------------------

``loopback_xmit`` 在bottom halves disabled的发送上下文调用：

::

   __netif_rx(XSYN)
   → netif_rx_internal
   → enqueue_to_backlog(XSYN, CPU0, ...)

本场景没有RPS重定向，目标CPU就是当前CPU0。XSYN进入CPU0的 ``softnet_data.input_pkt_queue`` / backlog NAPI，并触发：

::

   NET_RX_SOFTIRQ pending

此刻没有硬件receive interrupt。SYN已经完成device transmit统计，同时等待软件receive路径处理。

为什么NET_RX可以在connect syscall中运行
--------------------------------------

设备发送路径退出并重新启用bottom halves时，CPU0发现NET_RX pending，于是可以在返回 ``tcp_transmit_skb`` 之前运行softirq：

::

   local_bh_enable
   → do_softirq
   → net_rx_action
   → process_backlog

current task仍是parent，但CPU执行上下文已经切换为softirq。parent尚未离开 ``connect(7, ...)``，也仍然拥有client socket的用户锁。

这条顺序很重要：loopback不是“先让connect睡眠，再由另一个CPU收包”。固定单CPU场景中，SYN receive可以嵌套发生在SYN transmit返回之前。

SYN怎样进入IPv4 local-delivery
-----------------------------

backlog NAPI取出XSYN后进入通用receive core：

::

   __netif_receive_skb
   → IPv4 packet_type handler
   → ip_rcv
   → ip_rcv_finish
   → dst_input
   → ip_local_deliver
   → ip_local_deliver_finish
   → ip_protocol_deliver_rcu
   → tcp_v4_rcv

固定packet满足：

* ``pkt_type=PACKET_HOST``；
* IPv4 header、length与checksum有效；
* destination为local address；
* TCP header length与checksum有效；
* 没有XFRM、netfilter或policy drop。

TCP receive层填充：

::

   TCP_SKB_CB(XSYN).seq     = C_ISN
   TCP_SKB_CB(XSYN).end_seq = C_ISN + 1
   TCP_SKB_CB(XSYN).flags   = SYN

listener lookup为什么没有命中client C
------------------------------------

``tcp_v4_rcv`` 调用 ``__inet_lookup_skb``。入站SYN的方向为：

::

   source      = 127.0.0.1:40000
   destination = 127.0.0.1:28080

established lookup使用目的端作为local endpoint。client C的local endpoint是 ``127.0.0.1:40000``，因此它不会匹配这个方向的SYN。

当前也不存在server child或request socket。lookup继续进入listener路径：

::

   __inet_lookup_listener(N,
                          saddr=127.0.0.1,
                          sport=40000,
                          daddr=127.0.0.1,
                          dport=28080,
                          dif=lo.ifindex)

第172章发布的精确地址bucket首先被检查：

::

   ipv4_portaddr_hash(N, 127.0.0.1, 28080)
   → ILB2
   → listener L

因为L绑定具体地址，lookup不需要回退到 ``INADDR_ANY:28080``。

SYN交给listener前的对象状态
-------------------------

``tcp_v4_rcv`` 已经完成policy、filter与control-block填充，然后发现：

::

   L.sk_state = TCP_LISTEN

于是调用：

::

   tcp_v4_do_rcv(L, XSYN)

本章停在该调用进入listener状态机之前。

本章结束状态
------------

* current executor：parent对应的CPU0执行流；
* CPU mode/context：x86-64 kernel NET_RX softirq；
* parent syscall：仍是blocking ``connect(7, ...)``，尚未返回；
* client socket lock：仍由parent拥有；
* ``CS.state=SS_UNCONNECTED``；
* ``C.sk_state=TCP_SYN_SENT``；
* client tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* client bind/bind2 ownership与ehash：active；
* client route/dst：active，output device为 ``lo``；
* ``CTP.write_seq=C_ISN+1``；
* retransmission tree：contains original CSYN；
* ``CTP.packets_out=1``；
* sent clone XSYN：已经由loopback receive path持有；
* server listener L：已被精确lhash2 lookup命中；
* listener request queue length：0；
* request socket：none；
* accepted child：none；
* SYN-ACK：none；
* next entry：``tcp_v4_do_rcv(L, XSYN)`` 进入 ``TCP_LISTEN`` receive state。

关键边界
--------

#. loopback MTU为65536时，IPv4 advertised MSS仍受16-bit total length限制为65495。
#. SYN消耗一个sequence number；``write_seq`` 从C_ISN推进到C_ISN+1。
#. TCP保留原始CSYN用于重传，device层发送并消费clone XSYN。
#. local destination仍经过IPv4 output、device queue与 ``loopback_xmit``。
#. ``loopback_xmit`` 不调用server socket；它通过 ``__netif_rx`` 排入CPU receive backlog。
#. 单CPUloopback的NET_RX softirq可以嵌套运行在 ``connect()`` 的发送路径中。
#. softirq运行时current仍是parent，但执行上下文已经不是普通process context。
#. SYN方向不匹配client C的local endpoint，因此ehash不会错误命中C。
#. server listener通过具体地址 ``127.0.0.1:28080`` 的lhash2被找到。
#. 本章结束时尚未分配request socket，也没有SYN-ACK。

下一入口
--------

下一章从：

::

   tcp_v4_do_rcv(L, XSYN)
   → tcp_rcv_state_process(L, XSYN)
   → tcp_v4_conn_request

开始，追踪SYN option解析、request socket R、ehash与timer引用、SYN-ACK发送，以及SYN-ACK为何先进入client socket backlog。

资料
----

* `Linux 7.2-rc1 net/ipv4/tcp_output.c：tcp_connect、tcp_connect_init与SYN retransmission状态 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_output.c>`_
* `Linux 7.2-rc1 net/ipv4/ip_output.c：ip_queue_xmit与IPv4 header/output路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/ip_output.c>`_
* `Linux 7.2-rc1 drivers/net/loopback.c：loopback_xmit与__netif_rx注入 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/net/loopback.c>`_
* `Linux 7.2-rc1 net/core/dev.c：CPU backlog、NET_RX softirq与receive core <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/dev.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_ipv4.c：tcp_v4_rcv与listener lookup <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_ipv4.c>`_
