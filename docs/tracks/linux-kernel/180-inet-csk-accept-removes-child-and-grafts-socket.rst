第一百八十章：inet_csk_accept怎样取出R/H并把child graft到accepted socket？
===================================================================

上一章结束时，fd 8槽位已经预留，accepted sockfs inode ``I8``、socket ``AS`` 与file ``F8`` 已经建立；协议层尚未处理listener accept queue：

::

   fdtable fd 8
       open bit       = 1
       close-on-exec  = 1
       file pointer   = NULL

   accepted socket AS
       state          = SS_UNCONNECTED
       sk             = NULL
       file           = F8

   listener L
       state          = TCP_LISTEN
       accept queue   = R
       sk_ack_backlog = 1

   accept node R
       R.sk           = H

   server child H
       state          = TCP_ESTABLISHED
       sk_socket      = NULL

本章从：

::

   inet_stream_ops.accept(S, AS, &arg)
   → inet_accept(S, AS, &arg)

开始，追踪TCP如何取出R/H、结束R的accept-node生命周期，并通过 ``sock_graft`` 把H接到AS。叙事停在 ``do_accept`` 即将读取peer地址的位置。

本章固定queue初始非空，不启用TCP Fast Open，不发生错误、等待、信号或并发accept。

inet_accept怎样分派到TCP accept
-------------------------------

``inet_accept`` 取得listener protocol socket：

::

   sk1 = S.sk = L

随后通过protocol ``struct proto`` 调用：

::

   sk2 = READ_ONCE(L.sk_prot)->accept(L, &arg)
       = inet_csk_accept(L, &arg)

``inet_stream_ops`` 属于socket API operations； ``tcp_prot.accept`` 属于TCP protocol operations。两层accept名称相似，职责不同：

::

   inet_accept       # 管理struct socket并执行graft
   inet_csk_accept   # 管理listener queue并返回struct sock child

此刻AS与F8已经存在，fd 8仍未发布。

inet_csk_accept为什么不会等待
-----------------------------

``inet_csk_accept`` 首先：

::

   lock_sock(L)

然后验证：

::

   L.sk_state == TCP_LISTEN

固定成立。接着检查：

::

   reqsk_queue_empty(&L.icsk_accept_queue)

当前：

::

   rskq_accept_head = R

所以结果为false。代码不会计算receive timeout，也不会调用 ``inet_csk_wait_for_connect``。

这说明blocking ``accept4`` 具备睡眠能力，却不代表本次调用实际睡眠。已经完成握手的H在syscall进入前就位于accept queue中，parent始终保持 ``TASK_RUNNING``。

reqsk_queue_remove怎样更新FIFO与backlog
--------------------------------------

路径调用：

::

   R = reqsk_queue_remove(queue, L)

该函数在：

::

   spin_lock_bh(&queue->rskq_lock)

保护下读取head。固定只有一个节点：

::

   head = R
   tail = R
   R.dl_next = NULL

移除时先执行：

::

   sk_acceptq_removed(L)

因此：

::

   L.sk_ack_backlog : 1 → 0

再更新FIFO：

::

   queue.rskq_accept_head = R.dl_next = NULL
   queue.rskq_accept_tail = NULL

释放queue spinlock后返回R。

这里减少的是“已经完成握手、等待accept的连接数”。SYN阶段的：

::

   request qlen  = 0
   request young = 0

早在最终ACK完成hashdance时已经归零，本章不会再次修改。

arg.is_empty记录移除后的queue状态
---------------------------------

``inet_csk_accept`` 紧接着写入：

::

   arg.is_empty = reqsk_queue_empty(queue)
                = true

然后取得完整child：

::

   newsk = R.sk = H

``R`` 与 ``H`` 仍然是两个对象：

* R是accept FIFO节点；
* H是完整 ``struct tcp_sock``，已经在established ehash中。

移除FIFO没有unhash H，也没有修改H的TCP状态。

普通TCP为什么可以立即释放R
-------------------------

TCP Fast Open场景可能在accept发生时仍等待三次握手最终ACK，因此会保留request并把 ``req->sk`` 清空。固定场景禁用TFO：

::

   tcp_rsk(R).tfo_listener = 0

所以不会进入Fast Open特殊分支。

``inet_csk_accept`` 随后：

::

   release_sock(L)
   reqsk_put(R)

R已经离开accept FIFO，也不再拥有ehash或request timer身份。固定场景中这次 ``reqsk_put`` 结束R的逻辑生命周期并释放request对象存储。

结果变为：

::

   listener accept queue = empty
   R                      = freed
   H                      = alive

H的生命周期并不依赖R继续存在；H拥有独立的protocol socket引用、ehash身份与bind ownership。

inet_init_csk_locks为什么在返回H前执行
-------------------------------------

accept queue中的H来自listener clone。返回给用户socket之前，路径调用：

::

   inet_init_csk_locks(H)

它为accepted connection重新初始化拥塞控制相关锁类别和使用统计所需状态，使child后续作为普通用户TCP socket运行。

随后：

::

   inet_csk_accept(L, &arg)
   → H

