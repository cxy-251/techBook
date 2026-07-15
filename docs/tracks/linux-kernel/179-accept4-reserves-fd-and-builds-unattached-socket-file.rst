第一百七十九章：accept4怎样先预留fd 8并创建尚未graft的socket与file？
=================================================================

上一章结束时，TCP三次握手已经完成，parent回到CPU0用户态。client fd 7已经连接；server child ``H`` 已经进入listener ``L`` 的accept queue，却还没有面向用户态的 ``struct socket``、sockfs file或fd：

::

   listener L
       fd                    = 6
       state                 = TCP_LISTEN
       accept head/tail      = R/R
       sk_ack_backlog        = 1

   accept node R
       R.sk                  = H

   server child H
       state                 = TCP_ESTABLISHED
       local                 = 127.0.0.1:28080
       remote                = 127.0.0.1:40000
       established ehash     = active
       bind/bind2 owner      = active
       sk_socket             = NULL
       sockfs file/fd        = none

本章执行：

.. code-block:: c

   struct sockaddr_in peer = {0};
   socklen_t peer_len = sizeof(peer);

   int accepted_fd = accept4(6,
                             (struct sockaddr *)&peer,
                             &peer_len,
                             SOCK_CLOEXEC);

本章只追踪syscall入口、fd 8预留、accepted ``struct socket AS`` 与sockfs file ``F8`` 的创建。叙事停在协议 ``accept`` 即将从listener队列取出 ``R/H`` 的位置。

本章固定：

* fd 0至7已经占用，fd 8是最低空闲描述符；
* ``peer_len`` 初值为 ``sizeof(struct sockaddr_in)=16``；
* ``flags=SOCK_CLOEXEC``，没有 ``SOCK_NONBLOCK``；
* listener file ``F6`` 是blocking sockfs file；
* accept queue在调用开始前已经非空；
* 不启用TCP Fast Open、MPTCP、BPF重定向或reuseport迁移；
* fd、inode、file与安全检查分配全部成功；
* 当前只有parent与CPU0，不发生调度、softirq或网络包处理。

accept4怎样找到listener file
----------------------------

x86-64 syscall入口最终进入：

::

   __x64_sys_accept4
   → __se_sys_accept4
   → __do_sys_accept4
   → __sys_accept4(6, &peer, &peer_len, SOCK_CLOEXEC)

``__sys_accept4`` 使用fd class取得fd 6对应的file：

::

   fd 6
   → file F6
   → F6.private_data
   → listener struct socket S
   → S.sk
   → listener tcp_sock L

如果fd 6未打开，会立即返回 ``-EBADF``。固定场景中F6仍然有效，因此进入：

::

   __sys_accept4_file(F6,
                      &peer,
                      &peer_len,
                      SOCK_CLOEXEC)

此时只解析了listener fd；accept queue中的R/H尚未移动。

flags检查为什么保留SOCK_CLOEXEC
-------------------------------

``__sys_accept4_file`` 只接受：

::

   SOCK_CLOEXEC
   SOCK_NONBLOCK

固定调用只有：

::

   flags = SOCK_CLOEXEC

所以不会触发 ``-EINVAL``，也不会执行 ``SOCK_NONBLOCK`` 到 ``O_NONBLOCK`` 的转换。随后执行：

::

   FD_ADD(flags,
          do_accept(F6,
                    &arg,
                    &peer,
                    &peer_len,
                    flags))

这里最容易产生错误理解： ``FD_ADD`` 不是先执行完整 ``do_accept`` 再寻找fd。宏展开后，fd reservation发生在file构造表达式之前。

FD_ADD为什么先预留fd 8
----------------------

``FD_ADD`` 通过 ``FD_PREPARE`` 初始化组合资源：

::

   get_unused_fd_flags(SOCK_CLOEXEC)
   → alloc_fd(0, RLIMIT_NOFILE, O_CLOEXEC)

fdtable扫描从最低可用位置开始。fd 0至7已经占用，因此选择：

::

   reserved fd = 8

``alloc_fd`` 在 ``files->file_lock`` 下更新：

::

   open_fds[8]       : 0 → 1
   close_on_exec[8]  : 0 → 1
   files->next_fd    : 8 → 9
   fdtable.fd[8]       = NULL

这是一种“描述符槽位已经忙，但file尚未发布”的中间状态。

``open_fds`` bit阻止同一fdtable中的并发分配再次选择8； ``close_on_exec`` bit已经按 ``SOCK_CLOEXEC`` 设置；真正的file pointer仍然是NULL，用户态也尚未收到返回值。

只有fd reservation成功后，宏才计算第二个表达式：

::

   do_accept(F6, ...)

如果后续任一步失败， ``fd_prepare`` cleanup会调用 ``put_unused_fd(8)`` 清除这个预留槽位。

do_accept怎样分配accepted socket AS
-----------------------------------

``do_accept`` 先把F6验证为socket file：

::

   sock = sock_from_file(F6)
   → listener struct socket S

随后调用：

::

   newsock = sock_alloc()
   → accepted struct socket AS

``sock_alloc`` 通过sockfs伪文件系统分配一个新inode，并取得嵌在 ``struct socket_alloc`` 中的socket对象。固定命名：

::

   accepted sockfs inode = I8
   accepted socket       = AS

新inode写入：

::

   I8.i_ino  = new unique inode number
   I8.i_mode = S_IFSOCK | S_IRWXUGO
   I8.i_uid  = current_fsuid()
   I8.i_gid  = current_fsgid()
   I8.i_op   = sockfs_inode_ops

