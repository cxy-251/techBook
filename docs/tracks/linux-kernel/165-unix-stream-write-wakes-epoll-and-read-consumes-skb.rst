第一百六十五章：helper写入hello时，Unix stream skb怎样唤醒epoll并让read返回5？
========================================================================================

上一章结束时，parent睡眠在eventpoll ``EP.wq``，helper运行于CPU0。fd 7对应发送端socket ``B/SB/UB``，fd 6对应接收端socket ``A/SA/UA``：

::

   unix_peer(SB) = SA
   SA.receive_queue = empty
   UA.inq_len        = 0

helper执行：

.. code-block:: c

   ssize_t n = write(7, "hello", 5);

本章固定：

* 5字节数据一次复制成功；
* 不携带 ``SCM_RIGHTS``、credentials或其他control message；
* 不使用 ``MSG_OOB``、 ``MSG_PEEK``、 ``MSG_WAITALL`` 或nonblocking模式；
* send buffer和memcg预算充足；
* 5字节固定装入一个skb；
* SA未关闭receive方向，SB未关闭send方向；
* callback ``P`` 仍挂在SA的socket wait queue；
* helper完成write后阻塞在socket对象之外；
* parent随后恢复、取得一个 ``EPOLLIN`` event，并执行 ``read(6, buf, 5)``；
* 不发生signal、copy fault、scheduler race或并发reader/writer。

write怎样进入Unix stream sendmsg
--------------------------------

helper从CPL 3进入：

::

   write(7, "hello", 5)
   → __x64_sys_write
   → ksys_write
   → vfs_write
   → new_sync_write
   → socket_file_ops.write_iter
   → sock_write_iter(F7)

``sock_write_iter`` 从 ``F7->private_data`` 取出socket ``B``，建立只含用户iov iterator的 ``msghdr``，然后调用：

::

   __sock_sendmsg(B, msg)
   → unix_stream_ops.sendmsg
   → unix_stream_sendmsg(B, msg, 5)

因为fd 7是blocking file， ``msg_flags`` 不包含 ``MSG_DONTWAIT``。

发送端如何找到接收端
--------------------

``unix_stream_sendmsg`` 从 ``SB`` 读取：

::

   other = unix_peer(SB) = SA

固定状态满足：

::

   SB.sk_shutdown & SEND_SHUTDOWN == 0
   SA is not SOCK_DEAD
   SA.sk_shutdown & RCV_SHUTDOWN == 0

因此发送可以继续。这里没有地址查找、路由表、邻居表、IP header或设备队列；目标socket已经由peer pointer直接确定。

5字节怎样进入skb
----------------

send path为本次数据分配一个stream skb。固定小写入下：

::

   requested size = 5
   skb.len         = 5
   data bytes      = "hello"

``skb_copy_datagram_from_iter`` 从helper用户地址复制5字节到skb。

skb仍计入发送端的socket write-memory accounting；它的destructor会在接收端消费完后归还相关引用和内存预算。Unix domain socket虽然没有网卡传输，仍复用skb作为内核中的数据容器与accounting单位。

skb怎样排进fd 6的receive queue
------------------------------

``unix_stream_sendmsg`` 锁住peer ``SA``，再次确认peer没有死亡或关闭receive方向，然后取得 ``SA.sk_receive_queue.lock``：

::

   UA.inq_len: 0 → 5
   __skb_queue_tail(&SA.sk_receive_queue, skb)

释放receive queue lock与Unix state lock后：

::

   SA.receive_queue = { skb("hello", len=5) }

这里的队列属于接收端SA。数据没有复制到fd 6的file object，也没有直接复制进parent用户buffer。

sk_data_ready怎样触发epoll callback
-----------------------------------

数据入队后，helper调用：

::

   SA->sk_data_ready(SA)

默认socket readable通知会唤醒SA的socket wait queue。该wait queue当前含有epoll callback ``P``：

::

   A.wq.wait = { P }

callback在eventpoll自旋锁保护下检查epitem ``I``。 ``I`` 尚未位于ready list，因此：

::

   add I to EP.rdllist

随后callback唤醒 ``EP.wq`` 上的exclusive waiter ``W``：

::

   parent: TASK_INTERRUPTIBLE → TASK_RUNNING
   parent: enqueue on CPU0 runqueue

这只说明fd 6可能ready；callback本身不会读取skb，也不会向用户复制event。

helper的write怎样返回
---------------------

``unix_stream_sendmsg`` 累加：

::

   sent: 0 → 5

清理临时SCM状态后返回5。通用socket与VFS写路径继续向上返回：

::

   write(7, "hello", 5) = 5

固定调度顺序让helper随后阻塞在Unix socket对象之外，CPU0切回已被唤醒的parent。

parent恢复后为什么必须重新poll
------------------------------

parent从 ``schedule`` 返回到原来的 ``epoll_wait`` 内核栈，移除栈waiter ``W``：

::

   EP.wq = empty

``EP.rdllist`` 包含 ``I``。delivery scan调用：

::

   ep_item_poll(I)
   → vfs_poll(F6)
   → sock_poll(F6)
   → unix_poll(F6, A)

``unix_poll`` 读取：

::

   SA.receive_queue is not empty
   UA.inq_len = 5
   SA.sk_shutdown = 0

因此返回的完整mask包含：

::

   EPOLLIN | EPOLLRDNORM

socket本身仍可写，完整mask也可能带 ``EPOLLOUT`` 类bits；与registration interest相交后，用户只得到：

::

   events[0].events   = EPOLLIN
   events[0].data.u64 = 0x554E4958

