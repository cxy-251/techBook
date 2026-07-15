第一百八十三章：PSH|ACK数据段怎样通过lo进入H并触发立即ACK？
================================================================

上一章已经把 ``"hello"`` 复制进client数据skb，并建立固定TCP header身份：

::

   tuple       = 127.0.0.1:40000 → 127.0.0.1:28080
   seq         = C_ISN + 1
   end_seq     = C_ISN + 6
   ack_seq     = S_ISN + 1
   flags       = ACK | PSH
   payload     = "hello"

parent仍在 ``write(7,"hello",5)`` 内持有client C。server child H已经graft到accepted socket AS，但没有任何task持有H的socket lock。

本章从：

::

   ip_queue_xmit(C,data clone,...)

开始，追踪数据segment经过IPv4 output与loopback NET_RX、命中H、进入receive queue并发送立即ACK。叙事停在反向ACK已经排入 ``C.sk_backlog`` 的位置。

固定netfilter、XFRM、cgroup、BPF、PSP、checksum和内存检查全部成功；只有CPU0 online，没有丢包、重排、GRO合并或并发read。

IPv4为什么复用已有loopback route
-------------------------------

client connect阶段已经把local route缓存到C的dst。 ``__ip_queue_xmit`` 首先读取该route：

::

   C dst → RTN_LOCAL → lo

因此本次无需新的 ``ip_route_output_flow`` 查找。路径给发送clone前压入IPv4 header：

::

   version  = 4
   protocol = IPPROTO_TCP
   saddr    = 127.0.0.1
   daddr    = 127.0.0.1
   DF       = set for cached route policy

随后：

::

   ip_local_out
   → LOCAL_OUT netfilter hook
   → dst_output
   → ip_output
   → ip_finish_output
   → dev_queue_xmit

五字节payload远小于loopback MTU，不发生IPv4 fragmentation。

lo为什么直接调用loopback_xmit
-----------------------------

``lo`` 是noqueue软件设备。 ``__dev_queue_xmit`` 在BH disabled区域发现qdisc没有enqueue函数，经过设备UP、recursion和validation检查后直接调用：

::

   dev_hard_start_xmit
   → lo.ndo_start_xmit
   → loopback_xmit

``loopback_xmit`` 不把packet交给物理NIC。它执行：

::

   skb_tx_timestamp
   skb_orphan
   skb_dst_force
   eth_type_trans
   __netif_rx(data clone)

``skb_orphan`` 解除发送clone对C的write-memory owner关系；保留在client retransmission tree中的原始skb仍属于C，继续代表未确认数据。

``__netif_rx`` 把packet加入CPU0 input backlog并触发NET_RX softirq。当前只有CPU0，所以没有跨CPU steering。

原始skb何时进入retransmission tree
---------------------------------

发送clone被 ``loopback_xmit`` 接收后， ``tcp_transmit_skb`` 返回成功。 ``tcp_write_xmit`` 对原始skb调用：

::

   tcp_event_new_data_sent(C,original skb)

该函数完成发送端发布：

::

   C.snd_nxt       : C_ISN+1 → C_ISN+6
   C write queue   : remove original skb
   C rtx tree      : insert original skb
   C.packets_out   : 0 → 1
   retransmit timer: armed/rearmed

``C.snd_una`` 仍是 ``C_ISN+1``，表示这五字节已经发送却尚未被ACK确认。

NET_RX怎样命中server child H
----------------------------

当 ``__dev_queue_xmit`` 离开BH-disabled区域时，CPU0可以在当前write调用栈内运行pending NET_RX softirq。IPv4 local receive最终进入：

::

   tcp_v4_rcv(data skb)

``__inet_lookup_skb`` 使用反向接收四元组：

::

   local  = 127.0.0.1:28080
   remote = 127.0.0.1:40000

established ehash直接找到H。packet不会回到listener L，也不会创建新的request_sock。

``tcp_v4_rcv`` 随后：

::

   bh_lock_sock(H)

H没有被用户task持有，所以：

::

   sock_owned_by_user(H) = false
   → tcp_v4_do_rcv(H,skb)
   → tcp_rcv_established(H,skb)

数据不进入 ``H.sk_backlog``，而是在NET_RX上下文直接处理。

header prediction怎样接受这5字节
-------------------------------

固定segment满足established fast path的关键条件：

::

   seq == H.rcv_nxt == C_ISN+1
   ack_seq == H.snd_una == S_ISN+1
   payload is inside receive window
   checksum valid
   timestamps valid
   no SYN/FIN/RST/URG

PSH被header-prediction mask忽略，不阻止fast path。 ``tcp_rcv_established`` 移除TCP header后，把payload交给：

::

   tcp_queue_rcv(H,skb,...)

receive queue最初为空，不能与tail coalesce，因此skb本身加入：

::

   H.sk_receive_queue

并由 ``skb_set_owner_r`` 计入H的receive-memory accounting。

H的接收序列怎样推进
-------------------

``tcp_queue_rcv`` 在入队时更新：

::

   H.rcv_nxt : C_ISN+1 → C_ISN+6

