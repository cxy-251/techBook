第一百八十六章：client FIN怎样让server H进入TCP_CLOSE_WAIT？
========================================================

上一章停在client FIN已经由 ``loopback_xmit`` 放入CPU0输入backlog，而client的 ``__dev_queue_xmit`` 尚未重新启用bottom halves的位置：

::

   parent / CPU0 / kernel process context

   client C
       state       = TCP_FIN_WAIT1
       snd_una     = C_ISN + 6
       snd_nxt     = C_ISN + 7
       write_seq   = C_ISN + 7
       rcv_nxt     = S_ISN + 1
       owned       = by parent

   CFIN clone
       seq         = C_ISN + 6
       end_seq     = C_ISN + 7
       ack_seq     = S_ISN + 1
       flags       = FIN | ACK
       queued      = CPU0 input backlog

   server H
       state       = TCP_ESTABLISHED
       rcv_nxt     = C_ISN + 6
       copied_seq  = C_ISN + 6
       receive q   = empty

本章从：

::

   rcu_read_unlock_bh()

开始。pending ``NET_RX_SOFTIRQ`` 会让CFIN命中H。H把FIN作为一个占用sequence space的零长度receive skb保存，进入 ``TCP_CLOSE_WAIT``，设置receive shutdown与done标志，并发布fd 8可读。固定的quickack状态随后立即发送纯ACK；该ACK经 ``lo`` 回到client方向时，因为parent仍持有C的用户锁，只能进入 ``C.sk_backlog``。client FIN ACK的实际状态转换留给下一章。

本章固定条件
------------

* 只有CPU0 online，NET_RX在parent当前内核调用栈上嵌套执行；
* CFIN checksum、sequence、ACK与timestamp均有效；
* H没有user owner， ``H.sk_backlog`` 为空；
* H的receive queue在CFIN到达前为空，没有乱序skb；
* 上一轮首个data段建立的quickack计数仍为正，CFIN会触发立即ACK；
* C仍由执行 ``tcp_close`` 的parent持有用户锁；
* 没有RST、丢包、内存失败、window异常、filter拒绝或并发packet；
* server对FIN的ACK固定记为 ``HACK``。

bottom halves重新启用时怎样进入NET_RX
------------------------------------

client的 ``__dev_queue_xmit`` 执行：

::

   rcu_read_unlock_bh()

上一章的 ``loopback_xmit`` 已经调用 ``__netif_rx(CFIN)``，把CPU0 backlog NAPI标记为pending。因此内核可以在返回 ``tcp_send_fin`` 之前运行：

::

   NET_RX_SOFTIRQ
   → net_rx_action
   → process_backlog
   → __netif_receive_skb
   → ip_rcv
   → ip_local_deliver
   → tcp_v4_rcv(CFIN)

这里没有hardware interrupt，也没有切换task。执行环境从parent的process context临时进入同一CPU上的softirq context，处理完成后仍返回原来的close调用栈。

server方向ehash为什么找到H
-------------------------

CFIN的四元组为：

::

   source      = 127.0.0.1:40000
   destination = 127.0.0.1:28080

server方向ehash中已经存在完整child H：

::

   H.local  = 127.0.0.1:28080
   H.remote = 127.0.0.1:40000
   H.state  = TCP_ESTABLISHED

所以 ``__inet_lookup_skb`` 返回H。listener L只匹配尚未建立具体四元组的流量；当前CFIN不会回到listen receive路径，也不会重新创建request或child。

``tcp_v4_rcv`` 取得H的临时引用，完成policy、checksum、header与filter检查，然后查看：

::

   sock_owned_by_user(H) = false

H已经graft到accepted socket AS，但parent此刻没有在fd 8上执行系统调用，因而没有task持有H的用户锁。路径直接取得内部BH lock并调用：

::

   tcp_v4_do_rcv(H, CFIN)
   → tcp_rcv_established(H, CFIN)

CFIN的ACK部分确认了什么
----------------------

CFIN携带：

::

   CFIN.ack_seq = S_ISN + 1

server H当前：

::

   HTP.snd_una = S_ISN + 1
   HTP.snd_nxt = S_ISN + 1

因此这个ACK没有推进server send sequence，也没有清理新的retransmission skb。它只是一个合法的重复ACK值。H没有未确认server data，send queue保持为空。

receive sequence检查看到：

::

   CFIN.seq     = HTP.rcv_nxt = C_ISN + 6
   CFIN.end_seq = C_ISN + 7

CFIN正好位于下一个期望sequence，没有hole，也没有越出receive window。

为什么零payload FIN不会被当作空packet丢弃
--------------------------------------

CFIN的payload长度为0，但它的TCP sequence区间不是空的：

::

   seq     = C_ISN + 6
   end_seq = C_ISN + 7

``end_seq`` 包含FIN占用的一个sequence number。因此 ``tcp_data_queue`` 的“ ``seq==end_seq`` 空segment”检查为false，packet继续进入in-order receive路径。

这一点区分了两个长度：

