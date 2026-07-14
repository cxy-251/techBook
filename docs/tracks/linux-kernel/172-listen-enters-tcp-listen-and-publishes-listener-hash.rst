第一百七十二章：listen(8)怎样建立空请求队列并把socket加入TCP监听哈希？
===========================================================

上一章结束时，fd 6已经绑定 ``127.0.0.1:28080``，但尚未成为listener：

::

   fd 6 → F6 → socket S → tcp_sock LTP

   S.state                   = SS_UNCONNECTED
   L.sk_state                = TCP_CLOSE
   LINET.inet_rcv_saddr      = 127.0.0.1
   LINET.inet_num            = 28080
   LINET.inet_sport          = htons(28080)
   LICSK.icsk_bind_hash      = TB
   LICSK.icsk_bind2_hash     = TB2
   listener hash membership = none

parent现在执行：

.. code-block:: c

   int r = listen(6, 8);

本章固定：

* network namespace仍为 ``N``；
* ``somaxconn`` 大于或等于8，所以backlog不会被截断；
* socket类型为 ``SOCK_STREAM``，socket API状态为 ``SS_UNCONNECTED``；
* local address与port已由显式bind固定；
* ``SO_REUSEPORT`` 未设置；
* server-side TCP Fast Open未开启，且未通过socket option建立fastopen queue；
* 当前没有SYN、request socket、accepted child或accept waiter；
* 不发生LSM/BPF拒绝、allocation failure、并发listen、close或shutdown；
* 本章结束于空listener已经发布，尚未创建client socket；
* 本章不发送packet，不经过 ``lo`` transmit/receive或NET_RX softirq。

listen syscall怎样取得已绑定socket
---------------------------------

x86-64控制流为：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_listen
   → __sys_listen(6, 8)

``__sys_listen`` 通过scoped fd lookup取得 ``F6``，再调用：

::

   sock_from_file(F6) → S

固定验证结果：

::

   F6.f_op == socket_file_ops
   F6.private_data == S

所以fd 6仍指向上一章的同一socket对象，没有创建新file、socket或protocol control block。

backlog 8怎样经过somaxconn限制
-----------------------------

通用层进入：

::

   __sys_listen_socket(S, backlog=8)

首先读取当前network namespace的：

::

   N.core.sysctl_somaxconn

规则为：

::

   if ((unsigned int)backlog > somaxconn)
       backlog = somaxconn

固定 ``somaxconn >= 8``，因此：

::

   effective backlog = 8

通用层随后执行 ``security_socket_listen``。固定场景允许该操作，再分派：

::

   S.ops->listen(S, 8)
   → inet_listen(S, 8)

``S.ops`` 在第170章已经固定为 ``inet_stream_ops``。

inet_listen为什么要求SS_UNCONNECTED与SOCK_STREAM
----------------------------------------------

``inet_listen`` 取得：

::

   L = S.sk

然后：

::

   lock_sock(L)

在socket lock下验证：

::

   S.state == SS_UNCONNECTED
   S.type  == SOCK_STREAM

这两个条件区分socket API层的使用方式：

* 已经connect完成的socket不能转成普通listener；
* datagram socket不能调用TCP stream listen路径；
* 当前socket虽然已bind， ``S.state`` 仍保持 ``SS_UNCONNECTED``，所以允许listen。

验证通过后调用：

::

   __inet_listen_sk(L, 8)

__inet_listen_sk怎样检查TCP协议状态
-----------------------------------

``__inet_listen_sk`` 保存：

::

   old_state = L.sk_state
             = TCP_CLOSE

listen只接受：

::

   TCP_CLOSE
   TCP_LISTEN

``TCP_CLOSE`` 表示第一次进入listen； ``TCP_LISTEN`` 表示对已有listener调整backlog。本章属于第一次listen。

它先发布用户请求的完成队列上限：

::

   WRITE_ONCE(L.sk_max_ack_backlog, 8)

``sk_max_ack_backlog`` 限制的是已经完成握手、等待accept的队列容量语义。SYN request队列还受到独立的TCP与namespace参数约束，不能把一个backlog字段等同于所有半连接结构的精确数组长度。

为什么本章不启用TCP Fast Open server
-----------------------------------

第一次listen时， ``__inet_listen_sk`` 会读取：

::

   N.ipv4.sysctl_tcp_fastopen

只有server enable相关bits成立，且fastopen queue尚未配置时，才可能执行：

::

   fastopen_queue_tune
   tcp_fastopen_init_key_once

固定场景没有启用server-side TFO，也没有TCP_FASTOPEN socket option，因此该分支不改变listener。

这保证后续章节中的第一个连接使用普通：

::

   SYN → SYN-ACK → ACK

而不是SYN携带应用数据的Fast Open路径。

inet_csk_listen_start怎样初始化监听队列
--------------------------------------

第一次listen进入：

::

   inet_csk_listen_start(L)

它先验证当前ULP是否允许listener clone。固定socket没有附加不兼容ULP，检查通过。

随后调用：

::

   reqsk_queue_alloc(&LICSK.icsk_accept_queue)

