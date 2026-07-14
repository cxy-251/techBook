第一百七十三章：client connect怎样选择loopback路由、自动端口并进入TCP_SYN_SENT？
====================================================================

上一章结束时，server listener已经发布在精确地址监听哈希中：

::

   fd 6 → F6 → server socket S → listener L

   S.state                   = SS_UNCONNECTED
   L.sk_state                = TCP_LISTEN
   local endpoint            = 127.0.0.1:28080
   listener lhash2           = contains L
   request queue length      = 0
   accept queue length       = 0

parent仍在CPU0用户态运行，fd 7是最低空闲描述符。现在创建client并执行blocking connect：

.. code-block:: c

   int client_fd = socket(AF_INET,
                          SOCK_STREAM | SOCK_CLOEXEC,
                          0);

   int r = connect(client_fd,
                   (struct sockaddr *)&addr,
                   sizeof(addr));

本章先追踪client对象创建、route selection、自动源端口与四元组哈希。叙事边界停在 ``tcp_v4_connect`` 即将调用 ``tcp_connect`` 的位置；此时还没有分配SYN skb。

本章固定：

* network namespace仍为 ``N``，只有CPU0 online；
* ``lo`` 为UP，MTU为65536，local table中已有 ``127.0.0.1`` local route；
* fd 0至6占用，client取得fd 7；
* client不设置 ``SOCK_NONBLOCK``、 ``SO_REUSEADDR``、 ``SO_REUSEPORT``、 ``IP_BIND_ADDRESS_NO_PORT`` 或TCP Fast Open；
* ``ip_local_port_range`` 为32768至60999，端口40000未被占用或保留；
* 随机扰动与四元组hash在本场景中使 ``inet_hash_connect`` 首个成功候选为40000；这不是所有运行都固定选择40000；
* route result固定为local unicast route：source与destination均为 ``127.0.0.1``，output device为 ``lo``；
* client initial sequence number固定为 ``C_ISN=0x13572468``，timestamp offset由固定随机状态产生；
* 不发生BPF地址重写、LSM/XFRM拒绝、route failure、port collision、TIME_WAIT复用或allocation failure；
* 本章结束前没有SYN、SYN-ACK、request socket或softirq packet processing。

client socket为什么复用fd 7
--------------------------

client的 ``socket()`` 与第170章服务器端经过同一创建主链：

::

   __x64_sys_socket
   → __sys_socket
   → __sys_socket_create
   → __sock_create
   → inet_create
   → sk_alloc(..., tcp_prot, ...)
   → sock_init_data
   → tcp_v4_init_sock
   → tcp_init_sock
   → sock_map_fd
   → sock_alloc_file
   → fd_install

本章不重复展开这些初始化，只固定新对象名称：

::

   sockfs inode CIS
       └── client struct socket CS
              └── client tcp_sock CTP
                    └── struct sock C

   fd 7 → F7 → CS → C/CTP

fd 6仍指向server listener；fdtable按最低空闲编号返回7：

::

   socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0) = 7

client创建完成后：

::

   CS.type       = SOCK_STREAM
   CS.state      = SS_UNCONNECTED
   CS.ops        = inet_stream_ops
   C.sk_state    = TCP_CLOSE
   C.sk_prot     = tcp_prot
   C.sk_protocol = IPPROTO_TCP

   C.inet_num        = 0
   C.inet_sport      = 0
   C.inet_rcv_saddr  = 0
   C.inet_daddr      = 0
   C.inet_dport      = 0

   bind hash membership = none
   ehash membership     = none
   dst cache            = none

``SOCK_CLOEXEC`` 设置fdtable中的close-on-exec bit；F7仍是blocking socket file。

connect syscall怎样取得F7与用户地址
-----------------------------------

parent执行 ``connect(7, ...)`` 后进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_connect
   → __sys_connect(7, user_addr, sizeof(sockaddr_in))

``__sys_connect`` 先取得scoped file reference，再把用户地址复制到内核：

::

   fd 7 → F7
   move_addr_to_kernel(user_addr,
                       sizeof(struct sockaddr_in),
                       &address)

固定复制结果为：

::

   address.sin_family = AF_INET
   address.sin_addr   = htonl(127.0.0.1)
   address.sin_port   = htons(28080)

然后：

::

   __sys_connect_file(F7, &address, addrlen, 0)
   → sock_from_file(F7) → CS
   → security_socket_connect(...)
   → CS.ops->connect(...)
   → inet_stream_connect(CS, ...)

F7的 ``f_op`` 是 ``socket_file_ops``， ``private_data`` 是CS，所以fd不会被误解释成其他VFS对象。

inet_stream_connect为什么先锁client socket
-----------------------------------------

``inet_stream_connect`` 执行：

::

   lock_sock(C)
   → __inet_stream_connect(CS, address, addrlen,
                           F7.f_flags, is_sendmsg=0)

本章client没有 ``O_NONBLOCK``，所以后续 ``sock_sndtimeo`` 会得到blocking timeout语义。

``__inet_stream_connect`` 先验证两层状态：