* userspace可复制payload长度为0；
* TCP sequence space长度为1。

所以FIN可以在不提供任何用户字节的同时改变receive状态，并且需要由peer ACK。

tcp_queue_rcv怎样保存FIN标记
---------------------------

CFIN满足：

::

   CFIN.seq = HTP.rcv_nxt

且receive window非零。 ``tcp_data_queue`` 调用：

::

   tcp_queue_rcv(H, CFIN, &fragstolen)

H的receive queue此前为空，所以CFIN不能与一个已有data skb合并。它作为独立skb加入：

::

   H.sk_receive_queue = [CFIN receive skb]

同时推进：

::

   HTP.rcv_nxt : C_ISN + 6 → C_ISN + 7

``copied_seq`` 代表应用已经消费到哪里，此时fd 8尚未执行新的read，所以保持：

::

   HTP.copied_seq = C_ISN + 6

于是receive queue中的skb没有payload可复制，却保存了“应用还没有消费FIN sequence”的事实。

tcp_fin怎样发布receive shutdown
------------------------------

``tcp_data_queue`` 看到：

::

   CFIN.tcp_flags & TCPHDR_FIN

于是调用：

::

   tcp_fin(H)

它先安排ACK，然后设置：

::

   H.sk_shutdown |= RCV_SHUTDOWN
   H.SOCK_DONE     = true

``RCV_SHUTDOWN`` 表示peer不会再在这个方向发送新的正常数据； ``SOCK_DONE`` 让socket readiness与receive逻辑知道协议receive end已经到达。

这些标志不会关闭H的发送方向。server应用仍可以继续 ``write(8,...)``，也可以稍后调用 ``close(8)`` 发送自己的FIN。

TCP_ESTABLISHED怎样进入TCP_CLOSE_WAIT
-----------------------------------

H收到有效FIN时处于：

::

   H.sk_state = TCP_ESTABLISHED

``tcp_fin`` 的状态分支执行：

::

   tcp_set_state(H, TCP_CLOSE_WAIT)
   inet_csk_enter_pingpong_mode(H)

因此：

::

   H.sk_state = TCP_CLOSE_WAIT

``TCP_CLOSE_WAIT`` 表示TCP已经收到peer FIN并完成receive-side关闭，仍在等待本地应用关闭send side。它不是TIME_WAIT；主动发送第一个FIN的一侧才承担后续FIN_WAIT/TIME_WAIT方向的工作。

为什么fd 8此刻已经EOF-readable
-----------------------------

H仍连接到：

::

   H.sk_socket = AS
   AS.file      = F8
   fd 8         = F8

``tcp_fin`` 完成状态修改后调用H的 ``sk_state_change``。随后 ``tcp_data_queue`` 在H不是dead socket的条件下执行：

::

   tcp_data_ready(H)

``tcp_data_ready`` 看到 ``SOCK_DONE`` 已设置，会调用accepted socket的data-ready回调，唤醒 ``sk_sleep(H)`` 上可能存在的poll/read waiters，并发布异步 ``POLL_IN`` 语义。本场景没有task正在fd 8上睡眠，所以没有task被重新加入runqueue；readiness仍然已经成立。

这里的“readable”不是receive queue中出现了一个用户字节。它表示下一次blocking read能够立即得到确定结果：0，也就是EOF。

为什么FIN ACK立即发送
--------------------

``tcp_fin`` 已经通过：

::

   inet_csk_schedule_ack(H)

记录需要确认新的 ``rcv_nxt``。上一轮H接收首个 ``hello`` data段时进入quickack状态，并只消费了其中一次quickack机会；固定场景中quickack计数仍为正。

因此receive路径的ACK发送检查不会等待delayed-ACK timer，而是调用：

::

   tcp_send_ack(H)

构造纯ACK ``HACK``：

::

   source      = 127.0.0.1:28080
   destination = 127.0.0.1:40000

   seq         = S_ISN + 1
   ack_seq     = C_ISN + 7
   flags       = ACK
   payload     = 0

   Timestamp   = TSval S_TS2, TSecr C_TS2

``HACK`` 确认CFIN占用的sequence number。纯ACK本身不推进H的 ``snd_nxt``，也不进入H的retransmission tree。

HACK怎样再次经过lo
------------------

HACK沿H的local route执行：

::

   tcp_transmit_skb
   → ip_queue_xmit
   → ip_local_out
   → ip_output
   → __dev_queue_xmit
   → loopback_xmit(HACK, lo)
   → __netif_rx(HACK)

当前已经处于CPU0 NET_RX softirq中。新ACK加入CPU0 input backlog后， ``process_backlog`` 在本轮budget内继续取得它，并重新进入：

::

   ip_rcv
   → ip_local_deliver
   → tcp_v4_rcv(HACK)

client方向ehash返回C：

::

   C.local  = 127.0.0.1:40000
   C.remote = 127.0.0.1:28080
   C.state  = TCP_FIN_WAIT1

为什么HACK不能立即修改C
----------------------

parent仍在：

