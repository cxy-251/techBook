第一百八十一章：peer地址怎样写回用户态并最终发布close-on-exec fd 8？
=================================================================

上一章结束时，listener accept queue已经清空，accept node ``R`` 已经释放，server child ``H`` 已经graft到accepted socket ``AS``：

::

   listener L
       state          = TCP_LISTEN
       accept queue   = empty
       sk_ack_backlog = 0

   accepted chain
       F8.private_data = AS
       AS.file         = F8
       AS.sk           = H
       AS.state        = SS_CONNECTED
       H.sk_socket     = AS
       H.sk_state      = TCP_ESTABLISHED

   fd 8 preparation
       open bit        = 1
       close-on-exec   = 1
       fdtable.fd[8]   = NULL

``do_accept`` 的协议accept已经成功。本章继续完成peer地址获取、用户缓冲区复制与fd发布，最终让：

::

   accept4(...) = 8

本章固定 ``peer_len`` 初值16，用户地址缓冲区可写，所有copy与audit成功，不发生并发close。

do_accept为什么在fd发布前读取peer地址
------------------------------------

协议accept返回0后， ``do_accept`` 检查：

::

   upeer_sockaddr != NULL

固定调用传入 ``&peer``，因此执行：

::

   len = AS.ops->getname(AS,
                         (struct sockaddr *)&address,
                         peer=2)
       = inet_getname(AS, &address, 2)

此时F8尚未进入fdtable。这样如果peer地址获取或copy失败，syscall仍能统一回滚未发布的file与fd reservation。

inet_getname怎样从H生成peer sockaddr
----------------------------------

``inet_getname`` 通过：

::

   AS.sk = H

取得：

::

   struct inet_sock *inet = inet_sk(H)

先写入：

::

   sin_family = AF_INET

随后锁住H。参数 ``peer=2`` 选择peer分支，读取：

::

   sin_port        = H.inet_dport
   sin_addr.s_addr = H.inet_daddr

server child H的remote endpoint来自client：

::

   H.inet_dport = htons(40000)
   H.inet_daddr = 127.0.0.1

因此kernel ``sockaddr_in`` 结果为：

::

   address.sin_family      = AF_INET
   address.sin_port        = htons(40000)
   address.sin_addr        = 127.0.0.1
   address.sin_zero[0..7]  = 0
   returned len            = 16

H处于 ``TCP_ESTABLISHED``，peer endpoint完整，连接检查成功。函数释放H socket lock后返回16。

peer=2与普通getpeername有什么差异
--------------------------------

``inet_getname`` 对 ``peer`` 的主要分支判断使用非零值。内部某个关闭状态检查只在 ``peer==1`` 时应用；accept路径固定传2，用于接受刚从协议层返回的socket状态集合。

本场景H已经ESTABLISHED，所以无论该细节如何，最终都会返回client地址。关键结论是：accept写回的peer是连接发起者：

::

   127.0.0.1:40000

不是listener自己的 ``127.0.0.1:28080``。

move_addr_to_user怎样处理peer_len
--------------------------------

``do_accept`` 调用：

::

   move_addr_to_user(&address,
                     klen=16,
                     &peer,
                     &peer_len)

函数先从用户空间读取：

::

   user supplied len = peer_len = 16

并计算copy长度：

::

   copy_len = min(user_len, kernel_len)
            = min(16,16)
            = 16

随后把真实kernel长度写回：

::

   peer_len = 16

最后复制完整 ``sockaddr_in`` 16字节到用户buffer。

syscall仍在内核态运行，用户代码要等accept4返回后才能读取结果。固定成功后的用户态内容将是：

.. code-block:: c

   peer.sin_family      == AF_INET
   ntohs(peer.sin_port) == 40000
   peer.sin_addr        == 127.0.0.1
   peer_len             == sizeof(struct sockaddr_in)

为什么地址copy失败会关闭已经取出的H
----------------------------------

对象顺序意味着：peer copy发生时，H已经从accept queue取出并graft到AS。如果 ``inet_getname`` 或 ``move_addr_to_user`` 失败， ``do_accept`` 会进入：

::

   out_fd:
       fput(F8)
       return ERR_PTR(error)

F8的最终 ``__fput`` 会释放AS并关闭其H；外层 ``FD_ADD`` cleanup再调用：

::

   put_unused_fd(8)

恢复fdtable reservation。

因此错误不会把H重新插回listener accept queue。POSIX accept语义允许连接已经被内核取出后，因为用户地址复制错误而被关闭。

固定场景没有错误，F8继续返回给 ``FD_ADD``。

do_accept返回F8时fd 8仍未可用
----------------------------

成功路径执行：

::

   do_accept(...)
   → F8

此时：

::

   F8 is valid
   AS/H are connected
   peer address copied
   fdtable.fd[8] is still NULL