::

   CS.state   = SS_UNCONNECTED
   C.sk_state = TCP_CLOSE

只有socket API层尚未连接，且TCP协议层仍在 ``TCP_CLOSE``，才会首次调用协议connect回调：

::

   C.sk_prot->connect(C, address, addrlen)
   → tcp_v4_connect(C, address, addrlen)

注意此刻 ``CS.state`` 仍是 ``SS_UNCONNECTED``。通用层只有在 ``tcp_v4_connect`` 成功返回后，才把它改成 ``SS_CONNECTING``。

tcp_v4_connect怎样验证destination
---------------------------------

``tcp_v4_connect`` 检查：

::

   addrlen >= sizeof(struct sockaddr_in)
   sin_family == AF_INET

固定没有source-route IP option，因此：

::

   daddr   = 127.0.0.1
   nexthop = 127.0.0.1
   orig_sport = 0
   orig_dport = htons(28080)

client当前没有显式bind， ``inet_sport`` 和 ``inet_saddr`` 都是0。随后开始第一次route lookup：

::

   ip_route_connect(fl4,
                    nexthop=127.0.0.1,
                    saddr=0,
                    oif=0,
                    protocol=IPPROTO_TCP,
                    sport=0,
                    dport=28080,
                    C)

ip_route_connect怎样选择loopback source address
-----------------------------------------------

路由层在network namespace N中查询到 ``127.0.0.1`` 的local route。固定结果：

::

   fl4.daddr       = 127.0.0.1
   fl4.saddr       = 127.0.0.1
   fl4.flowi4_oif  = 0
   route type      = RTN_LOCAL
   rt.dst.dev      = lo
   rt.dst.mtu      = 65536
   route error     = 0

``flowi4_oif`` 仍为0，因为client没有通过 ``SO_BINDTODEVICE`` 或其他方式绑定输出device。真正选择 ``lo`` 的是返回route中的 ``rt.dst.dev``。该local route同时为未绑定client选择loopback source address。

``tcp_v4_connect`` 拒绝multicast与broadcast route；本章route不带这些flags，因此继续。

client source address怎样写回socket
----------------------------------

因为 ``C.inet_saddr`` 原来为0，路径调用：

::

   inet_bhash2_update_saddr(C, &fl4.saddr, AF_INET)

client尚未占用端口，所以这里的关键结果是把route选出的source identity提交给socket：

::

   C.inet_saddr     = 127.0.0.1
   C.inet_rcv_saddr = 127.0.0.1

这不是用户显式bind，因此不会设置 ``SOCK_BINDADDR_LOCK``。后续连接失败时，错误路径仍可以重置自动选择的source address。

随后写入remote identity：

::

   C.inet_daddr = 127.0.0.1
   C.inet_dport = htons(28080)

到这里已经有地址对与remote port，但local port仍为0，四元组还不完整。

为什么先进入TCP_SYN_SENT再选择端口
---------------------------------

``tcp_v4_connect`` 设置协议准备状态：

::

   CTP.rx_opt.mss_clamp = TCP_MSS_DEFAULT
   tcp_set_state(C, TCP_SYN_SENT)

源码特意在仍持有socket lock时先写 ``TCP_SYN_SENT``，再选择local port与插入hash。端口冲突检查需要按“主动连接socket”的语义处理，而不是把它当作普通 ``TCP_CLOSE`` bind。

此刻：

::

   CS.state   = SS_UNCONNECTED
   C.sk_state = TCP_SYN_SENT

两者短暂不同步是正常的：socket API层尚未收到协议connect成功结果；TCP层已经进入主动打开准备状态。

inet_hash_connect怎样选择40000
------------------------------

``tcp_v4_connect`` 调用：

::

   inet_hash_connect(&N.ipv4.tcp_death_row, C)

由于：

::

   C.inet_num = 0

``inet_hash_connect`` 根据完整remote identity计算per-flow port offset，再进入 ``__inet_hash_connect``。默认local range固定为：

::

   low  = 32768
   high = 60999

算法使用table perturbation、secure flow offset与步长扫描，不等同于“从32768顺序加一”。本场景固定随机状态后，首个可用候选为：

::

   client local port = 40000

没有local reserved-port命中、bind owner冲突、established四元组冲突或TIME_WAIT对象，因此候选直接成功。

主动连接怎样同时进入bind hash与ehash
-----------------------------------

成功路径创建或找到client自己的端口桶：

::

   struct inet_bind_bucket CTB
       net    = N
       port   = 40000
       l3mdev = 0

以及地址特定的第二级bucket：

::

   struct inet_bind2_bucket CTB2
       net       = N
       port      = 40000
       rcv_saddr = 127.0.0.1

然后：

::

   inet_bind_hash(C, CTB, CTB2, 40000)

产生：

::

   C.inet_num            = 40000
   C.inet_sport          = htons(40000)
   C.icsk_bind_hash      = CTB
   C.icsk_bind2_hash     = CTB2
   CTB2.owners            contains C
   C.sk_userlocks        includes SOCK_CONNECT_BIND

