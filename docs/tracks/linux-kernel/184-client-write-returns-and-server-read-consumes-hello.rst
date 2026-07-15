第一百八十四章：write怎样在ACK处理后返回5，并让read(8)取出hello？
=================================================================

上一章结束时，server child H已经收到5字节，accepted fd 8已经可读；反向ACK因为parent仍持有client C而停在 ``C.sk_backlog``：

::

   client C
       snd_una       = C_ISN + 1
       snd_nxt       = C_ISN + 6
       write_seq     = C_ISN + 6
       rtx tree      = original hello skb
       sk_backlog    = ACK(C_ISN+6)
       owner         = parent

   server child H
       rcv_nxt       = C_ISN + 6
       copied_seq    = C_ISN + 1
       receive queue = one 5-byte hello skb
       readable      = true

本章先完成当前 ``write(7,"hello",5)``，再执行：

.. code-block:: c

   char buf[5];
   ssize_t n = read(8, buf, sizeof(buf));

固定两个syscall都成功，不发生signal、page fault失败、socket error或并发读写。H已经有5字节可读，因此blocking read不会进入wait queue，也不会调用scheduler。

tcp_sendmsg_locked为什么先返回5
------------------------------

``tcp_push`` 已经成功交付一个data segment。 ``tcp_sendmsg_locked`` 的 ``copied`` 为5，因此返回：

::

   tcp_sendmsg_locked(C,&msg,5) = 5

这表示五个用户字节已被TCP接受。它不以peer application是否调用read为条件。

此刻反向ACK仍在 ``C.sk_backlog``。 ``tcp_sendmsg`` 尚未把结果返回到inet/socket/VFS层，而是先执行：

::

   release_sock(C)

release_sock怎样同步处理ACK backlog
----------------------------------

``release_sock`` 不只是清除owner。发现 ``C.sk_backlog`` 非空后，它在parent process context执行：

::

   __release_sock(C)
   → detach ACK skb from C.sk_backlog
   → C.sk_backlog_rcv
   → tcp_v4_do_rcv(C,ACK)
   → tcp_rcv_established(C,ACK)

该packet没有payload，命中established pure-ACK fast path。ACK号：

::

   ack_seq = C_ISN + 6

正好确认完整hello sequence区间。

ACK怎样结束原始skb的重传身份
----------------------------

``tcp_ack`` 推进发送窗口左边界：

::

   C.snd_una : C_ISN+1 → C_ISN+6

原始hello skb已经被全部累计确认，路径把它从retransmission tree删除并释放相应write-memory accounting：

::

   C rtx tree      : one skb → empty
   C.packets_out   : 1 → 0
   retransmit timer: no outstanding data

数据发送clone早已由loopback receive路径消费；这里释放的是client为可靠重传保留的原始skb身份。

ACK不携带server data，所以：

::

   C.rcv_nxt = S_ISN + 1

保持不变。

write何时回到用户态
-------------------

ACK backlog清空后， ``release_sock`` 清除parent对C的ownership。返回值5逐层上送：

::

   tcp_sendmsg      → 5
   inet_sendmsg     → 5
   sock_write_iter  → 5
   new_sync_write   → 5
   vfs_write        → 5
   write syscall    → userspace RAX = 5

本次write没有进入 ``sk_stream_wait_memory``，没有等待ACK timer，也没有task switch。ACK恰好因为单CPU loopback在同一syscall内到达，并在 ``release_sock`` 中被同步处理；POSIX ``write=5`` 本身并不保证一般网络上的peer已经ACK。

read怎样解析accepted fd 8
------------------------

parent随后在CPU0 CPL3调用：

::

   read(8,buf,5)

通用read路径解析：

::

   fd 8 → F8
   F8.private_data → AS
   AS.sk → H

F8是blocking socket file， ``sock_read_iter`` 构造destination iterator，没有设置 ``MSG_DONTWAIT``：

::

   sock_read_iter
   → sock_recvmsg(AS,&msg,0)
   → inet_recvmsg
   → tcp_recvmsg(H,&msg,5,0)

``tcp_recvmsg`` 执行 ``lock_sock(H)``。NET_RX已经完成，H没有socket backlog需要先处理。

为什么blocking read不会睡眠
--------------------------

``tcp_recvmsg_locked`` 使用：

::

   seq    = &H.copied_seq
   target = sock_rcvlowat(H,flags=0,len=5)

默认 ``SO_RCVLOWAT`` 为1，receive queue head已经存在。循环直接找到：

::

   skb.seq     = C_ISN + 1
   skb.end_seq = C_ISN + 6
   skb.len     = 5
   offset      = H.copied_seq - skb.seq = 0
   used        = min(5,5) = 5

