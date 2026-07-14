第一百六十四章：socketpair怎样建立双向Unix stream并让parent阻塞在epoll_wait？
========================================================================================

上一章已经完成inotify与eventpoll的最终清理。本章开始一个独立运行期场景：parent与helper是同一TGID中的两个线程，共享 ``mm_struct`` 与 ``files_struct``，系统只有CPU0在线，二者均为 ``SCHED_NORMAL``。

用户代码依次执行：

.. code-block:: c

   int sv[2];
   socketpair(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0, sv);

   int epfd = epoll_create1(EPOLL_CLOEXEC);
   struct epoll_event ev = {
       .events = EPOLLIN | EPOLLRDHUP,
       .data.u64 = 0x554E4958,
   };
   epoll_ctl(epfd, EPOLL_CTL_ADD, sv[0], &ev);
   epoll_wait(epfd, events, 1, -1);

本章固定：

* fd 0至5已经占用；
* ``socketpair`` 成功返回 ``sv[0]=6``、 ``sv[1]=7``；
* fd 6和fd 7均为blocking、close-on-exec；
* fd 8是close-on-exec eventpoll file；
* fd 6对应socket ``A``、 ``struct sock SA``、 ``struct unix_sock UA``；
* fd 7对应socket ``B``、 ``struct sock SB``、 ``struct unix_sock UB``；
* 两个socket均未bind，没有pathname或abstract address；
* epoll registration为level-triggered，不使用 ``EPOLLET``、 ``EPOLLONESHOT`` 或 ``EPOLLEXCLUSIVE``；
* 不发生LSM拒绝、fd耗尽、copy fault、allocation failure、signal或并发close；
* 本章结束在parent睡眠于eventpoll wait queue，helper成为CPU0上的下一可运行线程。

socketpair为何先保留两个fd
--------------------------

x86-64 syscall入口进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_socketpair
   → __sys_socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, sv)

``__sys_socketpair`` 先从 ``type`` 中拆出：

::

   socket type = SOCK_STREAM
   flags       = SOCK_CLOEXEC

由于没有 ``SOCK_NONBLOCK``，最终file不会带 ``O_NONBLOCK``。

在创建socket对象前，内核先调用两次：

::

   get_unused_fd_flags(O_CLOEXEC)

固定fdtable状态下得到：

::

   fd1 = 6
   fd2 = 7

两个fd此时只是reserved：open bitmap与close-on-exec bitmap已经占位， ``fdt->fd[6]`` 和 ``fdt->fd[7]`` 尚未安装file pointer。

随后内核先把数字6和7写入用户 ``sv``。固定场景没有copy fault，因此继续创建对象。这里的边界是：用户数组中出现数字并不等于fd已经发布；真正发布发生在最后的 ``fd_install``。

两个Unix socket对象怎样建立
---------------------------

``sock_create`` 为AF_UNIX创建两个 ``struct socket``。 ``unix_create`` 根据 ``SOCK_STREAM`` 选择：

::

   socket ops = unix_stream_ops
   sock proto = unix_stream_proto

每次 ``unix_create1`` 都会：

::

   sk_alloc(..., PF_UNIX, ..., unix_stream_proto)
   → sock_init_data(socket, sk)
   → initialize sk_receive_queue and socket wait queue
   → initialize unix_sock state lock, iolock, bindlock and peer_wait
   → insert unbound socket into Unix socket table

因此socketpair建立前：

::

   SA receive queue = empty
   SB receive queue = empty
   SA shutdown      = 0
   SB shutdown      = 0
   unix_peer(SA)    = NULL
   unix_peer(SB)    = NULL

它们是未命名Unix sockets，不会在ext4目录中创建socket inode或目录项。

unix_socketpair怎样把两端背靠背连接
-----------------------------------

通用socket层调用：

::

   sock1->ops->socketpair(sock1, sock2)
   → unix_socketpair(A, B)

``unix_socketpair`` 先准备两份peer credentials，然后为双向peer关系增加socket references：

::

   sock_hold(SA)
   sock_hold(SB)

接着建立：

::

   unix_peer(SA) = SB
   unix_peer(SB) = SA

并把两端协议状态都改成：

::

   SA.sk_state = TCP_ESTABLISHED
   SB.sk_state = TCP_ESTABLISHED

这里的 ``TCP_ESTABLISHED`` 是Unix stream复用的socket状态常量，不代表数据经过TCP/IP、路由、网卡或网络协议栈。

固定结果为：

::

   SA <────────────────────> SB
       peer reference both directions

   SA.receive_queue = empty
   SB.receive_queue = empty

socket file怎样发布为fd 6和fd 7
------------------------------

通用层分别执行：

