第一百八十八章：close(8)怎样撤销accepted fd并发送server FIN？
=========================================================

上一章结束时，client已经完成主动关闭的第一半，server应用也已经读取到EOF：

::

   parent / CPU0 / x86-64 CPL 3

   close(7)             = 0
   read(8,buf,1)        = 0

   client fd 7          = closed
   client tuple lookup  = lightweight TW
   TW.tw_state          = TCP_TIME_WAIT
   TW.tw_substate       = TCP_FIN_WAIT2
   TW.tw_rcv_nxt        = S_ISN + 1
   TW.tw_snd_nxt        = C_ISN + 7
   TW timer             = armed for 60 seconds

   accepted fd 8        = open, blocking, close-on-exec
   H.sk_state           = TCP_CLOSE_WAIT
   H.sk_shutdown        includes RCV_SHUTDOWN
   H.SOCK_DONE          = true
   H.rcv_nxt            = C_ISN + 7
   H.copied_seq         = C_ISN + 7
   H.snd_una            = S_ISN + 1
   H.snd_nxt            = S_ISN + 1
   H.write_seq          = S_ISN + 1
   H receive queue      = empty

``TCP_CLOSE_WAIT`` 表示H已经收到client FIN，仍在等待server应用关闭自己的发送方向。parent现在执行：

::

   close(8)

本章追踪fd 8怎样从fdtable撤销，F8的最后引用怎样同步进入 ``tcp_close(H,0)``，H怎样从 ``TCP_CLOSE_WAIT`` 进入 ``TCP_LAST_ACK``，以及server FIN怎样经过IPv4与 ``lo`` 进入CPU0输入backlog。本章停在FIN已排入client方向接收路径、bottom halves尚未重新启用的位置。

本章固定条件
------------

* 只有CPU0 online，parent是唯一执行本次close的task；
* fd 8没有被 ``dup``、 ``fork`` 或其他引用共享，F8由本次close释放最后引用；
* H receive queue为空，client FIN已经由上一章的read消费；
* H从未发送server payload，write queue与retransmission tree为空；
* 没有配置 ``SO_LINGER``， ``inet_release`` 传入 ``timeout=0``；
* client lightweight TW仍在ehash中， ``tw_substate=TCP_FIN_WAIT2``；
* 没有signal、RST、丢包、checksum错误、路由失败、内存失败或并发packet；
* server FIN固定记为 ``HFIN``，sequence为 ``S_ISN+1``。

close为什么先让fd 8失效
----------------------

x86-64入口执行：

::

   __x64_sys_close(8)
   → __do_sys_close(8)
   → file_close_fd(8)

在 ``files->file_lock`` 下，locked路径找到：

::

   fdt->fd[8] = F8

随后发布：

::

   fdt->fd[8] = NULL

并由：

::

   __put_unused_fd(files, 8)

清除fd 8的open位，必要时把 ``files->next_fd`` 退回8。与fd 7关闭相同，旧 ``close_on_exec`` 位允许保留；fd已由open位判定为无效，未来复用编号时新flags会覆盖该位。

因此从这一刻开始：

::

   a later fd lookup of 8 → EBADF

H仍然存在，因为当前close调用栈已经取得F8，而且TCP还需要发送server FIN并处理最终ACK。

F8为什么同步进入__fput
---------------------

``file_close_fd`` 返回F8后，系统调用执行：

::

   filp_flush(F8, current->files)

socket file没有额外flush操作，本场景返回0。随后：

::

   fput_close_sync(F8)

F8没有共享引用， ``file_ref_put_close`` 判断这是最后一个引用，直接调用：

::

   __fput(F8)

所以server FIN发送发生在当前 ``close(8)`` 的内核调用栈中，不会推迟到task work，也不会等下一次系统调用入口。

socket release怎样找到H
----------------------

``__fput`` 完成file级通知与锁清理后，调用：

::

   F8.f_op->release
   → sock_close(I8, F8)
   → __sock_release(AS, I8)
   → inet_release(AS)

此时accepted ``struct socket`` 仍保存：

::

   AS.sk = H

没有 ``SO_LINGER``，所以 ``inet_release`` 选择：

::

   timeout = 0
   H.sk_prot->close(H, 0)
   → tcp_close(H, 0)

``timeout=0`` 只表示close调用者不等待对端ACK之外更长的linger周期。由于loopback最终ACK可以在当前调用栈中到达，本场景仍可能在系统调用返回前完成H的协议销毁。

tcp_close怎样取得H的用户锁
-------------------------

