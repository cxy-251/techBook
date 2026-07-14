第一百六十六章：shutdown(SHUT_WR)怎样让peer收到EPOLLRDHUP并让read返回EOF？
========================================================================================

上一章结束时，parent已经读完 ``hello``：

::

   SA.receive_queue = empty
   UA.inq_len        = 0
   SA.sk_shutdown    = 0
   SB.sk_shutdown    = 0
   EP.rdllist        = { stale-ready I }

fd 6、fd 7和eventpoll fd 8都仍然open。parent再次执行：

.. code-block:: c

   int n = epoll_wait(8, events2, 1, -1);

helper随后执行：

.. code-block:: c

   shutdown(7, SHUT_WR);

本章固定：

* parent第二次 ``epoll_wait`` 使用无限timeout；
* stale-ready item先被re-poll清除，parent确实进入睡眠；
* helper只关闭fd 7的send方向，不关闭file descriptor；
* helper不再向fd 7写数据；
* fd 6 receive queue在shutdown发生前为空；
* 不发生signal、copy fault、close race或额外socket operation；
* parent被唤醒后得到 ``EPOLLIN|EPOLLRDHUP``，再执行 ``read(6, buf, 5)``；
* 本章不执行 ``EPOLL_CTL_DEL`` 或close。

第二次epoll_wait怎样先清除stale-ready
------------------------------------

parent进入eventpoll时， ``I`` 已在ready list中，所以先进入delivery scan：

::

   ep_item_poll(I)
   → vfs_poll(F6)
   → sock_poll(F6)
   → unix_poll(F6, A)

``unix_poll`` 看到：

::

   SA.receive_queue = empty
   SA.sk_shutdown    = 0
   SA.sk_state       = TCP_ESTABLISHED
   SA.sk_err         = 0

完整poll mask仍包含可写bits，但registration只关心 ``EPOLLIN|EPOLLRDHUP``。过滤后：

::

   revents = 0

因此本次scan不向用户复制event，也不把 ``I`` 重新放回ready list：

::

   EP.rdllist: { I } → empty

因为timeout为无限且当前没有ready item，eventpoll建立第二个exclusive栈waiter ``W2``：

::

   EP.wq = { W2 }
   parent state = TASK_INTERRUPTIBLE

parent调用scheduler并离开CPU0。固定调度顺序选择helper运行。

shutdown syscall怎样找到fd 7的socket
------------------------------------

helper执行：

::

   shutdown(7, SHUT_WR)
   → __x64_sys_shutdown
   → __sys_shutdown(7, SHUT_WR)

通用socket层从共享fdtable取得 ``F7``，再通过 ``sock_from_file`` 得到socket ``B``。LSM检查成功后：

::

   B->ops->shutdown(B, SHUT_WR)
   → unix_shutdown(B, SHUT_WR)

``shutdown`` 不从fdtable撤销fd 7，也不下降 ``F7`` reference。它只改变socket方向状态。

SHUT_WR怎样映射为SEND_SHUTDOWN
------------------------------

``unix_shutdown`` 验证mode后执行内部映射：

::

   userspace SHUT_WR = 1
   internal mode     = 2 = SEND_SHUTDOWN

它锁住本端 ``SB`` 并更新：

::

   SB.sk_shutdown: 0 → SEND_SHUTDOWN

同时读取并临时持有peer：

::

   other = unix_peer(SB) = SA
   sock_hold(SA)

释放本端state lock后，fd 7的未来send path会在 ``unix_stream_sendmsg`` 开头看到 ``SEND_SHUTDOWN``。若再次write且未设置 ``MSG_NOSIGNAL``，固定语义将是 ``-EPIPE`` 并可能产生 ``SIGPIPE``；本章不执行该写入。

为什么peer得到RCV_SHUTDOWN
--------------------------

Unix stream是全双工连接。关闭B的send方向，意味着A的receive方向以后不会再得到来自B的新字节。

``unix_shutdown`` 为peer计算：

::

   local mode contains SEND_SHUTDOWN
   → peer_mode contains RCV_SHUTDOWN

在SA的Unix state lock下更新：

::

   SA.sk_shutdown: 0 → RCV_SHUTDOWN

重要边界是：

