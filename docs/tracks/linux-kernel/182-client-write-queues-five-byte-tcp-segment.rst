第一百八十二章：write(7,"hello",5)怎样把5字节排入client TCP write queue？
============================================================================

上一章结束时，parent已经完成 ``accept4``，三个fd都在CPU0上的同一进程中保持open：

::

   fd 6 → F6 → S  → listener L
   fd 7 → F7 → CS → client C
   fd 8 → F8 → AS → server child H

   C = 127.0.0.1:40000 → 127.0.0.1:28080, TCP_ESTABLISHED
   H = 127.0.0.1:28080 ← 127.0.0.1:40000, TCP_ESTABLISHED

双方都已完成三次握手，TCP数据队列为空：

::

   C.snd_una = C.snd_nxt = C.write_seq = C_ISN + 1
   C.rcv_nxt = S_ISN + 1
   C write queue = empty
   C retransmission tree = empty

   H.snd_una = H.snd_nxt = H.write_seq = S_ISN + 1
   H.rcv_nxt = H.copied_seq = C_ISN + 1
   H receive queue = empty

本章从：

.. code-block:: c

   ssize_t n = write(7, "hello", 5);

开始，追踪fd 7怎样解析到client C、 ``tcp_sendmsg_locked`` 怎样建立一个5字节skb，并把它交给 ``tcp_write_xmit``。叙事停在数据segment即将进入IPv4 output的位置。

固定调用没有 ``MSG_MORE``、 ``MSG_OOB``、zerocopy或splice；client没有启用 ``TCP_CORK``、 ``TCP_NODELAY`` 或自定义低水位。内存、route、cgroup、LSM和BPF检查全部成功，不发生send-buffer等待。

write怎样找到client socket
--------------------------

x86-64 syscall入口沿已经完成的通用write路径取得fd 7对应的file：

::

   write(7,"hello",5)
   → ksys_write
   → fdget_pos(7)
   → F7
   → vfs_write(F7,...,5)
   → new_sync_write
   → F7.f_op->write_iter

F7是sockfs file，所以：

::

   F7.f_op = socket_file_ops
   write_iter = sock_write_iter

``sock_write_iter`` 从：

::

   F7.private_data = CS

取得client ``struct socket``。F7是blocking，当前调用也没有 ``IOCB_NOWAIT``，因此新建的 ``msghdr`` 不含 ``MSG_DONTWAIT``。

这里解析的是fd 7，不是accepted fd 8。数据发送者始终是client C。

socket层怎样进入TCP sendmsg
---------------------------

``sock_write_iter`` 把用户iov包装成：

::

   msg.msg_iter  = source iterator over "hello"
   msg.msg_flags = 0
   remaining     = 5

随后调用：

::

   __sock_sendmsg(CS,&msg)
   → security_socket_sendmsg
   → sock_sendmsg_nosec
   → CS.ops->sendmsg
   → inet_sendmsg(CS,&msg,5)

``inet_send_prepare`` 看见client早已绑定本地端口40000，不需要再次autobind。 ``inet_sendmsg`` 通过：

::

   C.sk_prot = tcp_prot

进入：

::

   tcp_sendmsg(C,&msg,5)

``tcp_sendmsg`` 先执行：

::

   lock_sock(C)

从这里直到本次send结束，parent拥有client socket C。后续从loopback返回的ACK如果在此期间到达，不能直接进入C的TCP状态机，只能先进入 ``C.sk_backlog``。

为什么不需要等待连接或发送空间
------------------------------

``tcp_sendmsg_locked`` 首先读取flags并计算blocking send timeout。固定状态满足：

::

   C.sk_state = TCP_ESTABLISHED
   C.sk_err = 0
   C.sk_shutdown & SEND_SHUTDOWN = 0
   send memory available = true
   route/dst = active loopback route

因此不会调用 ``sk_stream_wait_connect``，也不会进入 ``sk_stream_wait_memory``。

``tcp_send_mss`` 取得当前路径允许的MSS和size goal。握手记录的MSS足以容纳5字节；timestamp等TCP option会影响当前header与payload上限，却不会让本次数据分段。

本场景只生成一个数据skb。

tcp_stream_alloc_skb怎样建立空segment
------------------------------------

write queue与retransmission tree都为空，所以 ``tcp_sendmsg_locked`` 不能复用tail skb，进入 ``new_segment``：

::

   first_skb = true
   skb = tcp_stream_alloc_skb(C,...,first_skb=true)
   tcp_skb_entail(C,skb)

``tcp_skb_entail`` 用发送序列当前位置初始化control block：

::

   skb.seq       = C_ISN + 1
   skb.end_seq   = C_ISN + 1
   skb.tcp_flags = ACK

