第一百七十章：socket(AF_INET,SOCK_STREAM)怎样创建TCP endpoint并发布fd 6？
============================================================

上一章已经释放Unix socketpair与eventpoll。parent仍在CPU0的用户态运行，fd 0至5保持占用，fd 6至8重新空闲。本章开始一个独立的TCP/IPv4 loopback场景，只执行服务器端的第一条调用：

.. code-block:: c

   int server_fd = socket(AF_INET,
                          SOCK_STREAM | SOCK_CLOEXEC,
                          0);

接下来将依次执行 ``bind(127.0.0.1:28080)`` 与 ``listen(8)``。本章只追踪 ``socket()``，不提前进入地址绑定、监听哈希或三次握手。

本章固定：

* current network namespace为本场景唯一使用的network namespace ``N``；
* loopback device ``lo`` 已经UP， ``127.0.0.1/8`` 与local route已经存在；
* fd 0至5占用，fd 6是最低可用描述符；
* ``SOCK_CLOEXEC`` 生效，不设置 ``SOCK_NONBLOCK``；
* protocol参数为0，由AF_INET按 ``SOCK_STREAM`` 选择TCP；
* 不发生LSM、cgroup BPF或socket-create hook拒绝；
* 不发生fd耗尽、inode耗尽、slab分配失败或module加载；
* 当前没有并发close、fork、exec、signal或另一个线程访问新socket；
* 本章结束时只创建未绑定TCP endpoint，不产生route lookup、skb或设备I/O。

socket syscall怎样进入通用socket层
----------------------------------

x86-64用户态执行 ``socket`` 后，控制流进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_socket
   → __sys_socket(AF_INET,
                  SOCK_STREAM|SOCK_CLOEXEC,
                  0)

``__sys_socket`` 先调用：

::

   __sys_socket_create(family, type, protocol)

这里的 ``type`` 同时携带socket类型与创建flags。通用层验证：

::

   family = AF_INET
   type bits = SOCK_STREAM
   flags = SOCK_CLOEXEC
   protocol = 0

``SOCK_CLOEXEC`` 与 ``SOCK_NONBLOCK`` 不属于 ``SOCK_TYPE_MASK``。验证通过后， ``__sys_socket_create`` 把type收缩为纯 ``SOCK_STREAM``，再调用：

::

   sock_create(AF_INET, SOCK_STREAM, 0, &server_socket)
   → __sock_create(N, AF_INET, SOCK_STREAM, 0, ...)

因此协议族创建函数看到的是纯socket类型；close-on-exec信息留在通用syscall层，稍后用于fd发布。

sock_alloc怎样建立sockfs inode与struct socket
---------------------------------------------

``__sock_create`` 先经过socket-create安全检查，然后调用：

::

   sock_alloc()
   → new_inode_pseudo(sock_mnt->mnt_sb)
   → SOCKET_I(inode)

``sock_alloc`` 从全局sockfs superblock取得一个pseudo inode。 ``struct socket`` 嵌在sockfs私有inode对象中，因此本章建立的第一层对象是：

::

   sockfs inode IS
       └── struct socket S

初始化后的inode具有：

::

   i_mode = S_IFSOCK | S_IRWXUGO
   i_uid  = current_fsuid()
   i_gid  = current_fsgid()
   i_op   = sockfs_inode_ops

这里没有在ext4目录树创建pathname、dentry名称或磁盘inode。sockfs只为VFS file与socket对象提供内核中的承载关系。

``__sock_create`` 随后记录：

::

   S.type = SOCK_STREAM

此时 ``S`` 还没有协议私有的 ``struct sock``，也没有file或数字fd。

AF_INET怎样把protocol 0解析成TCP
-------------------------------

``__sock_create`` 在 ``net_families[AF_INET]`` 中找到：

::

   inet_family_ops
       .create = inet_create

于是调用：

::

   inet_create(N, S, protocol=0, kern=0)

``inet_create`` 先设置socket层状态：

::

   S.state = SS_UNCONNECTED

随后遍历 ``inetsw[SOCK_STREAM]``。固定内核注册的永久条目为：

::

   type     = SOCK_STREAM
   protocol = IPPROTO_TCP
   prot     = tcp_prot
   ops      = inet_stream_ops
   flags    = INET_PROTOSW_PERMANENT | INET_PROTOSW_ICSK

用户传入 ``protocol=0``，即 ``IPPROTO_IP`` 通配选择，因此命中该TCP条目，并把解析后的protocol改为：