sockfs inode allocator已经初始化AS：

::

   AS.state       = SS_UNCONNECTED
   AS.flags       = 0
   AS.ops         = NULL
   AS.sk          = NULL
   AS.file        = NULL
   AS.wq.wait     = initialized empty wait queue
   AS.wq.fasync   = NULL

这里创建的是用户socket API层对象，不是新的TCP endpoint。完整TCP endpoint仍然是accept queue中的H。

为什么AS先复制listener的type与ops
--------------------------------

``do_accept`` 读取listener protocol operations：

::

   ops = READ_ONCE(S.ops)

再写入：

::

   AS.type = S.type = SOCK_STREAM
   AS.ops  = S.ops  = inet_stream_ops

accepted socket与listener同属AF_INET stream接口，所以复用同一组 ``proto_ops``。代码同时增加 ``ops->owner`` module reference；listener本身已经保持该module可用，这里为新socket独立持有生命周期。

此刻仍然满足：

::

   AS.sk = NULL
   H.sk_socket = NULL

复制 ``type`` 与 ``ops`` 没有完成graft，也没有改变H。

sock_alloc_file怎样建立F8
-------------------------

在调用协议accept之前， ``do_accept`` 已经执行：

::

   F8 = sock_alloc_file(AS,
                        SOCK_CLOEXEC,
                        L.sk_prot_creator->name)

对TCP而言protocol name为 ``TCP``。 ``sock_alloc_file`` 使用AS对应的sockfs inode I8建立file：

::

   alloc_file_pseudo(I8,
                     sock_mnt,
                     "TCP",
                     O_RDWR | (flags & O_NONBLOCK),
                     socket_file_ops)

固定flags中没有 ``O_NONBLOCK``，所以F8的file status是：

::

   F8.f_flags contains O_RDWR
   F8.f_flags does not contain O_NONBLOCK

``SOCK_CLOEXEC`` 不会成为file status flag。它已经在fdtable的 ``close_on_exec[8]`` 中表达。

file与socket建立双向关系：

::

   AS.file          = F8
   F8.private_data  = AS
   F8.f_op          = socket_file_ops
   F8 path          = sockfs inode I8

``stream_open`` 还会为stream file设置标准的不可seek语义。此时：

::

   fdtable.fd[8] = NULL
   AS.file       = F8
   AS.sk         = NULL

所以“file已经存在”与“fd已经发布”仍然是两个不同阶段。

security_socket_accept发生在queue removal之前
---------------------------------------------

F8建立成功后， ``do_accept`` 调用：

::

   security_socket_accept(S, AS)

固定安全策略允许。随后：

::

   arg.flags |= F6.f_flags

这组 ``arg.flags`` 用于协议层决定accept等待是否允许阻塞。F6是blocking file，accept4也没有要求 ``SOCK_NONBLOCK``，因此协议层可以等待。

当前accept queue已经非空，后续不会实际进入wait queue。

关键边界
--------

``SOCK_CLOEXEC`` 同时出现在accept4 flags中，却影响不同位置：

::

   fdtable close_on_exec bit = set
   accepted file O_NONBLOCK  = not set

因此最终fd 8会是：

::

   blocking
   close-on-exec

还必须区分三层对象：

::

   AS = struct socket          # 已分配，尚未连接H
   F8 = struct file            # 已分配，尚未fd_install
   H  = struct tcp_sock        # 已ESTABLISHED，仍在accept queue

本章没有从accept queue移除R，没有减少 ``L.sk_ack_backlog``，没有调用 ``sock_graft``。

固定源码依据
------------

以下链接全部固定到 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d``：

* `net/socket.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/net/socket.c>`_： ``__sys_accept4``、 ``__sys_accept4_file``、 ``do_accept``、 ``sock_alloc`` 与 ``sock_alloc_file``；
* `include/linux/file.h <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/file.h>`_： ``FD_PREPARE``、 ``FD_ADD``、 ``fd_publish`` 与失败清理；
* `fs/file.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_： ``alloc_fd``、 ``get_unused_fd_flags``、 ``put_unused_fd`` 与fdtable位图更新。

本章结束状态
------------

::

   current executor          = parent
   CPU/mode                  = CPU0, x86-64 kernel process context
   current syscall           = accept4(6,&peer,&peer_len,SOCK_CLOEXEC)

   fd 6 / F6 / S / L         = unchanged
   fd 7 / client C           = unchanged, TCP_ESTABLISHED

   fd 8 slot                 = reserved
   open_fds[8]               = 1
   close_on_exec[8]          = 1
   fdtable.fd[8]             = NULL

   accepted inode I8         = allocated in sockfs
   accepted socket AS        = SS_UNCONNECTED
   AS.type / AS.ops          = SOCK_STREAM / inet_stream_ops
   AS.sk                     = NULL
   AS.file                   = F8

   accepted file F8          = allocated, O_RDWR, blocking
   F8.private_data           = AS
   F8 published in fdtable   = no

   listener accept queue     = R/H still present
   L.sk_ack_backlog          = 1
   server child H            = TCP_ESTABLISHED; sk_socket=NULL

   next entry                = inet_stream_ops.accept(S,AS,&arg)

下一章从 ``inet_accept`` 调用TCP的 ``inet_csk_accept`` 开始，取出accept node R与server child H，再把H graft到AS。