``H.copied_seq`` 仍是 ``C_ISN+1``，因为用户态尚未调用read。两者差值正好是可读字节数：

::

   H.rcv_nxt - H.copied_seq = 5

skb的TCP header已经pull掉，receive queue中的有效payload长度为5，内容保持 ``"hello"``。

为什么accepted fd 8变为可读
---------------------------

入队后 ``tcp_data_ready(H)`` 检查：

::

   available bytes = 5
   H.sk_rcvlowat    = 1
   5 >= 1

于是调用H的 ``sk_data_ready`` callback。默认callback是 ``sock_def_readable``，它通过上一批 ``sock_graft`` 建立的：

::

   H.sk_wq = &AS.wq

向wait queue发布：

::

   EPOLLIN | EPOLLPRI | EPOLLRDNORM | EPOLLRDBAND

本场景没有task或epoll registration正在等待fd 8，所以没有实际task需要唤醒。可读性仍然是持续状态：此后poll/select/epoll或blocking read检查H时会看见5字节可读。

第一份数据为什么触发立即ACK
---------------------------

``tcp_event_data_recv`` 为H安排ACK并观察到这是连接建立后的第一份data：

::

   H.icsk_ack.ato = 0

于是初始化delayed-ACK engine，同时进入quickack模式：

::

   tcp_incr_quickack(H,TCP_MAX_QUICKACKS)
   H.icsk_ack.ato = TCP_ATO_MIN

随后 ``__tcp_ack_snd_check`` 看见 ``tcp_in_quickack_mode(H)``，直接调用：

::

   tcp_send_ack(H)

因此固定场景不会把第一份 ``hello`` 留给delayed-ACK timer。这个ACK在fd 8 read之前已经构造并发送。

反向ACK包含什么
--------------

``tcp_send_ack`` 分配独立pure-ACK skb。它不加入H的write queue或retransmission tree：

::

   tuple   = 127.0.0.1:28080 → 127.0.0.1:40000
   seq     = S_ISN + 1
   ack_seq = C_ISN + 6
   flags   = ACK
   payload = none

pure ACK不消耗sequence number，所以：

::

   H.snd_nxt = S_ISN + 1

保持不变。

ACK为什么先进入C.sk_backlog
--------------------------

ACK再次经过IPv4 output与 ``lo``，反向ehash lookup找到client C。此时parent仍在 ``tcp_sendmsg`` 内持有C：

::

   sock_owned_by_user(C) = true

``tcp_v4_rcv`` 不能直接执行C的 ``tcp_rcv_established``，于是调用：

::

   tcp_add_backlog(C,ack skb)

ACK成为 ``C.sk_backlog`` 的一个节点。此刻它尚未推进 ``C.snd_una``，原始hello skb仍留在client retransmission tree。

固定源码依据
------------

以下链接全部固定到 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d``：

* `net/ipv4/tcp_output.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_output.c>`_： ``tcp_write_xmit``、 ``tcp_event_new_data_sent``、 ``__tcp_transmit_skb`` 与 ``tcp_send_ack``；
* `net/ipv4/ip_output.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/ip_output.c>`_： ``__ip_queue_xmit`` 与IPv4 local output；
* `net/core/dev.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/dev.c>`_： ``__dev_queue_xmit``、noqueue发送与 ``__netif_rx``；
* `drivers/net/loopback.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/net/loopback.c>`_： ``loopback_xmit``；
* `net/ipv4/tcp_ipv4.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_ipv4.c>`_： ``tcp_v4_rcv``、ehash lookup与socket-owned backlog分支；
* `net/ipv4/tcp_input.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_input.c>`_： ``tcp_rcv_established``、 ``tcp_queue_rcv``、 ``tcp_event_data_recv`` 与ACK选择；
* `net/core/sock.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_： ``sock_def_readable``。

本章结束状态
------------

::

   current executor          = CPU0 NET_RX inside parent write stack
   CPU/mode                  = CPU0, softirq processing
   current syscall           = write(7,"hello",5)

   client C                  = TCP_ESTABLISHED
   C.snd_una                 = C_ISN + 1
   C.snd_nxt/write_seq       = C_ISN + 6 / C_ISN + 6
   C rtx tree                = one original hello skb
   C.packets_out             = 1
   C.sk_backlog              = one pure ACK
   client socket owner       = parent

   server child H            = TCP_ESTABLISHED
   H.rcv_nxt                 = C_ISN + 6
   H.copied_seq              = C_ISN + 1
   H receive queue           = one 5-byte hello skb
   H readable bytes          = 5
   fd 8 poll state           = EPOLLIN | EPOLLRDNORM
   H.snd_nxt                 = S_ISN + 1

   ACK seq/ack               = S_ISN+1 / C_ISN+6
   ACK location              = C.sk_backlog
   packet/NET_RX backlog     = empty
   next entry                = release_sock(C)

下一章从 ``tcp_sendmsg`` 的 ``release_sock(C)`` 开始，处理反向ACK并让write返回5；随后parent调用 ``read(8,buf,5)`` 取走 ``hello``。