::

   protocol = IPPROTO_TCP

``inet_create`` 随后建立两条分派关系：

::

   S.ops = &inet_stream_ops
   L.sk_prot = &tcp_prot

其中 ``inet_stream_ops`` 负责socket API层的bind、listen、connect、accept与poll； ``tcp_prot`` 负责TCP控制块、端口、hash、send/receive与close。

sk_alloc怎样分配完整tcp_sock
----------------------------

TCP的 ``proto.obj_size`` 是 ``sizeof(struct tcp_sock)``。 ``inet_create`` 调用：

::

   sk_alloc(N, PF_INET, GFP_KERNEL, &tcp_prot, kern=0)

得到协议对象 ``L``。从类型关系看：

::

   struct tcp_sock LTP
       contains struct inet_connection_sock LICSK
       contains struct inet_sock LINET
       contains struct sock L

所以 ``L``、 ``LINET``、 ``LICSK`` 与 ``LTP`` 不是四次独立分配，而是同一块TCP协议对象的不同结构视图。

``inet_create`` 因 ``INET_PROTOSW_ICSK`` 初始化connection-socket锁与相关基础成员，然后调用：

::

   sock_init_data(S, L)

该步骤把VFS/socket层对象与协议对象双向连接：

::

   S.sk       = L
   L.sk_socket = S

同时初始化socket wait queue、receive queue、write queue、error queue、backlog与默认callbacks，并把新协议socket置于未连接关闭态：

::

   L.sk_state    = TCP_CLOSE
   L.sk_shutdown = 0
   L.sk_err      = 0

这里的 ``TCP_CLOSE`` 只说明TCP协议状态尚未进入监听或连接状态，不表示对象已经执行close或进入析构。在当前时点它同时尚未bind；下一章bind成功后，协议状态仍会保持 ``TCP_CLOSE``。

TCP初始化建立了哪些尚未使用的状态
--------------------------------

``inet_create`` 继续设置：

::

   L.sk_destruct   = inet_sock_destruct
   L.sk_protocol   = IPPROTO_TCP
   L.sk_backlog_rcv = tcp_v4_do_rcv

随后通过：

::

   tcp_prot.init(L)
   → tcp_v4_init_sock(L)
   → tcp_init_sock(L)

初始化TCP传输状态，包括：

* retransmission、delayed-ACK与keepalive相关timer基础状态；
* out-of-order tree与retransmission tree；
* 初始RTO、初始拥塞窗口与默认MSS；
* TCP congestion-control指针；
* 默认send/receive buffer；
* stream write-space callback；
* IPv4-specific发送、连接请求与child创建operations；
* TCP socket allocation accounting。

本章尚未建立连接，因此以下身份仍为空：

::

   LINET.inet_num       = 0
   LINET.inet_sport     = 0
   LINET.inet_rcv_saddr = 0
   LINET.inet_saddr     = 0
   LINET.inet_daddr     = 0
   LINET.inet_dport     = 0

``LICSK.icsk_bind_hash`` 与 ``icsk_bind2_hash`` 也仍为NULL。 ``L`` 不在TCP bind hash、listener hash或established hash中。

为什么socket对象完成后才保留fd
-----------------------------

``inet_create`` 成功返回后， ``__sock_create`` 完成protocol module reference与post-create安全检查，把 ``S`` 返回给 ``__sys_socket``。

与 ``socketpair`` 先reserve两个fd不同，单个 ``socket`` 到这里才调用：

::

   sock_map_fd(S, O_CLOEXEC)

``sock_map_fd`` 首先执行：

::

   get_unused_fd_flags(O_CLOEXEC) → 6

共享fdtable此时为数字6建立reserved位置，并设置close-on-exec bitmap。这个阶段：

::

   open_fds bit 6      = 1
   close_on_exec bit 6 = 1
   fdt->fd[6]          = NULL

``O_CLOEXEC`` 是fdtable属性，不会作为普通file status flag写入 ``F6.f_flags``。

sock_alloc_file怎样建立F6
-------------------------

``sock_map_fd`` 接着调用：

::

   sock_alloc_file(S, O_CLOEXEC, NULL)
   → alloc_file_pseudo(IS, sock_mnt, "TCP",
                       O_RDWR,
                       &socket_file_ops)

由于本章没有 ``SOCK_NONBLOCK``，创建出的file是blocking socket file。形成对象链：

