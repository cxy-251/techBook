第一百九十二章：close(6)怎样撤销listener fd并退出TCP_LISTEN？
================================================================

上一章的timer softirq已经释放轻量 ``TW``，CPU0回到parent的x86-64 CPL 3用户态。
连接侧四元组不再存在，进程手里只剩server listener fd 6。它仍指向blocking、
close-on-exec文件 ``F6``；sockfs socket ``LS`` 仍把协议socket ``L`` 连接到文件；
``L`` 仍以 ``TCP_LISTEN`` 出现在精确地址 ``127.0.0.1:28080`` 的 ``lhash2`` 中，
并通过显式bind持有普通bind与bind2身份。

parent现在执行固定调用：

.. code-block:: c

   int close_result = close(6);

本章只走到listener退出监听身份、空监听队列停止的位置。端口28080与对象存储的最终
释放留给下一章的 ``adjudge_to_death`` 路径。这个切分很重要，因为在固定实现里，
“不再listen”和“显式绑定端口已经释放”不是同一个瞬间。

fd 6先消失，协议释放随后才开始
-------------------------------

系统调用把CPU0从CPL 3带入内核态，current仍是parent。``close_fd`` 先调用
``file_close_fd`` 处理fdtable，而不是先进入TCP。

fdtable锁内，内核读取 ``fdtable.fd[6]`` 中的 ``F6``，把该slot清为 ``NULL``，并清除
fd 6的open位。锁释放以后，任何新一次 ``read(6)``、``accept4(6,...)`` 或
``close(6)`` 都不能再从进程fdtable取得F6。旧的close-on-exec位可能留到这个编号
再次分配时被覆盖；close本身保证的是fd指针与open位撤销，不能把它写成逐位清理整张
close-on-exec bitmap。

撤销fd只切断用户态名称，并没有立刻终止当前close已经取得的文件引用。固定场景中F6
没有dup、SCM_RIGHTS、epoll注册或其他共享者，因此它是最后一份文件引用。``filp_flush``
处理flush钩子后，``fput_close_sync`` 同步进入 ``__fput``。这条close专用路径不会把
最后释放仅仅排给另一个worker然后立即返回；parent会在本次系统调用中继续走到socket
release。

``__fput`` 在完成fsnotify、eventpoll、security与fasync等通用文件收尾后调用
``F6.f_op->release``。sockfs文件的release是 ``sock_close``：它从inode内嵌的
``socket_alloc`` 取回 ``LS``，再进入 ``__sock_release``。此时 ``LS.sk`` 仍指向L，
所以IPv4 stream ops的 ``release`` 调用 ``inet_release``。

``inet_release`` 检查linger设置。本场景没有启用 ``SO_LINGER``，传给传输层的timeout
为0，于是控制流进入 ``tcp_close(L,0)``。这里的0不是RST指令；listener有自己的关闭
分支，不会像有未读数据的established socket那样做数据队列裁决。

listener关闭分支先设置完整shutdown
----------------------------------

``tcp_close`` 取得L的socket锁，``__tcp_close`` 首先把 ``sk_shutdown`` 写成
``SHUTDOWN_MASK``。这同时关闭读写方向的应用语义，但fd 6已经更早从fdtable消失，
用户态也没有机会再通过这个descriptor观察半关闭状态。

函数检查旧状态恰好是 ``TCP_LISTEN``，直接选择listener专用分支：

.. code-block:: c

   if (sk->sk_state == TCP_LISTEN) {
       tcp_set_state(sk, TCP_CLOSE);
       inet_csk_listen_stop(sk);
       goto adjudge_to_death;
   }

因此，这里不发送FIN，不等待ACK，也不创建TIME_WAIT。listener没有一个需要四次挥手
结束的对端连接；曾经accept出来的H早已独立销毁，不能把H的关闭状态重新挂回L。

tcp_set_state在发布TCP_CLOSE之前先按旧状态unhash
----------------------------------------------

``tcp_set_state(L,TCP_CLOSE)`` 并非先盲写 ``sk_state``。从有身份的状态进入
``TCP_CLOSE`` 时，它先调用协议的 ``unhash``。调用这一刻L的旧状态仍是
``TCP_LISTEN``，所以IPv4的 ``inet_unhash`` 能选择监听hash路径，而不是把它误当作
established ehash成员。

``inet_unhash`` 根据本地端口和精确本地地址定位 ``lhash2`` bucket，取得bucket锁，
再用RCU可见的hlist删除规则移除L的listen节点。新的SYN listener lookup从此不再命中
``127.0.0.1:28080`` 的L；已经开始的RCU读侧仍按既定生命周期规则完成，不能因此把
L的存储立即归还slab。删除hash节点也撤销协议对这个监听hash成员的in-use记账。

完成unhash后，``tcp_set_state`` 才把 ``sk_state`` 发布为 ``TCP_CLOSE``。这条顺序保证
其他CPU不会先看到一个仍挂在listener hash里的 ``TCP_CLOSE`` 对象；即使本场景只有
CPU0，固定源码的并发边界仍必须保留在叙述里。

显式bind让28080暂时留在bind表
--------------------------------

``tcp_set_state`` 的关闭路径还会判断是否可以立即放掉本地端口。对自动选择端口、且
没有bind-port lock的socket，unhash后的状态迁移可能顺便调用端口释放；但L来自第
一百七十一章的显式

.. code-block:: c

   bind(6, 127.0.0.1:28080)

这次成功bind已经设置 ``SOCK_BINDPORT_LOCK``。因此，``tcp_set_state`` 不在这里执行
``inet_put_port``。L虽已从 ``lhash2`` 消失并进入 ``TCP_CLOSE``，``inet_num`` 仍是
28080，``icsk_bind_hash`` 与 ``icsk_bind2_hash`` 也仍指向原来的bind owner。