随后把空skb加入C的write queue，并计入socket write-memory accounting。此时它还没有payload，尚未进入retransmission tree，也没有发送clone。

hello怎样复制进skb frag
-----------------------

普通 ``write`` 没有zerocopy标志，路径使用socket page fragment：

::

   sk_page_frag_refill
   → tcp_wmem_schedule(C,5)
   → skb_copy_to_page_nocache(...,5)

用户空间的五个字节：

::

   68 65 6c 6c 6f

被复制到skb引用的page fragment。随后发送序列状态推进：

::

   C.write_seq : C_ISN+1 → C_ISN+6
   skb.end_seq : C_ISN+1 → C_ISN+6
   copied      : 0 → 5

``snd_nxt`` 此时仍是 ``C_ISN+1``。 ``write_seq`` 表示已经排入发送流的末端， ``snd_nxt`` 要在skb真正交给发送路径后才推进。

为什么这个skb带PSH
-------------------

五个字节已经耗尽 ``msg_iter``，路径进入 ``out`` 并调用：

::

   tcp_push(C, flags=0, mss_now, C.nonagle, size_goal)

因为没有 ``MSG_MORE``， ``tcp_push`` 调用 ``tcp_mark_push``：

::

   skb.tcp_flags |= PSH
   C.pushed_seq   = C.write_seq = C_ISN+6

最终control flags为：

::

   ACK | PSH

PSH不额外占用TCP sequence number。payload的sequence区间仍是：

::

   [C_ISN+1, C_ISN+6)

Nagle为什么不会扣住这5字节
--------------------------

固定client没有 ``TCP_CORK`` 或 ``MSG_MORE``，write之前也没有未确认的数据：

::

   C.packets_out = 0
   C retransmission tree = empty

因此即使默认启用Nagle，小segment也不需要等待旧数据ACK。autocork条件同样要求已有发送中的数据，本场景不成立。

``tcp_push`` 立即进入：

::

   __tcp_push_pending_frames
   → tcp_write_xmit

tcp_write_xmit怎样发布发送身份
-----------------------------

``tcp_write_xmit`` 检查pacing、congestion window、peer receive window、Nagle和small-queue条件。固定全部允许一个segment发送。

它调用：

::

   tcp_transmit_skb(C,skb,clone_it=1,...)

原始skb必须保留给重传体系，所以 ``__tcp_transmit_skb`` 创建发送clone，在clone前部构造TCP header：

::

   source port = 40000
   dest port   = 28080
   seq         = C_ISN + 1
   ack_seq     = S_ISN + 1
   flags       = ACK | PSH
   payload len = 5

timestamp option沿用已协商状态；没有SYN、FIN、RST或URG。

发送clone即将通过：

::

   ip_queue_xmit(C,clone,...)

进入IPv4 output。该调用返回后， ``tcp_event_new_data_sent`` 才会把原始skb从write queue移动到retransmission tree，并把 ``C.snd_nxt`` 推进到 ``C_ISN+6``。

固定源码依据
------------

以下链接全部固定到 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d``：

* `fs/read_write.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_： ``ksys_write``、 ``vfs_write`` 与 ``new_sync_write``；
* `net/socket.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_： ``sock_write_iter`` 与socket file发送分派；
* `net/ipv4/af_inet.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_： ``inet_send_prepare`` 与 ``inet_sendmsg``；
* `net/ipv4/tcp.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp.c>`_： ``tcp_sendmsg``、 ``tcp_sendmsg_locked``、 ``tcp_skb_entail`` 与 ``tcp_push``；
* `net/ipv4/tcp_output.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_output.c>`_： ``tcp_write_xmit`` 与 ``__tcp_transmit_skb``。

本章结束状态
------------

::

   current executor          = parent
   CPU/mode                  = CPU0, x86-64 kernel process context
   current syscall           = write(7,"hello",5)
   client socket owner       = parent

   client C                  = TCP_ESTABLISHED
   C.snd_una                 = C_ISN + 1
   C.write_seq               = C_ISN + 6
   C.rcv_nxt                 = S_ISN + 1
   data skb seq/end          = C_ISN+1 / C_ISN+6
   data skb flags            = ACK | PSH
   data skb payload          = "hello"

   server child H            = TCP_ESTABLISHED
   H.rcv_nxt                 = C_ISN + 1
   H.copied_seq              = C_ISN + 1
   H receive queue           = empty

   next entry                = ip_queue_xmit(C,data clone,...)

下一章从 ``ip_queue_xmit`` 开始，追踪数据segment通过IPv4 output与 ``lo`` 命中H、排入H receive queue、触发fd 8可读并发送ACK。