初始化request/accept queue基础状态：

::

   fastopenq.rskq_rst_head = NULL
   fastopenq.rskq_rst_tail = NULL
   fastopenq.qlen          = 0
   rskq_accept_head        = NULL

并设置：

::

   L.sk_ack_backlog = 0

因此此刻：

* 没有完成握手的child等待accept；
* 没有Fast Open reset条目；
* 没有 ``request_sock``；
* 没有accept queue tail所指对象；
* 没有线程睡眠在accept wait queue。

``inet_csk_delack_init`` 同时初始化connection-socket delayed-ACK相关基础状态，供未来child与协议路径使用。

为什么先写TCP_LISTEN再重新验证端口
--------------------------------

``inet_csk_listen_start`` 执行：

::

   inet_sk_state_store(L, TCP_LISTEN)

于是协议状态发生：

::

   TCP_CLOSE → TCP_LISTEN

源码明确保留了一个短窗口：state已经是 ``TCP_LISTEN``，但socket尚未进入listener hash。该窗口受socket lock与后续端口验证约束；外部listener lookup无法仅凭state找到尚未hash的socket。

随后再次调用：

::

   L.sk_prot->get_port(L, LINET.inet_num)
   → inet_csk_get_port(L, 28080)

listen必须重新按listener语义检查端口，因为reuse规则会参考当前 ``sk_state``。上一章已建立 ``TB/TB2`` 与owner ``L``；冲突遍历会忽略socket自身，固定场景也没有其他owner，因此检查成功。

由于：

::

   LICSK.icsk_bind_hash != NULL

成功路径不会再次把 ``L`` 重复加入bind owner链。原有端口所有权继续有效。

listen为什么再次写inet_sport并清空dst
------------------------------------

端口复核成功后写入：

::

   LINET.inet_sport = htons(LINET.inet_num)
                     = htons(28080)

该值与上一章一致。随后：

::

   sk_dst_reset(L)

listener不应保留面向某个remote peer的输出dst。固定socket本来没有dst cache，该调用再次确保监听身份只由local endpoint决定。

tcp_prot.hash怎样分派到inet_hash
-------------------------------

``inet_csk_listen_start`` 接着调用：

::

   L.sk_prot->hash(L)

固定：

::

   L.sk_prot      = tcp_prot
   tcp_prot.hash  = inet_hash

因此进入：

::

   inet_hash(L)

``inet_hash`` 根据：

::

   L.sk_state == TCP_LISTEN

选择listener路径，而不是established ``ehash`` 路径。

lhash2怎样按127.0.0.1与28080选择bucket
-------------------------------------

listener路径取得TCP ``inet_hashinfo``，根据：

::

   network namespace N
   local receive address 127.0.0.1
   local port 28080

计算：

::

   ipv4_portaddr_hash(N,
                      htonl(127.0.0.1),
                      28080)

并选择：

::

   struct inet_listen_hashbucket ILB2

``lhash2`` 是面向listener lookup的地址+端口hash。它与上一章的两级bind hash作用不同：

::

   bind hash:
       控制local port/address ownership与冲突

   listener lhash2:
       让入站TCP segment按destination address/port找到listener

两套结构可以同时引用同一个 ``L``，但回答的问题不同。

listener怎样被RCU可见地加入哈希
------------------------------

``inet_hash`` 确认 ``L`` 尚未hash，然后持有：

::

   ILB2.lock

本章未设置 ``SO_REUSEPORT``，所以不建立reuseport group。随后设置：

::

   SOCK_RCU_FREE

listener可能被无引用的RCU lookup路径观察，最终释放需要遵守相应RCU生命周期。

接着执行等价于：

::

   __sk_nulls_add_node_rcu(L, &ILB2.nulls_head)

并增加当前network namespace中的TCP protocol in-use accounting。

从该发布点开始，未来目的地址为 ``127.0.0.1``、目的端口为28080的IPv4 TCP segment可以通过listener lookup找到 ``L``。

精确地址listener lookup为什么优先于INADDR_ANY
--------------------------------------------

后续入站路径会先计算：

::

   ipv4_portaddr_hash(N, packet_daddr, packet_dport)

对本场景未来SYN：

::

   packet_daddr = 127.0.0.1
   packet_dport = 28080

因此首先查找精确地址bucket ``ILB2``。只有精确bucket没有匹配结果时，lookup才回退到：

::

   INADDR_ANY:28080

本章listener绑定了具体loopback地址，所以会在第一阶段被命中，不依赖wildcard回退。

listen返回时为什么仍没有request_sock
------------------------------------

``inet_hash`` 只发布listener。它不会主动创建：

* client endpoint；
* SYN skb；
* ``request_sock``；
* ``TCP_NEW_SYN_RECV`` 对象；
* established child；
* accept queue entry。

这些对象需要未来client执行connect并让SYN实际进入TCP receive path后才产生。

因此listen成功后的queue仍为空：

::

   reqsk_queue_len = 0
   sk_ack_backlog  = 0
   rskq_accept_head = NULL

backlog 8只是允许未来队列增长到相应策略边界，不代表listen立即分配8个request或child对象。