registration为level-triggered，交付时queue仍非空，所以 ``I`` 被重新放回 ``EP.rdllist``。 ``epoll_wait`` 返回：

::

   epoll_wait(8, events, 1, -1) = 1

read怎样进入unix_stream_read_generic
------------------------------------

parent回到CPL 3后立即执行：

.. code-block:: c

   char buf[5];
   ssize_t r = read(6, buf, sizeof(buf));

控制流为：

::

   read(6, buf, 5)
   → __x64_sys_read
   → ksys_read
   → vfs_read
   → new_sync_read
   → socket_file_ops.read_iter
   → sock_read_iter(F6)
   → sock_recvmsg(A)
   → unix_stream_recvmsg(A)
   → unix_stream_read_generic

``sock_read_iter`` 不把fd 6当作普通文件offset stream； ``ki_pos`` 必须为0，否则返回 ``-ESPIPE``。固定调用满足要求。

为什么读取由UA.iolock串行化
--------------------------

``unix_stream_read_generic`` 取得：

::

   mutex_lock(&UA.iolock)

该mutex保证同一个Unix stream socket上的reader不会在复制用户数据时打乱receive queue顺序。

随后在Unix state lock下查看queue首部：

::

   skb = first skb("hello")
   unix_skb_len(skb) = 5

固定read size也是5，因此本次chunk为：

::

   chunk = min(5, 5) = 5

``unix_stream_read_actor`` 通过 ``skb_copy_datagram_msg`` 把：

::

   "hello"

复制到parent用户buffer。

skb怎样被完整消费
-----------------

copy成功且未使用 ``MSG_PEEK``，内核更新：

::

   UNIXCB(skb).consumed: 0 → 5
   UA.inq_len:           5 → 0

此时 ``unix_skb_len(skb)`` 变为0。内核取得receive queue lock并执行：

::

   __skb_unlink(skb, &SA.sk_receive_queue)
   consume_skb(skb)

skb destructor归还发送端write-memory accounting。最终：

::

   SA.receive_queue = empty
   UA.inq_len        = 0

这次写入恰好只形成一个skb，但Unix ``SOCK_STREAM`` 对用户暴露的是字节流语义；内核并不承诺一个write永久对应一个read或一个skb。

read为什么正好返回5
-------------------

``copied`` 已经达到请求长度：

::

   copied = 5
   remaining size = 0

读取循环结束，释放 ``UA.iolock`` 并返回：

::

   read(6, buf, 5) = 5
   buf             = "hello"

fd 6仍处于connected状态，receive方向也没有shutdown；queue为空只表示当前没有数据，不表示EOF。

为什么epitem变成stale-ready
---------------------------

``I`` 在前面的epoll delivery时已经重新进入 ``EP.rdllist``。read只修改SA的receive queue和 ``UA.inq_len``，不会主动取得eventpoll lock或移除ready membership。

所以read返回后：

::

   SA.receive_queue = empty
   SA.sk_shutdown    = 0
   EP.rdllist        = { I }

``I`` 此刻是stale-ready item。下一次 ``epoll_wait`` 必须重新调用 ``unix_poll``，才能确认fd 6已经不再具有 ``EPOLLIN`` 或 ``EPOLLRDHUP`` readiness。

本章结束状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent： ``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* helper：阻塞在Unix socket对象之外；
* helper ``write(7)`` result：5；
* first ``epoll_wait`` result：1；
* delivered event： ``EPOLLIN``、data ``0x554E4958``；
* parent ``read(6)`` result：5；
* user bytes： ``hello``；
* fd 6/7/8：open；
* ``SA/SB.sk_state=TCP_ESTABLISHED``；
* ``SA/SB.sk_shutdown=0``；
* ``SA.receive_queue=empty``、 ``UA.inq_len=0``；
* ``SB.receive_queue=empty``、 ``UB.inq_len=0``；
* callback ``P`` 仍位于 ``A.wq.wait``；
* ``EP.rbr={I}``；
* ``EP.rdllist={I}``，当前为stale-ready；
* ``EP.wq=empty``；
* next entry：parent再次执行blocking ``epoll_wait(8, events2, 1, -1)``。

关键边界
--------

#. Unix stream send通过peer pointer直接定位接收socket，不经过IP或设备层。
#. 用户数据先复制到skb，再进入peer的receive queue。
#. ``UA.inq_len`` 是接收端未消费stream字节计数，本章为0→5→0。
#. ``sk_data_ready`` 唤醒的是socket wait queue上的epoll callback。
#. callback只建立fd-level candidate readiness，真正mask由delivery时的 ``unix_poll`` 确认。
#. 一条skb或一次write不是稳定的用户消息边界。
#. ``UA.iolock`` 串行化同一socket上的stream readers。
#. 完整消费skb后才从receive queue unlink并释放其memory accounting。
#. 空receive queue不等于EOF；只有receive shutdown、error或断开状态才能让空read结束为0或错误。
#. read清空queue不会主动移除eventpoll ready membership。

下一入口
--------

parent将再次调用：

::

   epoll_wait(8, events2, 1, -1)

它会先re-poll并清除stale-ready ``I``，然后真正睡眠。helper随后执行 ``shutdown(7, SHUT_WR)``。

资料
----

* `Linux 7.2-rc1 net/socket.c：socket file write_iter/read_iter与sock_sendmsg/sock_recvmsg <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 net/unix/af_unix.c：unix_stream_sendmsg、receive queue与unix_stream_read_generic <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/unix/af_unix.c>`_
* `Linux 7.2-rc1 net/core/sock.c：socket wait queue与skb memory accounting <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：callback、ready list与level-trigger delivery <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