::

   fd 6 → F6 → S → L/LINET/LICSK/LTP
                ↘ sockfs inode IS

关键连接为：

::

   S.file          = F6
   F6.private_data = S
   F6.f_op         = socket_file_ops

``socket_file_ops`` 的read、write、poll与release最终继续分派到 ``S.ops=inet_stream_ops`` 和 ``L.sk_prot=tcp_prot``。

最后执行：

::

   fd_install(6, F6)

release语义保证reserved fd 6在file完全建立后才发布。此刻：

::

   fdt->fd[6] = F6

parent以及任何共享同一 ``files_struct`` 的线程现在才能通过数字6取得该file。

socket返回时为什么没有网络数据包
-------------------------------

本章只完成对象创建与fd发布。没有调用：

* ``bind``，所以未验证本地地址或占用端口；
* ``listen``，所以未初始化request/accept queue，也未进入listener hash；
* ``connect``，所以未查路由、选择源端口或建立四元组；
* ``sendmsg``，所以没有分配数据skb；
* 网络设备发送入口，所以 ``lo`` 没有接收任何本章生成的packet。

``lo``、local route与TCP hash tables已经在系统中存在，只是新建的 ``L`` 尚未加入对应运行期结构。

本章结束状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent： ``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* helper：blocked outside本场景对象；
* syscall/result： ``socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)=6``；
* fd 6：open、blocking、close-on-exec；
* ``F6``：sockfs socket file， ``f_op=socket_file_ops``；
* ``S.type=SOCK_STREAM``、 ``S.state=SS_UNCONNECTED``；
* ``S.ops=inet_stream_ops``；
* ``L.sk_family=AF_INET``、 ``L.sk_protocol=IPPROTO_TCP``；
* ``L.sk_prot=tcp_prot``、 ``L.sk_state=TCP_CLOSE``；
* ``L.sk_shutdown=0``、 ``L.sk_err=0``；
* local address/port：全部未绑定；
* remote address/port：全部为0；
* bind hash membership：none；
* listener hash membership：none；
* established hash membership：none；
* request socket、child socket与skb：none；
* next entry： ``bind(6, 127.0.0.1:28080)``。

关键边界
--------

#. protocol 0在AF_INET/ ``SOCK_STREAM`` 下选择 ``IPPROTO_TCP``。
#. ``struct socket`` 嵌在sockfs pseudo inode中； ``struct tcp_sock`` 是独立协议对象。
#. ``tcp_sock``、 ``inet_connection_sock``、 ``inet_sock`` 与 ``sock`` 是同一分配对象的嵌套视图。
#. ``SS_UNCONNECTED`` 属于socket API层； ``TCP_CLOSE`` 属于协议状态机层。
#. 新建socket处于 ``TCP_CLOSE`` 不等于对象已关闭，它表示尚未bind/listen/connect。
#. 单个 ``socket`` 在协议对象创建成功后才reserve fd； ``socketpair`` 的fd顺序不同。
#. ``SOCK_CLOEXEC`` 设置fdtable的close-on-exec bit，不把 ``O_CLOEXEC`` 写成file status flag。
#. ``fd_install`` 是数字fd真正对共享 ``files_struct`` 可见的发布点。
#. 未绑定TCP socket不在bind hash、listener hash或established hash中。
#. 创建TCP endpoint不会执行route lookup，也不会产生skb或loopback packet。

下一入口
--------

parent将构造：

.. code-block:: c

   struct sockaddr_in addr = {
       .sin_family = AF_INET,
       .sin_port = htons(28080),
       .sin_addr.s_addr = htonl(INADDR_LOOPBACK),
   };

   bind(server_fd, (struct sockaddr *)&addr, sizeof(addr));

下一章追踪用户 ``sockaddr_in`` 怎样进入内核， ``127.0.0.1`` 怎样被确认是本地地址，以及固定TCP端口28080怎样进入bind hash。

资料
----

* `Linux 7.2-rc1 net/socket.c：__sys_socket、__sock_create、sock_alloc、sock_map_fd与sock_alloc_file <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 net/ipv4/af_inet.c：inet_create、inetsw TCP选择与inet_stream_ops <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
* `Linux 7.2-rc1 net/core/sock.c：sk_alloc与sock_init_data <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/core/sock.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp.c与tcp_ipv4.c：tcp_init_sock、tcp_v4_init_sock与tcp_prot <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp.c>`_
