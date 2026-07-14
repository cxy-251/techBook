第一百七十一章：bind(127.0.0.1:28080)怎样验证本地地址并占用TCP端口？
==========================================================

上一章结束时，fd 6已经指向一个未绑定的IPv4 TCP endpoint：

::

   fd 6 → F6 → socket S → tcp_sock LTP

   S.state                  = SS_UNCONNECTED
   L.sk_state               = TCP_CLOSE
   LINET.inet_num           = 0
   LINET.inet_sport         = 0
   LINET.inet_rcv_saddr     = 0
   LINET.inet_saddr         = 0
   LICSK.icsk_bind_hash     = NULL
   LICSK.icsk_bind2_hash    = NULL

parent现在执行：

.. code-block:: c

   struct sockaddr_in addr = {
       .sin_family = AF_INET,
       .sin_port = htons(28080),
       .sin_addr.s_addr = htonl(INADDR_LOOPBACK),
   };

   int r = bind(6, (struct sockaddr *)&addr, sizeof(addr));

本章固定：

* network namespace仍为 ``N``；
* ``lo`` 已经UP， ``127.0.0.1/8`` 已经配置，local table中存在loopback local route；
* ``N.ipv4.sysctl_ip_unprivileged_port_start=1024``，因此端口28080不需要 ``CAP_NET_BIND_SERVICE``；
* network namespace中没有其他socket占用与本场景冲突的 ``127.0.0.1:28080``；
* socket未设置 ``SO_REUSEADDR``、 ``SO_REUSEPORT``、 ``IP_FREEBIND`` 或 ``IP_TRANSPARENT``；
* socket未绑定device， ``sk_bound_dev_if=0``；
* 不存在BPF bind重写、LSM拒绝、allocation failure或并发bind；
* 本章只完成local address与port ownership，不进入 ``TCP_LISTEN``；
* 本章不执行route output lookup，也不生成skb或loopback packet。

bind syscall怎样取得fd 6对应的socket
------------------------------------

x86-64入口为：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_bind
   → __sys_bind(6, user_addr, sizeof(sockaddr_in))

``__sys_bind`` 先用scoped fd lookup取得 ``F6``。fd有效后调用：

::

   sock_from_file(F6)

该函数只接受：

::

   F6.f_op == &socket_file_ops

随后从：

::

   F6.private_data

取回 ``S``。因此通用bind层验证的是“fd是否指向socket file”，不会根据数字fd直接猜测协议。

固定结果：

::

   file   = F6
   socket = S
   sock   = L

scoped file reference保证bind路径执行期间 ``F6`` 不会因普通fd lookup结束而提前释放。

用户sockaddr_in怎样复制到内核
-----------------------------

用户指针不能直接传给协议实现。 ``__sys_bind`` 调用：

::

   move_addr_to_kernel(user_addr,
                       sizeof(struct sockaddr_in),
                       &address)

固定用户结构被复制进内核栈上的 ``sockaddr_storage address``。有效内容为：

::

   sin_family = AF_INET
   sin_port   = htons(28080)
   sin_addr   = htonl(127.0.0.1)

固定场景没有 ``EFAULT``，长度也不短于 ``sizeof(struct sockaddr_in)``。

然后进入：

::

   __sys_bind_socket(S, &address, sizeof(struct sockaddr_in))
   → security_socket_bind(...)
   → S.ops->bind(...)
   → inet_bind(S, address, addr_len)

上一章已经固定 ``S.ops=inet_stream_ops``，其 ``bind`` 回调就是 ``inet_bind``。

inet_bind怎样进入带socket lock的__inet_bind
------------------------------------------

``inet_bind`` 调用：

::

   inet_bind_sk(L, address, addr_len)

TCP没有覆盖独立的 ``sk_prot->bind`` 回调，因此继续：

::

   __inet_bind(L, address, addr_len, BIND_WITH_LOCK)

``BIND_WITH_LOCK`` 使 ``__inet_bind`` 在修改socket身份前执行：

::

   lock_sock(L)

本章没有softirq或另一个用户线程同时持有该socket，锁直接取得。锁保护的主要对象包括local address、local port、协议状态与绑定关系。

127.0.0.1为什么被认定为可绑定本地地址
------------------------------------

``__inet_bind`` 首先验证：

::

   addr.sin_family == AF_INET

随后根据socket绑定的L3 device与network namespace选择local routing table，固定为普通local table：

::

   tb_id = RT_TABLE_LOCAL

然后调用：

::

   inet_addr_type_table(N,
                        htonl(127.0.0.1),
                        RT_TABLE_LOCAL)

由于 ``lo`` 已配置 ``127.0.0.1/8``，返回类型是本地地址：

::

   chk_addr_ret = RTN_LOCAL

