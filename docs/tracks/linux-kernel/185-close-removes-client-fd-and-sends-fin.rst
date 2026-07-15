第一百八十五章：close(7)怎样撤销client fd并发送FIN？
==================================================

上一章结束时，parent已经完成一次client到server的数据传输：

::

   parent / CPU0 / x86-64 CPL 3

   fd 7 → client socket C
   fd 8 → accepted server socket H

   C.sk_state       = TCP_ESTABLISHED
   C.snd_una        = C_ISN + 6
   C.snd_nxt        = C_ISN + 6
   C.write_seq      = C_ISN + 6
   C.rcv_nxt        = S_ISN + 1

   H.sk_state       = TCP_ESTABLISHED
   H.rcv_nxt        = C_ISN + 6
   H.copied_seq     = C_ISN + 6
   H.snd_una        = S_ISN + 1
   H.snd_nxt        = S_ISN + 1

   C retransmission tree = empty
   C write queue         = empty
   H receive queue       = empty

``write(7,"hello",5)=5`` 已经得到server ACK， ``read(8,buf,5)=5`` 也已经消费全部五字节。现在parent执行：

::

   close(7)

本章追踪fd 7怎样先从fdtable消失，最后一个file引用怎样同步进入socket release， ``TCP_ESTABLISHED`` 的C怎样变为 ``TCP_FIN_WAIT1``，以及一个不带payload的 ``FIN|ACK`` 怎样经过IPv4与 ``lo`` 进入CPU0输入backlog。本章停在FIN已排入接收路径、bottom halves尚未重新启用的位置；server H对FIN的处理留给下一章。

本章固定条件
------------

* 只有CPU0 online，parent是唯一运行本故事系统调用的task；
* fd 7没有通过 ``dup``、 ``fork`` 或其他方式共享，F7的最后一个引用由本次 ``close`` 释放；
* client receive queue为空，没有尚未被应用读取的server数据；
* client write queue与retransmission tree为空，先前五字节已经被确认；
* 没有配置 ``SO_LINGER``，所以 ``inet_release`` 使用 ``timeout=0``；
* 没有signal、RST、路由失败、checksum错误、内存失败或并发packet；
* TCP timestamp继续启用，ECN、TFO、MD5、TCP-AO与MPTCP均关闭；
* 新FIN固定记为 ``CFIN``，它的sequence为 ``C_ISN+6``。

close系统调用为什么先撤销fd
---------------------------

x86-64系统调用入口进入：

::

   __x64_sys_close(7)
   → __do_sys_close(7)
   → file_close_fd(7)

``file_close_fd`` 在parent的 ``files_struct`` 上取得 ``file_lock``，找到：

::

   fdt->fd[7] = F7

随后调用的locked路径先发布：

::

   fdt->fd[7] = NULL

再由：

::

   __put_unused_fd(files, 7)

清除fd 7对应的open位，并把 ``files->next_fd`` 必要时退回7。 ``close_on_exec`` bitmap中的旧位不需要在这里同步清零：open位已经让fd 7失效，未来重新分配这个编号时 ``__set_open_fd`` 会按新flags覆盖该位。返回的 ``F7`` 只是供当前close路径继续清理；它已经不能再通过parent的fdtable查到。

因此从这一刻开始，即使后面的协议关闭仍在执行：

::

   a later fd lookup of 7 → EBADF

fd生命周期与TCP状态生命周期在这里第一次分开：fd 7已经关闭，C仍然是一个需要发送FIN并等待协议收尾的TCP对象。

filp_flush为什么不完成TCP关闭
----------------------------

``file_close_fd`` 返回F7后， ``close`` 调用：

::

   filp_flush(F7, current->files)

本场景socket file没有需要在 ``flush`` 中执行的额外工作，返回0。真正的最后引用释放由：

::

   fput_close_sync(F7)

完成。

这个入口针对close的最后引用做同步处理。F7没有共享引用，所以 ``file_ref_put_close`` 判断引用已经归零，直接调用：

::

   __fput(F7)

它不会把本次释放推迟到task work。也就是说，TCP FIN发送发生在当前 ``close(7)`` 的内核调用栈中，系统调用要等这条同步清理路径返回后才可能回到用户态。

__fput怎样进入socket release
---------------------------

``__fput`` 依次执行file级关闭通知、安全检查与锁清理，然后调用F7的release回调：

::

   F7.f_op->release
   → sock_close(I7, F7)
   → __sock_release(CS, I7)

其中 ``CS`` 是fd 7原来的 ``struct socket``。 ``__sock_release`` 读取IPv4 stream ``proto_ops``，并调用：

::

   CS.ops->release(CS)
   → inet_release(CS)

``inet_release`` 此时仍能取得：