inet_listen怎样完成锁边界
-------------------------

``inet_hash`` 成功返回后：

::

   inet_csk_listen_start → 0
   __inet_listen_sk      → 0

``inet_listen`` 执行：

::

   release_sock(L)

固定场景没有socket backlog skb需要处理。随后控制流返回：

::

   inet_listen
   → __sys_listen_socket
   → __sys_listen
   → __x64_sys_listen

最终：

::

   listen(6, 8) = 0

数字fd、 ``F6``、 ``S`` 与 ``LTP`` 不变；新增的是监听状态、空queue初始化和listener hash membership。

本章为什么没有经过loopback设备
-----------------------------

listen建立的是被动接收入口。它没有调用：

* ``tcp_connect`` 或 ``tcp_v4_connect``；
* ``ip_route_connect``；
* ``tcp_transmit_skb``；
* ``ip_queue_xmit``；
* ``dev_queue_xmit``；
* ``loopback_xmit``；
* ``net_rx_action``。

因此没有SYN、SYN-ACK或ACK。CPU0始终执行parent的syscall路径，没有切换到softirq或另一个task。

本批三章的对象变化
------------------

本批可以压缩为：

::

   socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0)
   → create sockfs inode IS and socket S
   → select inet_stream_ops + tcp_prot
   → allocate tcp_sock LTP
   → initialize S.state=SS_UNCONNECTED
   → initialize L.sk_state=TCP_CLOSE
   → allocate F6 and fd_install(6,F6)

   bind(6, 127.0.0.1:28080)
   → copy sockaddr_in
   → verify RTN_LOCAL
   → create/find bind bucket TB
   → create/find bind2 bucket TB2
   → attach L to TB2.owners
   → set local address and port
   → remain TCP_CLOSE

   listen(6, 8)
   → clamp backlog to 8
   → initialize empty request/accept queue
   → set sk_max_ack_backlog=8
   → TCP_CLOSE → TCP_LISTEN
   → revalidate bound port
   → insert L into exact-address listener lhash2
   → return 0

本章结束状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent： ``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* helper：blocked outside本场景对象；
* syscall/result： ``listen(6,8)=0``；
* fd 6：open、blocking、close-on-exec；
* ``F6/S/LTP``：active；
* ``S.state=SS_UNCONNECTED``；
* ``L.sk_state=TCP_LISTEN``；
* local endpoint： ``127.0.0.1:28080``；
* remote endpoint：unset；
* ``L.sk_max_ack_backlog=8``；
* ``L.sk_ack_backlog=0``；
* request queue length：0；
* accept queue head：NULL；
* Fast Open queue：empty；
* bind buckets ``TB/TB2``：active，owner包含 ``L``；
* listener bucket ``ILB2``：active，包含 ``L``；
* established hash membership：none；
* request socket：none；
* accepted child socket：none；
* skb与packet：none；
* route/dst cache：empty；
* next entry：client执行 ``socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)``。

关键边界
--------

#. 通用listen层先按 ``somaxconn`` 截断backlog，再调用协议listen回调。
#. ``S.state=SS_UNCONNECTED`` 与 ``L.sk_state=TCP_LISTEN`` 可以同时成立；它们属于不同状态层。
#. ``sk_max_ack_backlog`` 不是预分配child数量，也不能等同于SYN queue的唯一容量参数。
#. 第一次listen初始化空request/accept queue，并把 ``sk_ack_backlog`` 置0。
#. ``TCP_LISTEN`` 在端口复核和hash插入前写入，外部可查找性仍以hash发布为准。
#. listen会按listener状态重新调用 ``get_port``，但不会重复加入已有bind owner链。
#. bind hash解决端口所有权；listener lhash2解决入站segment查找。
#. 具体地址listener先按 ``127.0.0.1:28080`` 查找，之后才可能回退到 ``INADDR_ANY``。
#. listener设置 ``SOCK_RCU_FREE``，其哈希可见性与最终释放遵守RCU边界。
#. listen完成时没有request_sock、child socket或packet。
#. 直到client connect产生SYN，loopback route、output与receive路径才会进入叙事。

下一入口
--------

服务器监听端已经建立。下一批优先从client创建开始：

.. code-block:: c

   int client_fd = socket(AF_INET,
                          SOCK_STREAM | SOCK_CLOEXEC,
                          0);

   connect(client_fd,
           (struct sockaddr *)&addr,
           sizeof(addr));

固定fdtable下，client socket将复用最低空闲fd 7。后续需要继续固定client自动端口、loopback route、SYN发送、softirq接收、request socket、SYN-ACK、最终ACK与scheduler顺序。

资料
----

* `Linux 7.2-rc1 net/socket.c：__sys_listen与backlog截断 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `Linux 7.2-rc1 net/ipv4/af_inet.c：inet_listen与__inet_listen_sk <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_connection_sock.c：reqsk_queue_alloc与inet_csk_listen_start <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_connection_sock.c>`_
* `Linux 7.2-rc1 net/ipv4/inet_hashtables.c：inet_hash、listener lhash2与lookup顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_hashtables.c>`_