``inet_addr_valid_or_nonlocal`` 因此接受该地址。这里发生的是地址类型查询，不是为即将发送的packet建立dst，也不会执行TCP output route selection。

若地址不是当前namespace中的local address，且没有freebind/transparent语义，路径会返回 ``-EADDRNOTAVAIL``。固定场景不走该分支。

为什么28080不需要CAP_NET_BIND_SERVICE
-------------------------------------

内核把network-order端口转换为host-order：

::

   snum = ntohs(addr.sin_port)
        = 28080

随后调用等价判断：

::

   inet_port_requires_bind_service(N, 28080)

该判断使用当前network namespace的 ``ip_unprivileged_port_start``。本场景固定为1024，所以28080不属于受保护端口范围，路径不需要检查或持有 ``CAP_NET_BIND_SERVICE``。

此时socket仍满足bind前置状态：

::

   L.sk_state      = TCP_CLOSE
   LINET.inet_num  = 0

``__inet_bind`` 在socket lock下检查：

::

   if (L.sk_state != TCP_CLOSE || LINET.inet_num != 0)
       return -EINVAL

这阻止已连接、已监听或已绑定socket重新走普通bind路径。

local address为什么在端口分配前写入socket
----------------------------------------

状态检查通过后， ``__inet_bind`` 先写入：

::

   LINET.inet_rcv_saddr = htonl(127.0.0.1)
   LINET.inet_saddr     = htonl(127.0.0.1)

``inet_rcv_saddr`` 用于本地接收与hash匹配； ``inet_saddr`` 是发送侧选择的local source address。对普通单播loopback地址，两者保持相同。

这一步先于 ``get_port``，因为端口冲突判断需要把local address纳入比较。若后续端口占用失败，错误路径会把这两个地址恢复为0。

tcp_prot怎样把get_port分派到inet_csk_get_port
--------------------------------------------

固定 ``snum`` 非0， ``__inet_bind`` 调用：

::

   L.sk_prot->get_port(L, 28080)

上一章已经建立：

::

   L.sk_prot = tcp_prot
   tcp_prot.get_port = inet_csk_get_port

于是进入：

::

   inet_csk_get_port(L, 28080)

该函数负责TCP/connection-socket的本地端口所有权。它处理的是bind hash，不是listener hash，也不是established四元组hash。

inet_bind_bucket怎样表示端口28080
---------------------------------

``inet_csk_get_port`` 取得当前network namespace的TCP hashinfo，根据：

::

   network namespace N
   port 28080
   l3mdev = 0

选择bind hash bucket，并持有对应bucket lock。固定场景中尚不存在匹配的 ``inet_bind_bucket``，因此创建：

::

   struct inet_bind_bucket TB

关键身份为：

::

   TB.net    = N
   TB.port   = 28080
   TB.l3mdev = 0

``TB`` 表示namespace、port与L3 domain层面的端口桶。它本身不区分 ``127.0.0.1`` 与 ``INADDR_ANY``，地址维度由第二级bucket承担。

inet_bind2_bucket怎样加入local address维度
-----------------------------------------

TCP bind实现再根据socket的local receive address选择第二级hash bucket，并创建：

::

   struct inet_bind2_bucket TB2

固定身份为：

::

   TB2.net       = N
   TB2.port      = 28080
   TB2.l3mdev    = 0
   TB2.rcv_saddr = htonl(127.0.0.1)

``TB2`` 连接到 ``TB.bhash2``，并拥有一条socket owners链。这样内核可以分别判断：

* 相同namespace与port是否已有任何绑定；
* 特定local address是否冲突；
* wildcard bind与specific-address bind之间是否冲突；
* ``SO_REUSEADDR`` / ``SO_REUSEPORT`` 是否允许共享。

本章没有任何已有owner，冲突检查通过。

inet_bind_hash怎样建立socket的端口所有权
---------------------------------------

成功路径调用：

::

   inet_bind_hash(L, TB, TB2, 28080)

它写入：

::

   LINET.inet_num       = 28080
   LICSK.icsk_bind_hash = TB
   LICSK.icsk_bind2_hash = TB2

并把 ``L`` 加入：

::

   TB2.owners = { L }

这里的 ``inet_num`` 使用host byte order，便于内核端口比较。稍后 ``__inet_bind`` 写入network byte order字段：

::

   LINET.inet_sport = htons(LINET.inet_num)
                     = htons(28080)

因此要区分：

::

   inet_num   = host-order 28080
   inet_sport = network-order 28080

bind完成后哪些user lock被设置
----------------------------

因为local receive address非0，内核记录：

::

   L.sk_userlocks |= SOCK_BINDADDR_LOCK

因为用户显式传入非0端口，内核记录：

::

   L.sk_userlocks |= SOCK_BINDPORT_LOCK

这些bits说明地址和端口由用户bind固定。后续connect或listen不能把它们当作自动选择结果任意替换。