::

   CS.sk = C

因为没有 ``SO_LINGER``，它选择：

::

   timeout = 0
   C.sk_prot->close(C, 0)
   → tcp_close(C, 0)

``timeout=0`` 表示close调用者不等待TCP四次挥手全部完成。它不表示丢弃FIN，也不表示把正常关闭改成RST。

tcp_close为什么先取得C的用户锁
-----------------------------

``tcp_close`` 从：

::

   lock_sock(C)
   → __tcp_close(C, 0)

开始。parent成为C的socket user owner。若此时有入站packet，softirq不能直接改变受用户锁保护的TCP状态，只能把packet追加到 ``C.sk_backlog``。

``__tcp_close`` 先设置：

::

   C.sk_shutdown = SHUTDOWN_MASK

这表示应用层的发送与接收两侧都已关闭。它与TCP wire state不同；此时：

::

   C.sk_state = TCP_ESTABLISHED

仍未改变。

为什么本次关闭不会发送RST
-------------------------

descriptor close会检查并清空C的receive queue。当前队列为空：

::

   skb_peek(&C.sk_receive_queue) = NULL
   data_was_unread               = false

所以不会进入“丢弃未读数据并发送active reset”的分支。

固定场景同时满足：

::

   C.sk_state                  != TCP_CLOSE
   CTP.repair                  = false
   SOCK_LINGER with zero time  = false

因此 ``__tcp_close`` 选择正常的TCP active close：

::

   tcp_close_state(C)

若client receive queue中还有未读server数据，结果会变成RST；若配置zero linger，也会走abort路径。当前故事把这两个条件都排除，所以FIN是由明确的状态检查决定的。

TCP_ESTABLISHED怎样变为TCP_FIN_WAIT1
----------------------------------

``tcp_close_state`` 查固定状态表：

::

   TCP_ESTABLISHED
       → TCP_FIN_WAIT1
       → TCP_ACTION_FIN

于是：

::

   tcp_set_state(C, TCP_FIN_WAIT1)

C保留原四元组与established ehash身份：

::

   127.0.0.1:40000 → 127.0.0.1:28080

此处的 ``TCP_FIN_WAIT1`` 表示本地关闭已经开始，而且FIN需要被发送并确认。 ``tcp_close_state`` 返回 ``TCP_ACTION_FIN`` 后，调用：

::

   tcp_send_fin(C)

为什么FIN需要自己的skb
---------------------

``tcp_send_fin`` 先查看client write queue尾部。先前的 ``hello`` 已经发送并被确认，当前：

::

   tcp_write_queue_tail(C) = NULL
   C retransmission tree   = empty
   memory pressure         = false

因此不能把FIN附加到一个尚未发送的data skb，也无需在内存压力下修改已发送skb。路径分配新的skb ``CFIN-original``，保留TCP/IP header空间，然后调用：

::

   tcp_init_nondata_skb(CFIN-original,
                        seq=C_ISN+6,
                        flags=ACK|FIN)

CFIN没有payload：

::

   skb->len = 0

但FIN占用一个TCP sequence number，所以控制块记录：

::

   CFIN.seq     = C_ISN + 6
   CFIN.end_seq = C_ISN + 7

``tcp_queue_skb`` 把original加入write queue，并推进：

::

   CTP.write_seq : C_ISN + 6 → C_ISN + 7

FIN为什么立即发送
-----------------

新skb入队后， ``tcp_send_fin`` 调用：

::

   __tcp_push_pending_frames(C, current_mss, TCP_NAGLE_OFF)

``TCP_NAGLE_OFF`` 让这个关闭控制段不等待后续应用数据。发送路径为CFIN建立普通ACK段header：

::

   source      = 127.0.0.1:40000
   destination = 127.0.0.1:28080

   seq         = C_ISN + 6
   ack_seq     = S_ISN + 1
   flags       = FIN | ACK
   payload     = 0

   Timestamp   = TSval C_TS2, TSecr S_TS0

发送时 ``snd_nxt`` 前进到：

::

   CTP.snd_nxt = C_ISN + 7

而 ``snd_una`` 仍为：

::

   CTP.snd_una = C_ISN + 6

所以original FIN成为一个未确认sequence区间，进入client retransmission tree；若ACK丢失，它可以由TCP重传计时器重新发送。交给IPv4的是发送clone，original继续由C保存。

CFIN怎样进入loopback接收路径
----------------------------

发送clone沿用连接缓存的local route：

::

   tcp_transmit_skb
   → ip_queue_xmit
   → ip_local_out
   → ip_output
   → dev_queue_xmit
   → __dev_queue_xmit

``__dev_queue_xmit`` 在 ``rcu_read_lock_bh`` 保护下关闭local bottom halves，并选择无队列软件设备 ``lo``：