控制返回 ``inet_accept``。此时H已经不在listener accept queue中，却还没有与AS关联。

inet_accept为什么锁住H
----------------------

``inet_accept`` 得到H后执行：

::

   lock_sock(H)
   __inet_accept(S, AS, H)
   release_sock(H)

listener lock已经释放；现在锁住的是accepted child本身。这样 ``sock_graft`` 与socket API状态发布不会和H的协议处理并发修改冲突。

``__inet_accept`` 先处理可选的memcg socket accounting，并记录RPS flow。固定场景不改变网络数据状态，H仍然：

::

   H.sk_state = TCP_ESTABLISHED

状态检查允许ESTABLISHED、SYN_RECV及若干关闭中状态；固定命中ESTABLISHED。

sock_graft怎样建立AS与H的双向关系
--------------------------------

核心调用：

::

   sock_graft(H, AS)

入口要求：

::

   AS.sk == NULL

随后在 ``H.sk_callback_lock`` 写锁与BH disabled保护下执行：

::

   rcu_assign_pointer(H.sk_wq, &AS.wq)
   AS.sk = H
   sk_set_socket(H, AS)
   security_sock_graft(H, AS)

``sk_set_socket`` 写入：

::

   H.sk_socket = AS
   H.sk_uid     = I8.i_uid
   H.sk_ino     = I8.i_ino

因此graft之后形成：

::

   F8.private_data = AS
   AS.file         = F8
   AS.sk           = H
   H.sk_socket     = AS
   H.sk_wq         = &AS.wq

H从“没有用户socket外壳的已建立child”变为“由AS、I8和F8承载的用户可见socket endpoint”。

AS.state为什么在graft后才改为SS_CONNECTED
----------------------------------------

``sock_graft`` 只建立对象指针与wait queue关联。随后 ``__inet_accept`` 明确写入：

::

   AS.state = SS_CONNECTED

此时两层状态一致：

::

   socket API layer : AS.state   = SS_CONNECTED
   TCP layer        : H.sk_state = TCP_ESTABLISHED

H早在最终ACK时已经ESTABLISHED；AS直到本章才从 ``SS_UNCONNECTED`` 变成 ``SS_CONNECTED``。

这与主动连接client相反：client的 ``struct socket`` 从创建开始就存在，connect完成后更新其state；server child先在内核中完成握手，accept时才获得 ``struct socket``。

queue removal与graft之间有哪些暂态
----------------------------------

本章存在一个很短但重要的中间状态：

::

   R已经释放
   accept queue已经为空
   L.sk_ack_backlog=0
   H仍然TCP_ESTABLISHED
   AS.sk仍为NULL

随后 ``sock_graft`` 才建立AS/H关系。

固定路径在同一个parent syscall中连续执行，不释放H给用户态，也不发布fd 8。这个暂态用于理解对象顺序，不意味着用户程序能观察到“丢失的连接”。

本章没有网络活动
----------------

``inet_csk_accept`` 和 ``sock_graft`` 只操作内核对象、锁、引用与fd准备资源：

::

   no skb allocation
   no TCP segment
   no route lookup
   no NET_RX softirq
   no device transmission

client C保持TCP_ESTABLISHED，sequence number与队列均未变化。

固定源码依据
------------

以下链接全部固定到 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d``：

* `net/ipv4/af_inet.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/af_inet.c>`_： ``inet_accept``、 ``__inet_accept`` 与 ``SS_CONNECTED`` 更新；
* `net/ipv4/inet_connection_sock.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/ipv4/inet_connection_sock.c>`_： ``inet_csk_wait_for_connect``、 ``inet_csk_accept``、 ``reqsk_put`` 与 ``inet_init_csk_locks``；
* `include/net/request_sock.h <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/net/request_sock.h>`_：accept FIFO结构与 ``reqsk_queue_remove``；
* `include/net/sock.h <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/net/sock.h>`_： ``sock_graft`` 与 ``sk_set_socket`` 的具体指针写入。

本章结束状态
------------

::

   current executor          = parent
   CPU/mode                  = CPU0, x86-64 kernel process context
   current syscall           = accept4(6,&peer,&peer_len,SOCK_CLOEXEC)

   listener L                = TCP_LISTEN
   L accept head/tail        = NULL / NULL
   L.sk_ack_backlog          = 0
   SYN qlen/young            = 0 / 0

   accept node R             = released

   server child H            = TCP_ESTABLISHED
   H established ehash       = active
   H bind/bind2 owner        = active
   H.sk_socket               = AS
   H.sk_wq                   = &AS.wq

   accepted socket AS        = SS_CONNECTED
   AS.sk                     = H
   AS.file                   = F8

   accepted file F8          = allocated, blocking
   fdtable fd[8]             = NULL
   fd 8 open/cloexec bits    = reserved/set

   peer user buffer          = unchanged
   peer_len user value       = 16

   next entry                = inet_getname(AS,&address,peer=2)

下一章从 ``do_accept`` 获取peer sockaddr开始，完成用户地址写回、 ``fd_install(8,F8)`` 与 ``accept4`` 返回8。