file构造表达式完成后， ``FD_PREPARE`` 同时持有：

::

   prepared fd   = 8
   prepared file = F8
   error         = 0

随后才允许发布。

fd_publish怎样调用fd_install
----------------------------

``FD_ADD`` 成功分支调用：

::

   fd_publish(prepared)

核心操作是：

::

   fd_install(8, F8)

普通无resize路径在RCU sched read-side critical section中取得当前fdtable，并执行：

::

   rcu_assign_pointer(fdtable.fd[8], F8)

fd 8的状态因此从：

::

   open_fds[8]      = 1
   close_on_exec[8] = 1
   fd[8]            = NULL

变为：

::

   open_fds[8]      = 1
   close_on_exec[8] = 1
   fd[8]            = F8

``fd_install`` 消费准备阶段持有的file reference。 ``fd_publish`` 再清空cleanup对象中的file与fd ownership，避免scope结束时回滚已经发布的资源。

为什么fd 8是blocking且close-on-exec
----------------------------------

两个属性存放在不同位置：

::

   blocking/nonblocking  → F8.f_flags O_NONBLOCK bit
   close-on-exec         → fdtable.close_on_exec[8]

``sock_alloc_file`` 只从accept4 flags提取 ``O_NONBLOCK``。固定调用没有 ``SOCK_NONBLOCK``，所以：

::

   F8 is blocking

``get_unused_fd_flags`` 在reservation阶段识别 ``SOCK_CLOEXEC/O_CLOEXEC``，所以：

::

   fd 8 is close-on-exec

listener F6的file status不会自动复制成accepted F8的status。accepted file是否nonblocking由本次accept4 flags决定。

accept4怎样返回8
----------------

``fd_publish`` 返回准备好的fd number：

::

   8

调用链逐层返回：

::

   __sys_accept4_file → 8
   __sys_accept4      → 8
   __do_sys_accept4   → 8
   syscall exit       → userspace RAX = 8

parent回到CPU0 CPL3后：

.. code-block:: c

   accepted_fd == 8

此时用户态首次能够通过fd 8访问H。

accept完成后三个socket endpoint怎样对应
--------------------------------------

最终对象关系：

::

   fd 6
   → F6
   → listener socket S
   → listener tcp_sock L
   → 127.0.0.1:28080 TCP_LISTEN

   fd 7
   → client file F7
   → client socket CS
   → client tcp_sock C
   → 127.0.0.1:40000 → 127.0.0.1:28080 TCP_ESTABLISHED

   fd 8
   → accepted file F8
   → accepted socket AS
   → server child tcp_sock H
   → 127.0.0.1:28080 ← 127.0.0.1:40000 TCP_ESTABLISHED

L与H共享本地端口28080的bind体系，承担不同角色：

* L保留在listener hash中，继续接收新的SYN；
* H保留在established hash中，只处理当前四元组的数据。

accept没有复制TCP连接
--------------------

``accept4`` 返回的新fd不是新建第二条TCP连接。三次握手创建的H始终是同一个protocol object：

::

   before accept : H without struct socket/file/fd
   after accept  : H grafted to AS/F8/fd8

本章新增的是用户访问路径，不是新的SYN、ACK、route或sequence空间。

本章结束状态
------------

::

   system_state              = SYSTEM_RUNNING
   current executor          = parent
   CPU/mode                  = CPU0, x86-64 CPL 3
   last syscall/result       = accept4(6,&peer,&peer_len,SOCK_CLOEXEC) = 8
   parent state              = TASK_RUNNING
   accept schedule count     = 0

   fd 6                      = open, blocking, close-on-exec
   listener L                = TCP_LISTEN
   L endpoint                = 127.0.0.1:28080
   L accept queue            = empty
   L.sk_ack_backlog          = 0
   L bind/lhash2             = active

   accept node R             = released

   fd 7                      = open, blocking, close-on-exec
   client C                  = TCP_ESTABLISHED
   C endpoint                = 127.0.0.1:40000 → 127.0.0.1:28080
   C ehash/bind/dst          = active

   fd 8                      = open, blocking, close-on-exec
   fdtable.fd[8]             = F8
   accepted file F8          = active sockfs file
   accepted socket AS        = SS_CONNECTED
   AS.sk                     = H
   server child H            = TCP_ESTABLISHED
   H endpoint                = 127.0.0.1:28080 ← 127.0.0.1:40000
   H established ehash       = active
   H bind/bind2 owner        = active
   H.sk_socket               = AS
   H.sk_wq                   = &AS.wq

   peer user sockaddr        = AF_INET 127.0.0.1:40000
   peer_len                  = 16

   packet/softirq backlog    = empty
   next entry                = write(7,"hello",5)

下一章从client fd 7的 ``write`` 开始，追踪5字节数据怎样进入TCP write queue、通过loopback命中H，并使accepted fd 8变为可读。