这个短暂状态并不重新开放一个可用listener。SYN lookup已经找不到L，fd 6也已撤销；
保留bind身份只是让端口所有权跟随L活到协议destroy阶段，避免显式bind端点在对象尚未
完成析构时被提前拆散。下一章的 ``tcp_v4_destroy_sock`` 会在正确的锁域中调用
``inet_put_port``。

inet_csk_listen_stop检查并拆除空监听队列
--------------------------------------

状态发布为 ``TCP_CLOSE`` 后，``__tcp_close`` 调用 ``inet_csk_listen_stop``。这个函数
负责listener而不是fdtable：它停止request/accept基础设施，遍历已完成accept队列，
并处理可能存在的Fast Open reset队列与未完成请求。

固定场景的所有队列都已经为空。唯一的request ``R`` 在accept4取出H后释放；accept
queue为空，``sk_ack_backlog=0``；没有半连接SYN request，也没有Fast Open child。
因此 ``inet_csk_listen_stop`` 不需要为任何child发送RST，不迁移request，不减少一个
非零backlog，也不会通过循环中的 ``cond_resched`` 发生调度。

这里仍要执行stop逻辑，而不能因为队列为空就从叙述中跳过：queue指针、listen相关
计时与Fast Open辅助状态必须按listener关闭协议走到稳定终点。只是在固定输入下，
这些步骤不产生额外网络包或任务切换。

当 ``inet_csk_listen_stop`` 返回，``__tcp_close`` 执行 ``goto adjudge_to_death``。
本章停在这个标签即将读取 ``sk_state`` 的入口。parent仍处在 ``close(6)`` 的内核态，
F6的 ``__fput`` 尚未完成，``sock_close`` 也尚未返回；所以现在不能提前写
``close(6)=0``，也不能说LS、I6或L已经释放。

监听身份已撤销，协议与文件生命期仍在收尾
-----------------------------------------

从用户可达性看，fd 6最先消失；从TCP demultiplex看，L随后退出 ``lhash2`` 并进入
``TCP_CLOSE``；从端口所有权看，28080仍被L的显式bind身份保持；从对象生命期看，
F6、LS、sockfs inode I6与L都仍由当前同步release链访问。

这四个视角不能压缩成一句“close删除socket”。它们发生在同一次系统调用中，却由
不同引用、锁和可见性规则控制。下一章从 ``adjudge_to_death`` 继续，让L orphan化，
进入 ``inet_csk_destroy_sock`` 与 ``tcp_v4_destroy_sock``，到那里才会清除端口与
最后的协议资源。

本章结束状态
------------

* current executor：parent；
* CPU/mode：CPU0，x86-64 CPL 0；
* current syscall：``close(6)``，尚未返回；
* fdtable.fd[6]：``NULL``，open位已清除；
* fd 6的旧close-on-exec位：允许暂留，编号重用时覆盖；
* ``F6``：最后引用正在同步 ``__fput``/``sock_close`` 链中；
* ``LS`` 与sockfs inode ``I6``：仍在release链中；
* listener ``L.sk_shutdown``：``SHUTDOWN_MASK``；
* listener ``L.sk_state``：``TCP_CLOSE``；
* listener ``lhash2`` 身份：removed；
* listener request、accept与Fast Open相关队列：empty/stopped；
* ``L.sk_ack_backlog``：0；
* listener ``inet_num``：28080；
* listener bind与bind2身份：仍active；
* network output：没有FIN、RST或其他报文；
* schedule count：0；
* next code entry：``__tcp_close`` 的 ``adjudge_to_death``。

关键边界
--------

#. ``file_close_fd`` 先清fd指针与open位，TCP listener teardown随后才发生。
#. close不要求立即清除旧close-on-exec bitmap位；fd编号重用会重建正确位值。
#. 固定场景F6无共享引用，``fput_close_sync`` 在本次系统调用同步进入 ``__fput``。
#. ``inet_release`` 在未启用linger时调用 ``tcp_close(L,0)``；timeout 0不等于listener RST。
#. listener分支不发送FIN、不等待ACK，也不创建TIME_WAIT。
#. ``tcp_set_state`` 在发布 ``TCP_CLOSE`` 前按旧 ``TCP_LISTEN`` 状态执行unhash。
#. L从精确地址 ``lhash2`` 删除；它从未因listener身份进入established ehash。
#. 显式bind设置 ``SOCK_BINDPORT_LOCK``，所以 ``tcp_set_state`` 不提前释放28080。
#. ``TCP_CLOSE``、lhash2 removed与bind active可以在destroy前短暂同时成立。
#. 空request/accept队列仍要经过 ``inet_csk_listen_stop``，只是没有child或request可处理。
#. 固定场景不发送FIN/RST，不经过lo，也不在queue遍历中调度。
#. 本章结束时close尚未返回，F6、LS、I6与L不能提前宣告释放。

下一入口
--------

从 ``__tcp_close`` 的 ``adjudge_to_death`` 继续：固定L的orphan与引用顺序，进入
``inet_csk_destroy_sock``/``tcp_v4_destroy_sock``，由 ``inet_put_port`` 撤销28080的
bind与bind2 owner；随后返回sockfs和VFS release链，并区分 ``close(6)=0`` 与
``SOCK_RCU_FREE`` 对L存储的延后回收。

资料
----

* `固定源码：fs/open.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `固定源码：fs/file_table.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `固定源码：net/socket.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_
* `固定源码：net/ipv4/af_inet.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_
* `固定源码：net/ipv4/tcp.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/tcp.c>`_
* `固定源码：net/ipv4/inet_hashtables.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_hashtables.c>`_
* `固定源码：net/ipv4/inet_connection_sock.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_connection_sock.c>`_