::

   dev_hard_start_xmit
   → loopback_xmit(CFIN-clone, lo)
   → __netif_rx(CFIN-clone)
   → enqueue_to_backlog(CFIN-clone, CPU0)

结果是：

::

   CPU0 input_pkt_queue contains CFIN-clone
   NET_RX_SOFTIRQ pending
   no hardware IRQ
   no DMA
   no physical NIC queue

为什么本章停在rcu_read_unlock_bh之前
-----------------------------------

``loopback_xmit`` 返回后， ``__dev_queue_xmit`` 即将执行：

::

   rcu_read_unlock_bh()

这会重新启用bottom halves。CPU0已有pending ``NET_RX_SOFTIRQ``，所以server H可以在FIN发送调用尚未返回时立即处理CFIN。

本章选择的精确边界是：

::

   CFIN-clone has been queued to CPU0 backlog
   NET_RX_SOFTIRQ is pending
   __dev_queue_xmit has not executed rcu_read_unlock_bh yet

这样fd撤销、同步 ``__fput``、client active-close状态转换与FIN构造属于本章；server H的 ``TCP_CLOSE_WAIT`` 与EOF发布从下一章开始。

本章结束状态
------------

* current executor：parent；
* CPU/mode：CPU0，x86-64 kernel process context；
* call stack： ``close(7) → fput_close_sync → __fput → sock_close → inet_release → tcp_close → tcp_send_fin → __dev_queue_xmit``；
* parent state：``TASK_RUNNING``，没有schedule；
* fd 7：已从fdtable撤销，open位已清除；旧close-on-exec位即使保留也不再有语义；
* F7/CS清理：正在同步执行，尚未从 ``__fput`` 返回；
* ``CS.sk=C``：当前仍可由release调用栈使用；
* ``C.sk_state=TCP_FIN_WAIT1``；
* ``C.sk_shutdown=SHUTDOWN_MASK``；
* C tuple与established ehash：active；
* ``CTP.snd_una=C_ISN+6``；
* ``CTP.snd_nxt=CTP.write_seq=C_ISN+7``；
* ``CTP.rcv_nxt=S_ISN+1``；
* CFIN original：位于client retransmission tree，尚未确认；
* CFIN clone：已加入CPU0 input backlog；
* ``CFIN.seq=C_ISN+6``、 ``CFIN.end_seq=C_ISN+7``；
* C socket ownership：仍由parent持有；
* C socket backlog：empty；
* ``H.sk_state=TCP_ESTABLISHED``；
* H receive queue：empty；
* next entry： ``rcu_read_unlock_bh()`` 触发CPU0 NET_RX处理CFIN。

关键边界
--------

#. fdtable先撤销fd 7，再释放最后一个file引用；协议关闭失败也不会把fd重新装回。
#. ``fput_close_sync`` 让最后一次F7释放在当前close系统调用中同步进入 ``__fput``。
#. ``inet_release`` 的 ``timeout=0`` 表示不linger等待，不等于发送RST。
#. descriptor close会检查未读receive data；本场景队列为空，所以选择FIN而不是active reset。
#. socket API shutdown mask与TCP wire state是两层状态；前者先置满，后者再进入 ``TCP_FIN_WAIT1``。
#. FIN没有payload，仍占用一个sequence number。
#. ``snd_nxt`` 与 ``write_seq`` 前进到 ``C_ISN+7``， ``snd_una`` 等待server ACK。
#. original FIN留在retransmission tree，IPv4发送的是clone。
#. loopback FIN仍经过IPv4 output、 ``lo`` 与NET_RX输入路径。
#. fd 7已经不可查，C仍需以协议对象身份完成关闭。

下一入口
--------

下一章从：

::

   __dev_queue_xmit
   → rcu_read_unlock_bh()
   → run pending NET_RX_SOFTIRQ on CPU0
   → tcp_v4_rcv(CFIN)

开始。server方向ehash会找到H；合法FIN随后推进 ``H.rcv_nxt``，把H改为 ``TCP_CLOSE_WAIT``，在receive queue留下FIN标记，并发布fd 8的EOF readiness。

资料
----

* `Linux 7.2-rc1 fs/open.c：close系统调用与同步fput <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 fs/file.c：file_close_fd_locked撤销fdtable条目 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
* `Linux 7.2-rc1 fs/file_table.c：__fput与fput_close_sync <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 net/socket.c：sock_close与__sock_release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 net/ipv4/af_inet.c：inet_release <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp.c：__tcp_close与tcp_close_state <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_output.c：tcp_send_fin与FIN发送 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_output.c>`_
* `Linux 7.2-rc1 drivers/net/loopback.c：loopback_xmit <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/net/loopback.c>`_