``SOCK_CONNECT_BIND`` 表示端口由connect自动选择，不等于用户显式 ``SOCK_BINDPORT_LOCK``。

四元组现在固定为：

::

   local  = 127.0.0.1:40000
   remote = 127.0.0.1:28080

``__inet_check_established`` 确认该四元组唯一后，将C加入TCP established hash：

::

   C.sk_hash = inet_ehashfn(N,
                            127.0.0.1, 40000,
                            127.0.0.1, 28080)

   __sk_nulls_add_node_rcu(C, ehash_bucket)

主动连接socket在 ``TCP_SYN_SENT`` 阶段就进入ehash。这样未来SYN-ACK可以在连接尚未建立时按反向四元组查到C。

为什么route要按新端口再更新
--------------------------

第一次 ``ip_route_connect`` 使用 ``orig_sport=0``。端口40000确定后，路径调用：

::

   ip_route_newports(fl4, rt,
                     old_sport=0,
                     old_dport=28080,
                     new_sport=40000,
                     new_dport=28080,
                     C)

固定route仍为相同local route和 ``lo``，只是flow key现在包含完整端口对。

随后：

::

   sk_setup_caps(C, &rt->dst)

把route/dst能力提交到client socket。后续SYN发送可以复用该dst，不需要重新从零查找route。

initial sequence number怎样固定
-------------------------------

没有TCP repair和可复用TIME_WAIT状态，因此：

::

   secure_tcp_seq_and_ts_off(N,
                             127.0.0.1,
                             127.0.0.1,
                             htons(40000),
                             htons(28080))

返回本场景固定结果：

::

   CTP.write_seq = C_ISN
                 = 0x13572468

   CTP.tsoffset  = C_TS_OFFSET

该值来自带secret的per-flow计算；文中的常量只用于保持后续章节可追踪，不代表Linux对该四元组永远返回相同ISN。

本章结束状态
------------

叙事停在：

::

   tcp_v4_connect
   → tcp_connect(C)       # 下一章进入

当前精确状态：

* current executor：parent；
* CPU/mode：CPU0，x86-64 kernel mode，仍在 ``connect(7, ...)`` syscall；
* parent：``TASK_RUNNING``，持有client socket lock；
* server fd 6：保持open，listener L仍为 ``TCP_LISTEN``；
* client fd 7：open、blocking、close-on-exec；
* client file ``F7`` 与socket ``CS``：active；
* ``CS.state=SS_UNCONNECTED``，尚未由通用connect层改成 ``SS_CONNECTING``；
* ``C.sk_state=TCP_SYN_SENT``；
* client local endpoint：``127.0.0.1:40000``；
* client remote endpoint：``127.0.0.1:28080``；
* client bind ownership：``CTB/CTB2`` active，owners包含C；
* client ehash membership：active；
* ``SOCK_CONNECT_BIND``：set；
* ``SOCK_BINDADDR_LOCK`` / ``SOCK_BINDPORT_LOCK``：unset；
* client dst cache：local route through ``lo``；
* ``CTP.write_seq=C_ISN``；
* SYN skb：none；
* client retransmission queue：empty；
* server request queue：empty；
* request socket与accepted child：none；
* next entry：``tcp_connect(C)`` 初始化传输参数并构造SYN。

关键边界
--------

#. client ``socket()`` 复用服务器同一创建主链，差异是最低空闲fd变为7。
#. 通用socket状态 ``CS.state`` 只在协议connect成功返回后改成 ``SS_CONNECTING``。
#. ``ip_route_connect`` 在端口尚为0时先选择local route与source address；未绑定device时 ``flowi4_oif`` 仍为0，输出device由route的 ``dst.dev`` 决定。
#. 自动选择的source address不设置用户 ``SOCK_BINDADDR_LOCK``。
#. ``tcp_v4_connect`` 在选择local port之前先把协议状态写成 ``TCP_SYN_SENT``。
#. ephemeral port由带随机扰动的double-hash扫描选择；40000是固定场景结果，不是API保证。
#. connect自动端口同时建立bind/bind2 ownership与ehash membership。
#. ``SOCK_CONNECT_BIND`` 与用户显式 ``SOCK_BINDPORT_LOCK`` 含义不同。
#. ``TCP_SYN_SENT`` socket在SYN发出前已经能被未来SYN-ACK按四元组查找。
#. 本章尚未分配SYN skb，也没有进入loopback transmit或NET_RX softirq。

下一入口
--------

下一章从：

::

   tcp_connect(C)

开始，追踪route-derived MSS与窗口参数、SYN skb、TCP/IP header、retransmission queue，以及SYN怎样通过 ``lo`` 回到CPU0 receive backlog。

资料
----

* `Linux 7.2-rc1 net/socket.c：__sys_connect与__sys_connect_file <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 net/ipv4/af_inet.c：inet_stream_connect与blocking connect状态机 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
* `Linux 7.2-rc1 net/ipv4/tcp_ipv4.c：tcp_v4_connect、route与四元组提交 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp_ipv4.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_hashtables.c：inet_hash_connect与ephemeral port扫描 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_hashtables.c>`_