``tcp_close`` 调用：

::

   lock_sock(H)
   → __tcp_close(H, 0)

parent成为H的socket user owner。随后到达的最终ACK若在NET_RX softirq中找到H，不能直接修改受用户锁保护的状态，只能进入 ``H.sk_backlog``。

``__tcp_close`` 首先写入：

::

   H.sk_shutdown = SHUTDOWN_MASK

此前只有 ``RCV_SHUTDOWN``；现在server应用自己的send side也被关闭。H的wire state此刻仍是：

::

   H.sk_state = TCP_CLOSE_WAIT

为什么不会因未读数据发送RST
--------------------------

descriptor close会检查H receive queue。上一章的 ``read(8,buf,1)=0`` 已经消费并释放FIN skb，所以：

::

   skb_peek(&H.sk_receive_queue) = NULL
   data_was_unread               = false

固定场景同时没有TCP repair与zero linger。因此不会进入：

* unread-data active reset；
* zero-linger abort；
* already-closed shortcut。

路径进入正常的passive-side close状态转换：

::

   tcp_close_state(H)

即使纯FIN skb尚未被read，close检查也会从 ``end_seq`` 中减去FIN占用的sequence，不把FIN本身误判为未读payload；本场景队列已经完全为空，结论更直接。

TCP_CLOSE_WAIT怎样变为TCP_LAST_ACK
--------------------------------

``tcp_close_state`` 查固定状态表：

::

   TCP_CLOSE_WAIT
       → TCP_LAST_ACK
       → TCP_ACTION_FIN

于是执行：

::

   tcp_set_state(H, TCP_LAST_ACK)

H仍以原四元组留在established ehash中：

::

   127.0.0.1:28080 ← 127.0.0.1:40000

``TCP_LAST_ACK`` 表示本地已经收到peer FIN，现在发送自己的FIN并等待最后一个ACK。H不会进入TIME_WAIT；主动关闭的client一侧已经由TW承担这一职责。

为什么HFIN需要一个新skb
----------------------

``tcp_close_state`` 返回 ``TCP_ACTION_FIN``， ``__tcp_close`` 调用：

::

   tcp_send_fin(H)

H从未发送server payload，当前：

::

   tcp_write_queue_tail(H) = NULL
   H retransmission tree   = empty
   memory pressure         = false

因此路径分配新的 ``HFIN-original``，并调用：

::

   tcp_init_nondata_skb(HFIN-original,
                        seq=S_ISN+1,
                        flags=ACK|FIN)

HFIN没有payload，FIN仍占用一个sequence number：

::

   HFIN.seq     = S_ISN + 1
   HFIN.end_seq = S_ISN + 2

``tcp_queue_skb`` 把original排入write queue，并推进：

::

   HTP.write_seq : S_ISN + 1 → S_ISN + 2

HFIN确认client的哪个sequence
---------------------------

H已经收到并消费client FIN，所以receive状态为：

::

   HTP.rcv_nxt = C_ISN + 7

server FIN同时携带ACK：

::

   HFIN.ack_seq = C_ISN + 7

它再次确认client FIN之后的下一个sequence。这个ACK值不会让client send sequence继续前进；TW保存的：

::

   TW.tw_snd_nxt = C_ISN + 7

已经代表client发送端的终点。

tcp_send_fin为什么立即push
-------------------------

新FIN skb入队后，调用：

::

   __tcp_push_pending_frames(H, current_mss, TCP_NAGLE_OFF)

最终发出的 ``HFIN-clone`` 为：

::

   source      = 127.0.0.1:28080
   destination = 127.0.0.1:40000

   seq         = S_ISN + 1
   ack_seq     = C_ISN + 7
   flags       = FIN | ACK
   payload     = 0

   Timestamp   = TSval S_TS3, TSecr C_TS2

发送时：

::

   HTP.snd_nxt = S_ISN + 2
   HTP.snd_una = S_ISN + 1

所以 ``HFIN-original`` 成为未确认传输，进入H retransmission tree。IPv4发送的是clone；若最终ACK丢失，H可以重传server FIN。

HFIN怎样进入lo接收路径
---------------------

发送clone沿H的local route执行：

::

   tcp_transmit_skb
   → ip_queue_xmit
   → ip_local_out
   → ip_output
   → dev_queue_xmit
   → __dev_queue_xmit

``__dev_queue_xmit`` 在 ``rcu_read_lock_bh`` 下选择无队列软件设备 ``lo``：