::

   SA.sk_state remains TCP_ESTABLISHED
   SB.sk_state remains TCP_ESTABLISHED
   unix_peer(SA) remains SB
   unix_peer(SB) remains SA

这是half-close，不是disconnect或final close。

sk_state_change怎样唤醒epoll
----------------------------

更新peer shutdown bit后， ``unix_shutdown`` 调用：

::

   SA->sk_state_change(SA)

socket state-change通知唤醒SA的socket wait queue。该wait queue仍包含epoll callback ``P``：

::

   A.wq.wait = { P }

上一节已经清除了 ``EP.rdllist``，所以callback可以重新链接 ``I``：

::

   EP.rdllist: empty → { I }

随后callback唤醒 ``EP.wq`` 上的 ``W2``：

::

   parent: TASK_INTERRUPTIBLE → TASK_RUNNING
   parent: enqueue on CPU0 runqueue

helper自己的socket ``B`` 也执行本端state-change通知；本场景没有epoll registration监视fd 7，因此不会生成第二个epitem。

shutdown怎样返回
----------------

peer更新完成后，临时 ``sock_hold(SA)`` reference由 ``sock_put(SA)`` 归还。syscall返回：

::

   shutdown(7, SHUT_WR) = 0

fd 7仍open，仍可从fd 7读取由fd 6发送的数据；只有fd 7向fd 6发送的方向被关闭。

固定调度顺序让helper随后阻塞在socket对象之外，CPU0恢复parent。

parent为什么同时看到EPOLLIN和EPOLLRDHUP
--------------------------------------

parent从scheduler返回，移除 ``W2`` 并扫描 ``I``。 ``unix_poll`` 读取：

::

   SA.sk_shutdown & RCV_SHUTDOWN != 0
   SA.receive_queue = empty
   SA.sk_state = TCP_ESTABLISHED

对Unix socket，receive shutdown直接产生：

::

   EPOLLRDHUP | EPOLLIN | EPOLLRDNORM

这里同时报告 ``EPOLLIN``，是为了让传统只监听readable的程序也能调用read并取得EOF； ``EPOLLRDHUP`` 则显式表示peer关闭了写方向。

与registration interest相交后：

::

   events2[0].events   = EPOLLIN | EPOLLRDHUP
   events2[0].data.u64 = 0x554E4958

没有 ``EPOLLHUP``，因为：

::

   SA.sk_shutdown != SHUTDOWN_MASK
   SA.sk_state    != TCP_CLOSE

连接只完成单向half-close。

level-triggered ``I`` 在交付后重新进入 ``EP.rdllist``。第二次 ``epoll_wait`` 返回：

::

   epoll_wait(8, events2, 1, -1) = 1

空queue上的read为什么返回0
-------------------------

parent随后执行：

.. code-block:: c

   char buf[5];
   ssize_t r = read(6, buf, sizeof(buf));

控制流再次进入：

::

   sock_read_iter
   → sock_recvmsg
   → unix_stream_recvmsg
   → unix_stream_read_generic

读取循环在 ``UA.iolock`` 和SA state lock保护下观察：

::

   skb_peek(&SA.sk_receive_queue) = NULL
   copied                         = 0
   SA.sk_shutdown & RCV_SHUTDOWN  = true

代码按POSIX规定的顺序先检查socket error，再检查receive shutdown。没有error，因此遇到 ``RCV_SHUTDOWN`` 后直接退出，不进入 ``unix_stream_data_wait``，也不调度睡眠。

最终：

::

   copied = 0
   err    = 0
   return copied ? : err
   → return 0

用户看到：

::

   read(6, buf, 5) = 0

这就是stream EOF。EOF不是一条零长度skb；receive queue中没有任何skb，返回0来自持久的 ``RCV_SHUTDOWN`` 状态。

为什么read后epitem仍然真正ready
------------------------------

第一次数据读取后，ready item变成stale，是因为queue被清空。当前read EOF不会清除：

::

   SA.sk_shutdown & RCV_SHUTDOWN

所以即使再次调用 ``epoll_wait``， ``unix_poll`` 仍返回 ``EPOLLIN|EPOLLRDHUP``。level-triggered ``I`` 现在不是stale-ready，而是persistent-ready：

::

   EP.rdllist = { I }