::

   sock_alloc_file(A, O_CLOEXEC, NULL) → F6
   sock_alloc_file(B, O_CLOEXEC, NULL) → F7

socket file使用 ``socket_file_ops``：

::

   read_iter  = sock_read_iter
   write_iter = sock_write_iter
   poll       = sock_poll
   release    = sock_close

这些file由sockfs pseudo inode承载，不是anon-inode file，也没有磁盘目录项。

最后：

::

   fd_install(6, F6)
   fd_install(7, F7)

此时共享fdtable中的parent和helper同时可见fd 6/7。syscall返回：

::

   socketpair(...) = 0
   sv[0]           = 6
   sv[1]           = 7

为什么epoll注册时fd 6还不算ready
--------------------------------

parent创建eventpoll fd 8，然后执行：

::

   epoll_ctl(8, EPOLL_CTL_ADD, 6,
             { events=EPOLLIN|EPOLLRDHUP,
               data=0x554E4958 })

``ep_insert`` 建立epitem ``I``，并通过：

::

   vfs_poll(F6)
   → sock_poll(F6)
   → unix_poll(F6, A)

安装poll callback ``P``。

``sock_poll_wait`` 把 ``P`` 挂入SA对应的socket wait queue：

::

   sk_sleep(SA) = A.wq.wait
   A.wq.wait    = { P }

初次 ``unix_poll`` 读取：

::

   SA.sk_shutdown     = 0
   SA.sk_state        = TCP_ESTABLISHED
   SA.receive_queue   = empty
   SA.sk_err          = 0

连接仍可写，所以完整poll mask可包含 ``EPOLLOUT`` 类bits；registration只关心 ``EPOLLIN|EPOLLRDHUP``，二者都没有出现。因此interest过滤结果为0：

::

   EP.rbr     = { I }
   EP.rdllist = empty
   EP.refcount: 1 → 2

``epoll_ctl`` 返回0。

parent怎样真正睡眠
------------------

parent执行：

::

   epoll_wait(8, events, 1, -1)

eventpoll在 ``EP.mtx`` 下确认ready list为空，然后建立栈wait entry ``W``：

::

   add_wait_queue_exclusive(&EP.wq, &W)

两条wait queue必须区分：

::

   A.wq.wait = { epoll callback P }
   EP.wq     = { sleeping parent W, exclusive }

parent设置：

::

   current state = TASK_INTERRUPTIBLE

随后调用scheduler并离开CPU0。固定调度顺序选择helper运行。

本章结束状态
------------

* current executor：helper；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent： ``TASK_INTERRUPTIBLE``，不在runqueue；
* helper： ``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* fd 6/7：open、blocking、close-on-exec；
* fd 8：open eventpoll、close-on-exec；
* ``unix_peer(SA)=SB``、 ``unix_peer(SB)=SA``；
* ``SA/SB.sk_state=TCP_ESTABLISHED``；
* 两端 ``sk_shutdown=0``；
* 两端receive queue为空；
* ``UA.inq_len=0``、 ``UB.inq_len=0``；
* callback ``P`` 位于 ``A.wq.wait``；
* parent waiter ``W`` 位于 ``EP.wq``；
* ``EP.rbr={I}``、 ``EP.rdllist=empty``；
* ``EP.refcount=2``；
* next entry：helper的 ``write(7, "hello", 5)``。

关键边界
--------

#. ``socketpair`` 先reserve fd并写用户数组，最后才用 ``fd_install`` 发布file。
#. fd 6/7共享同一 ``files_struct``，所以parent与helper同时可见。
#. AF_UNIX stream使用skb与socket wait queue，但不经过IP、路由或网卡。
#. 两端互相持有peer reference，且协议状态为 ``TCP_ESTABLISHED``。
#. 未命名socketpair不会在ext4中创建pathname socket文件。
#. socket file属于sockfs，不是anon_inodefs。
#. 初次poll虽然可写，但registration未请求 ``EPOLLOUT``，所以不会进入ready list。
#. epoll callback位于socket wait queue；sleeping parent位于eventpoll自己的wait queue。
#. level-triggered registration当前尚未ready。

下一入口
--------

helper将执行：

::

   write(7, "hello", 5)

数据会被复制到一个Unix stream skb，排入SA的receive queue，并通过SA的socket wait queue触发epoll callback。

资料
----

* `Linux 7.2-rc1 net/socket.c：socketpair fd reserve、socket file创建与fd_install <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 net/unix/af_unix.c：unix_create1、unix_socketpair与unix_poll <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/unix/af_unix.c>`_
* `Linux 7.2-rc1 fs/eventpoll.c：ep_insert、poll callback与epoll_wait阻塞 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventpoll.c>`_