::

   dev_hard_start_xmit
   → loopback_xmit(HFIN-clone, lo)
   → __netif_rx(HFIN-clone)
   → enqueue_to_backlog(HFIN-clone, CPU0)

结果：

::

   CPU0 input_pkt_queue contains HFIN-clone
   NET_RX_SOFTIRQ pending
   no hardware IRQ
   no DMA
   no physical NIC queue

为什么本章停在rcu_read_unlock_bh之前
-----------------------------------

``__dev_queue_xmit`` 即将执行：

::

   rcu_read_unlock_bh()

CPU0已有pending NET_RX。bottom halves重新启用后，client方向lookup会命中轻量TW，而不是已经销毁的完整C。TW对HFIN的检查、真正TIME_WAIT转换与最终ACK构造属于下一章。

本章选择的精确边界是：

::

   HFIN-clone has been queued to CPU0 backlog
   NET_RX_SOFTIRQ is pending
   __dev_queue_xmit has not executed rcu_read_unlock_bh yet

本章结束状态
------------

* current executor：parent；
* CPU/mode：CPU0，x86-64 kernel process context；
* call stack： ``close(8) → fput_close_sync → __fput → sock_close → inet_release → tcp_close → tcp_send_fin → __dev_queue_xmit``；
* parent state：``TASK_RUNNING``，没有schedule；
* fd 8：fdtable条目已撤销，open位已清除；
* F8/AS清理：正在同步执行，尚未从 ``__fput`` 返回；
* ``H.sk_state=TCP_LAST_ACK``；
* ``H.sk_shutdown=SHUTDOWN_MASK``；
* H tuple与established ehash：active；
* H socket ownership：仍由parent持有；
* ``HTP.snd_una=S_ISN+1``；
* ``HTP.snd_nxt=HTP.write_seq=S_ISN+2``；
* ``HTP.rcv_nxt=HTP.copied_seq=C_ISN+7``；
* HFIN original：位于H retransmission tree，尚未确认；
* HFIN clone：已加入CPU0 input backlog；
* ``HFIN.seq=S_ISN+1``、 ``HFIN.end_seq=S_ISN+2``；
* ``TW.tw_state=TCP_TIME_WAIT``；
* ``TW.tw_substate=TCP_FIN_WAIT2``；
* ``TW.tw_rcv_nxt=S_ISN+1``；
* TW timer：仍为先前的FIN_WAIT2计时；
* next entry： ``rcu_read_unlock_bh()`` 触发CPU0 NET_RX处理HFIN。

关键边界
--------

#. fd 8先从fdtable撤销并清除open位，最后一个F8引用再同步进入 ``__fput``。
#. ``timeout=0`` 取消linger等待，不取消正常server FIN。
#. H receive queue为空，所以close不会因未读payload发送RST。
#. ``TCP_CLOSE_WAIT`` 在应用close时进入 ``TCP_LAST_ACK``，并要求发送FIN。
#. passive closer H不承担TIME_WAIT；client轻量TW已经承担该角色。
#. HFIN没有payload，仍占用 ``[S_ISN+1,S_ISN+2)`` sequence区间。
#. HFIN的ACK字段继续确认 ``C_ISN+7``。
#. original HFIN进入H retransmission tree，发送clone经IPv4与lo。
#. parent持有H用户锁；未来最终ACK不能在softirq中直接改变H。
#. client方向四元组由TW接管，完整C不会重新出现。

下一入口
--------

下一章从：

::

   __dev_queue_xmit
   → rcu_read_unlock_bh()
   → run pending NET_RX_SOFTIRQ on CPU0
   → tcp_v4_rcv(HFIN)

开始。ehash lookup会返回 ``tw_state=TCP_TIME_WAIT`` 的TW； ``tcp_timewait_state_process`` 根据 ``tw_substate=TCP_FIN_WAIT2`` 验证HFIN，把子状态推进到真正 ``TCP_TIME_WAIT``，更新 ``tw_rcv_nxt``，重新启动60秒timer并发送最终ACK。

资料
----

* `Linux 7.2-rc1 fs/open.c：close与fput_close_sync <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 fs/file.c：file_close_fd_locked与open位清理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
* `Linux 7.2-rc1 fs/file_table.c：__fput同步release路径 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 net/socket.c：sock_close与__sock_release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 net/ipv4/af_inet.c：inet_release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp.c：TCP_CLOSE_WAIT到TCP_LAST_ACK与__tcp_close <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_output.c：tcp_send_fin <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_output.c>`_
* `Linux 7.2-rc1 drivers/net/loopback.c：server FIN的loopback发送 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/net/loopback.c>`_