要停止这类重复交付，需要删除registration、关闭fd 6，或者改变对象生命周期；read EOF本身不会“消费”RDHUP状态。

完整控制流
----------

本章可以压缩为：

::

   parent epoll_wait(8, events2, 1, -1)
   → re-poll stale I
   → queue empty and shutdown=0
   → remove I from ready list
   → parent joins EP.wq and sleeps

   helper shutdown(7, SHUT_WR)
   → SB.sk_shutdown |= SEND_SHUTDOWN
   → SA.sk_shutdown |= RCV_SHUTDOWN
   → SA.sk_state_change
   → callback P links I to EP.rdllist
   → wake parent
   → shutdown returns 0

   parent resumes epoll_wait
   → unix_poll sees RCV_SHUTDOWN
   → deliver EPOLLIN|EPOLLRDHUP
   → level I requeues
   → epoll_wait returns 1

   parent read(6)
   → queue empty
   → RCV_SHUTDOWN detected
   → return EOF 0

本章结束状态
------------

* ``system_state``： ``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent： ``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* helper：blocked outside socket objects；
* ``shutdown(7, SHUT_WR)`` result：0；
* second ``epoll_wait`` result：1；
* delivered event： ``EPOLLIN|EPOLLRDHUP``、data ``0x554E4958``；
* final ``read(6)`` result/RAX：0；
* fd 6/7/8：open；
* ``SA.sk_state=TCP_ESTABLISHED``；
* ``SB.sk_state=TCP_ESTABLISHED``；
* ``SA.sk_shutdown=RCV_SHUTDOWN``；
* ``SB.sk_shutdown=SEND_SHUTDOWN``；
* ``unix_peer(SA)=SB``、 ``unix_peer(SB)=SA``；
* 两端receive queue均为空；
* ``UA.inq_len=0``、 ``UB.inq_len=0``；
* callback ``P`` 仍位于 ``A.wq.wait``；
* ``EP.rbr={I}``；
* ``EP.rdllist={I}``，persistent-ready；
* ``EP.wq=empty``；
* fd 6向fd 7的send方向仍可用；
* fd 7从fd 6接收的方向仍可用；
* fd 7向fd 6的send方向已经关闭；
* filesystem/block/device I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. 第二次epoll_wait先re-poll stale item，再真正进入睡眠，避免把旧ready membership误当成shutdown wake。
#. ``shutdown`` 改变方向状态，不撤销fd，也不释放socket file。
#. ``SHUT_WR`` 在本端设置 ``SEND_SHUTDOWN``，在peer设置 ``RCV_SHUTDOWN``。
#. half-close不清除peer pointers，也不把 ``sk_state`` 改成 ``TCP_CLOSE``。
#. peer的 ``sk_state_change`` 通过socket wait queue触发epoll callback。
#. ``RCV_SHUTDOWN`` 让Unix poll同时报告 ``EPOLLIN|EPOLLRDHUP``。
#. 单向half-close不产生 ``EPOLLHUP``；完整shutdown或close语义不同。
#. empty queue加 ``RCV_SHUTDOWN`` 使stream read返回0，不再阻塞。
#. EOF不是队列中的零长度skb，而是socket shutdown state的结果。
#. level-triggered RDHUP是persistent readiness，read EOF不会消费它。
#. 当前没有经过IP、网卡、文件系统或块设备I/O。

下一任务
--------

优先接续Unix socketpair cleanup：

::

   epoll_ctl(8, EPOLL_CTL_DEL, 6, NULL)
   → detach callback and epitem
   close(6)
   → peer fd 7 observes full disconnect/HUP state transition
   close(7)
   close(8)
   → release both sockfs files, Unix socket objects and eventpoll

开始前需要固定close顺序、peer ``sk_shutdown`` / ``sk_state`` 更新、receive queue清理、peer references、sockfs inode与eventpoll RCU释放边界。

资料
----

* `Linux 7.2-rc1 net/socket.c：shutdown syscall、socket file read与poll分派 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 net/unix/af_unix.c：unix_shutdown、unix_poll与空queue EOF判断 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/unix/af_unix.c>`_
* `Linux 7.2-rc1 net/core/sock.c：socket state-change与wait queue wakeup <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：stale-ready re-poll、callback与level-trigger requeue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