::

   tcp_close(C)
   → __tcp_close(C, 0)
   → tcp_send_fin(C)

而且 ``tcp_close`` 入口已经执行 ``lock_sock(C)``。因此：

::

   sock_owned_by_user(C) = true

``tcp_v4_rcv`` 不会在softirq中直接运行C的TCP状态机，而调用：

::

   tcp_add_backlog(C, HACK)

把HACK记入：

::

   C.sk_backlog = [HACK]

此时HACK只完成了checksum与早期demux等可在入队前完成的检查。它尚未推进 ``C.snd_una``，也尚未把C从 ``TCP_FIN_WAIT1`` 改成 ``TCP_FIN_WAIT2``。

softirq返回到哪里
----------------

CPU0处理完本轮CFIN与HACK后，返回最初触发NET_RX的client发送路径：

::

   NET_RX_SOFTIRQ returns
   → rcu_read_unlock_bh returns
   → __dev_queue_xmit(CFIN) continues
   → tcp_transmit_skb(CFIN) continues
   → tcp_send_fin(C) continues

H已经完成receive-side状态转换；client的FIN确认仍封存在C backlog中。下一章将从FIN发送返回后的 ``__tcp_close`` 收尾开始，由parent亲自消费HACK。

本章结束状态
------------

* current executor：parent调用栈上刚完成CPU0 NET_RX softirq；
* task schedule：没有发生；
* fd 7：已经从fdtable撤销，close系统调用尚未返回；
* ``C.sk_state=TCP_FIN_WAIT1``；
* ``C.sk_shutdown=SHUTDOWN_MASK``；
* C socket ownership：仍由parent持有；
* ``CTP.snd_una=C_ISN+6``；
* ``CTP.snd_nxt=CTP.write_seq=C_ISN+7``；
* CFIN original：仍在client retransmission tree；
* CFIN receive clone：已由H消费为receive queue中的FIN skb；
* ``H.sk_state=TCP_CLOSE_WAIT``；
* ``H.sk_shutdown``：包含 ``RCV_SHUTDOWN``；
* H ``SOCK_DONE``：true；
* ``HTP.rcv_nxt=C_ISN+7``；
* ``HTP.copied_seq=C_ISN+6``；
* H receive queue：包含一个零payload、带FIN标志的skb；
* fd 8 readiness：EOF-readable；
* ``HTP.snd_una=HTP.snd_nxt=S_ISN+1``；
* HACK：已加入 ``C.sk_backlog``；
* ``HACK.seq=S_ISN+1``、 ``HACK.ack_seq=C_ISN+7``；
* network packet backlog：empty；
* next entry： ``tcp_send_fin(C)`` 返回， ``__tcp_close`` 进入non-linger收尾并处理C backlog。

关键边界
--------

#. loopback NET_RX可以嵌套在发送FIN的同一个close调用栈中运行。
#. server ehash按反向四元组找到完整child H，不重新经过listener或request路径。
#. FIN payload长度为0，TCP sequence长度为1，所以不会被空segment检查丢弃。
#. ``rcv_nxt`` 在FIN入队时推进， ``copied_seq`` 要等应用read消费FIN标记后才推进。
#. ``RCV_SHUTDOWN`` 与 ``SOCK_DONE`` 发布receive end，不关闭H的send side。
#. ``TCP_CLOSE_WAIT`` 表示peer已关闭发送方向、本地应用尚未关闭自己的发送方向。
#. EOF readiness不要求receive queue中存在用户字节。
#. quickack仍有效，所以HACK在本场景立即发送，不等待delayed-ACK timer。
#. HACK是纯ACK，不占用server sequence space。
#. parent持有C的用户锁时，softirq只能把HACK追加到C backlog。
#. HACK入backlog尚未确认client original FIN，也尚未推进C状态。

下一入口
--------

下一章从client FIN发送返回后继续：

::

   tcp_send_fin(C) returns
   → sk_stream_wait_close(C, timeout=0)
   → sock_orphan(C)
   → __release_sock(C)
   → sk_backlog_rcv(C, HACK)

HACK会确认 ``C_ISN+7``，清除original FIN，把C推进到 ``TCP_FIN_WAIT2``。默认60秒 ``tcp_fin_timeout`` 随后使完整C转换为一个FIN-WAIT-2 time-wait socket；close返回0后，parent再执行 ``read(8,buf,1)`` 消费FIN标记并得到EOF。

资料
----

* `Linux 7.2-rc1 net/core/dev.c：NET_RX softirq与process_backlog <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/dev.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_ipv4.c：tcp_v4_rcv查找H与C <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_ipv4.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_input.c：tcp_data_queue、tcp_fin与TCP_CLOSE_WAIT <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_input.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_output.c：FIN ACK构造与发送 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_output.c>`_
* `Linux 7.2-rc1 net/core/sock.c：socket ownership与tcp_add_backlog <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_
* `Linux 7.2-rc1 drivers/net/loopback.c：HACK的loopback发送 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/net/loopback.c>`_