``__inet_bind`` 同时清除尚不存在的remote identity：

::

   LINET.inet_daddr = 0
   LINET.inet_dport = 0

并执行：

::

   sk_dst_reset(L)

本章之前没有有效dst cache；该调用仍保证旧路由状态不会跨越新的local bind身份。

为什么bind后仍不是listener
-------------------------

bind成功后保持：

::

   S.state    = SS_UNCONNECTED
   L.sk_state = TCP_CLOSE

``TB`` 与 ``TB2`` 只表示本地地址/端口所有权。当前 ``L`` 仍未加入：

* TCP listener ``lhash2``；
* established ``ehash``；
* request-socket hash；
* accept queue。

因此进入TCP receive path的SYN还不能通过listener lookup找到这个socket。真正发布监听身份要等下一章 ``listen`` 调用 ``inet_hash``。

bind返回前怎样释放socket lock
----------------------------

``__inet_bind`` 设置：

::

   err = 0

然后执行：

::

   release_sock(L)

固定场景没有积压backlog需要在release时处理。控制流返回：

::

   __inet_bind
   → inet_bind
   → __sys_bind_socket
   → __sys_bind
   → __x64_sys_bind

最终：

::

   bind(6, 127.0.0.1:28080) = 0

数字fd、file、socket与tcp_sock均保持存活；bind只改变协议对象与TCP bind tables。

本章为什么没有loopback packet
-----------------------------

本章访问了local address classification和TCP bind hash，但没有：

* ``ip_route_output`` 或 ``ip_route_connect``；
* ``tcp_transmit_skb``；
* ``ip_queue_xmit``；
* ``dev_queue_xmit``；
* ``netif_rx``；
* loopback NAPI或softirq receive path。

因此没有构造IP header、TCP header、SYN或任何skb。 ``lo`` 的存在只是让 ``127.0.0.1`` 成为有效local address，并为后续connect提供route。

本章结束状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent： ``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* syscall/result： ``bind(6,127.0.0.1:28080)=0``；
* fd 6与 ``F6/S/L``：保持open；
* ``S.state=SS_UNCONNECTED``；
* ``L.sk_state=TCP_CLOSE``；
* ``LINET.inet_rcv_saddr=127.0.0.1``；
* ``LINET.inet_saddr=127.0.0.1``；
* ``LINET.inet_num=28080``；
* ``LINET.inet_sport=htons(28080)``；
* ``LINET.inet_daddr=0``、 ``inet_dport=0``；
* ``SOCK_BINDADDR_LOCK``：set；
* ``SOCK_BINDPORT_LOCK``：set；
* bind bucket ``TB``：active；
* bind2 bucket ``TB2``：active，owners包含 ``L``；
* listener hash membership：none；
* request/accept queue：尚未作为listener初始化；
* route cache：empty；
* request socket、child socket与skb：none；
* next entry： ``listen(6, 8)``。

关键边界
--------

#. ``move_addr_to_kernel`` 在协议回调前复制并验证用户socket address。
#. ``127.0.0.1`` 的可绑定性由当前network namespace的local address状态决定。
#. 地址类型查询不是发送route lookup，不会建立dst或packet。
#. 是否需要 ``CAP_NET_BIND_SERVICE`` 由当前namespace的 ``ip_unprivileged_port_start`` 决定；本场景固定为1024，28080无需该能力。
#. 普通bind要求 ``sk_state=TCP_CLOSE`` 且 ``inet_num=0``。
#. local address先写入socket，使端口冲突判断可以包含地址维度。
#. ``inet_bind_bucket`` 表示namespace/port/L3 domain； ``inet_bind2_bucket`` 增加local address维度。
#. ``inet_num`` 是host-order， ``inet_sport`` 是network-order。
#. bind hash记录端口所有权，不等于TCP listener hash。
#. bind成功后socket仍为 ``SS_UNCONNECTED`` / ``TCP_CLOSE``。
#. bind过程不产生SYN、skb或loopback设备I/O。

下一入口
--------

parent将执行：

.. code-block:: c

   listen(server_fd, 8);

下一章追踪backlog怎样被限制，request/accept queue怎样初始化，状态怎样从 ``TCP_CLOSE`` 变成 ``TCP_LISTEN``，以及 ``L`` 怎样进入按 ``127.0.0.1:28080`` 查找的listener hash。

资料
----

* `Linux 7.2-rc1 net/socket.c：__sys_bind、move_addr_to_kernel与__sys_bind_socket <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 net/ipv4/af_inet.c：inet_bind_sk与__inet_bind <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_connection_sock.c：inet_csk_get_port与bind conflict检查 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_connection_sock.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_hashtables.c：inet_bind_bucket、inet_bind2_bucket与inet_bind_hash <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_hashtables.c>`_