所以不会执行 ``sk_wait_data``，parent保持 ``TASK_RUNNING``。

hello怎样复制到用户buf
---------------------

路径调用：

::

   skb_copy_datagram_msg(skb,offset=0,&msg,used=5)

发送端payload位于skb page fragment，通用datagram copy能够从linear area或frags复制。用户 ``buf`` 最终得到：

::

   buf[0..4] = 68 65 6c 6c 6f = "hello"

随后更新消费位置：

::

   H.copied_seq : C_ISN+1 → C_ISN+6
   copied       : 0 → 5
   remaining len: 5 → 0

整个skb已经消费， ``tcp_eat_recv_skb`` 把它从 ``H.sk_receive_queue`` 移除并释放receive-memory accounting。

read之后为什么不再发送ACK
-------------------------

上一章的第一-data quickack已经发送：

::

   ACK = C_ISN + 6

并在client C中完成处理。 ``tcp_send_ack`` 已清除scheduled ACK状态。 ``tcp_recvmsg_locked`` 末尾仍调用：

::

   tcp_cleanup_rbuf(H,copied=5)

但当前没有待处理ACK，也没有需要显著扩大advertised window的条件，因此本次read不再构造第二个pure ACK。

这一点依赖本批固定的“首个data触发quickack”时序；如果ACK被delayed，读空带PSH skb可能促使 ``tcp_cleanup_rbuf`` 立即发送它。

read怎样返回5
-------------

``tcp_recvmsg_locked`` 返回copied=5， ``tcp_recvmsg`` 释放H socket lock。结果逐层返回：

::

   tcp_recvmsg      → 5
   inet_recvmsg     → 5
   sock_read_iter   → 5
   new_sync_read    → 5
   vfs_read         → 5
   read syscall     → userspace RAX = 5

返回后 ``buf`` 包含完整 ``hello``，H仍然TCP_ESTABLISHED，只是当前receive queue为空。

数据传递改变了哪些状态
----------------------

本批完成的可靠字节流状态为：

::

   client C
       snd_una   = C_ISN + 6
       snd_nxt   = C_ISN + 6
       write_seq = C_ISN + 6
       rtx tree  = empty

   server H
       rcv_nxt    = C_ISN + 6
       copied_seq = C_ISN + 6
       recv queue = empty

TCP连接、四元组、route、ehash和bind ownership全部保留。listener L没有参与这次数据传递，fd 6的accept queue继续为空。

固定源码依据
------------

以下链接全部固定到 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d``：

* `net/core/sock.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_： ``release_sock`` 与 ``__release_sock`` backlog处理；
* `net/ipv4/tcp_input.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_input.c>`_：pure ACK fast path与 ``tcp_ack``；
* `net/socket.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_： ``sock_read_iter`` 与 ``sock_recvmsg``；
* `net/ipv4/af_inet.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_： ``inet_recvmsg``；
* `net/ipv4/tcp.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp.c>`_： ``tcp_sendmsg``、 ``tcp_recvmsg``、 ``tcp_recvmsg_locked``、 ``tcp_eat_recv_skb`` 与 ``tcp_cleanup_rbuf``；
* `fs/read_write.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/read_write.c>`_： ``ksys_read``、 ``vfs_read`` 与 ``new_sync_read``。

本章结束状态
------------

::

   system_state              = SYSTEM_RUNNING
   current executor          = parent
   CPU/mode                  = CPU0, x86-64 CPL 3
   last syscall/result       = read(8,buf,5) = 5
   parent state              = TASK_RUNNING
   write schedule count      = 0
   read schedule count       = 0
   user buffer               = "hello"

   fd 6                      = open, blocking, close-on-exec
   listener L                = TCP_LISTEN
   L endpoint                = 127.0.0.1:28080
   L accept queue            = empty
   L.sk_ack_backlog          = 0

   fd 7                      = open, blocking, close-on-exec
   client C                  = TCP_ESTABLISHED
   C.snd_una/snd_nxt         = C_ISN+6 / C_ISN+6
   C.write_seq               = C_ISN+6
   C.rcv_nxt                 = S_ISN+1
   C write/rtx/backlog       = empty / empty / empty

   fd 8                      = open, blocking, close-on-exec
   server child H            = TCP_ESTABLISHED
   H.rcv_nxt/copied_seq      = C_ISN+6 / C_ISN+6
   H.snd_una/snd_nxt         = S_ISN+1 / S_ISN+1
   H receive queue           = empty
   fd 8 readable bytes       = 0

   packet/softirq backlog    = empty
   next entry                = close(7)

下一批从client ``close(7)`` 开始，追踪active close怎样发送FIN、让H进入CLOSE_WAIT并使fd 8在数据读尽后观察EOF。
