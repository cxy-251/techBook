项目状态
========

最后更新
--------

2026-07-15

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097
   LK-EXEC-098..LK-EXEC-100
   LK-EXIT-101..LK-EXIT-103
   LK-OPEN-104..LK-OPEN-106
   LK-DELALLOC-107..LK-DELALLOC-109
   LK-UNLINK-110..LK-UNLINK-112
   LK-SLEEP-113..LK-SLEEP-115
   LK-SIGNAL-116..LK-SIGNAL-118
   LK-PIPE-119..LK-PIPE-121
   LK-PIPECLOSE-122..LK-PIPECLOSE-124
   LK-FUTEX-125..LK-FUTEX-127
   LK-EVENTFD-128..LK-EVENTFD-130
   LK-EVENTFDCLOSE-131..LK-EVENTFDCLOSE-133
   LK-EPOLL-134..LK-EPOLL-136
   LK-EPOLLCLOSE-137..LK-EPOLLCLOSE-139
   LK-SIGNALFD-140..LK-SIGNALFD-142
   LK-SIGNALFDCLOSE-143..LK-SIGNALFDCLOSE-145
   LK-TIMERFD-146..LK-TIMERFD-148
   LK-TIMERFDCLOSE-149..LK-TIMERFDCLOSE-151
   LK-PIDFD-152..LK-PIDFD-154
   LK-PIDFDCLOSE-155..LK-PIDFDCLOSE-157
   LK-INOTIFY-158..LK-INOTIFY-160
   LK-INOTIFYCLOSE-161..LK-INOTIFYCLOSE-163
   LK-UNIXSOCK-164..LK-UNIXSOCK-166
   LK-UNIXSOCKCLOSE-167..LK-UNIXSOCKCLOSE-169
   LK-TCPLISTEN-170..LK-TCPLISTEN-172
   LK-TCPCONNECT-173..LK-TCPCONNECT-175
   LK-TCPHANDSHAKE-176..LK-TCPHANDSHAKE-178
   LK-TCPACCEPT-179..LK-TCPACCEPT-181

最新三章：

#. ``LK-TCPACCEPT-179``：accept4怎样先预留fd 8并创建尚未graft的socket与file？
#. ``LK-TCPACCEPT-180``：inet_csk_accept怎样取出R/H并把child graft到accepted socket？
#. ``LK-TCPACCEPT-181``：peer地址怎样写回用户态并最终发布close-on-exec fd 8？

进度
----

当前已经完成181章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

固定accept调用
--------------

.. code-block:: c

   struct sockaddr_in peer = {0};
   socklen_t peer_len = sizeof(peer);

   int accepted_fd = accept4(6,
                             (struct sockaddr *)&peer,
                             &peer_len,
                             SOCK_CLOEXEC);

固定条件：

::

   CPUs online            = CPU0 only
   network namespace      = N
   listener fd            = 6
   listener endpoint      = 127.0.0.1:28080
   listener file mode     = blocking, close-on-exec
   client fd              = 7
   client endpoint        = 127.0.0.1:40000
   client/server state    = TCP_ESTABLISHED/TCP_ESTABLISHED
   accept queue before    = one node R with R.sk=H
   flags                  = SOCK_CLOEXEC
   peer buffer length     = 16
   TFO/MPTCP              = disabled
   failures/races         = none

完整控制流
----------

::

   accept4(6,&peer,&peer_len,SOCK_CLOEXEC)
   → __sys_accept4 resolves F6
   → __sys_accept4_file validates flags
   → FD_ADD invokes get_unused_fd_flags first
   → reserve lowest free fd 8
   → open_fds[8]=1; close_on_exec[8]=1; fdtable.fd[8]=NULL

   do_accept(F6,...)
   → sock_from_file obtains listener socket S and L
   → sock_alloc creates sockfs inode I8 and socket AS
   → AS.state=SS_UNCONNECTED; AS.sk=NULL; AS.file=NULL
   → copy S.type/S.ops to AS
   → sock_alloc_file creates blocking socket file F8
   → AS.file=F8; F8.private_data=AS
   → security_socket_accept succeeds
   → arg.flags includes listener F6 flags

   inet_accept(S,AS,&arg)
   → tcp_prot.accept invokes inet_csk_accept(L,&arg)
   → lock L and see non-empty accept queue
   → no inet_csk_wait_for_connect and no schedule
   → reqsk_queue_remove returns R
   → L.sk_ack_backlog 1→0
   → accept head/tail become NULL
   → newsk=R.sk=H
   → no TFO special case
   → release L and reqsk_put(R)
   → R lifetime ends
   → inet_init_csk_locks(H)

   __inet_accept(S,AS,H)
   → lock H
   → sock_graft(H,AS)
   → H.sk_wq=&AS.wq
   → AS.sk=H
   → H.sk_socket=AS
   → H.sk_uid/sk_ino inherit I8 identity
   → AS.state=SS_CONNECTED
   → release H

   do_accept peer copy
   → inet_getname(AS,peer=2)
   → sockaddr_in AF_INET 127.0.0.1:40000
   → move_addr_to_user copies 16 bytes
   → peer_len remains 16
   → do_accept returns F8

   FD_ADD publish
   → fd_install(8,F8)
   → fdtable.fd[8]=F8
   → cleanup ownership cleared
   → accept4 returns 8 to userspace

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* last syscall/result：``accept4(6,&peer,&peer_len,SOCK_CLOEXEC)=8``；
* parent：``TASK_RUNNING``；
* scheduler：本次accept没有调用 ``schedule_timeout``；
* server fd 6：open、blocking、close-on-exec；
* listener ``L``：``TCP_LISTEN``；
* listener endpoint：``127.0.0.1:28080``；
* listener bind hash与lhash2：active；
* listener SYN qlen/young：0/0；
* listener accept queue：empty；
* listener ``sk_ack_backlog=0``；
* accept node ``R``：released；
* client fd 7：open、blocking、close-on-exec；
* client ``CS``：``SS_CONNECTED``；
* client ``C``：``TCP_ESTABLISHED``；
* client tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* client bind/bind2/ehash/dst：active；
* accepted fd 8：open、blocking、close-on-exec；
* accepted file ``F8``：active sockfs file；
* accepted socket ``AS``：``SS_CONNECTED``；
* ``AS.sk=H``、``AS.file=F8``；
* server child ``H``：``TCP_ESTABLISHED``；
* H tuple：``127.0.0.1:28080 ← 127.0.0.1:40000``；
* H established ehash：active；
* H bind/bind2 ownership：active；
* ``H.sk_socket=AS``；
* ``H.sk_wq=&AS.wq``；
* peer sockaddr：``AF_INET 127.0.0.1:40000``；
* ``peer_len=16``；
* packet与CPU0 NET_RX backlog：empty；
* next runtime entry：``write(7,"hello",5)``。

关键边界
--------

#. fd 8在accepted socket/file创建前已经被reservation标记为open与close-on-exec，但file pointer仍为NULL。
#. accepted ``struct socket AS``、sockfs inode I8与file F8在协议accept之前创建。
#. ``SOCK_CLOEXEC``不等于nonblocking；F8只含O_RDWR，没有O_NONBLOCK。
#. queue非空，所以blocking accept不会进入exclusive wait queue。
#. ``reqsk_queue_remove``只更新accept FIFO与``sk_ack_backlog``，不会修改SYN qlen/young。
#. R释放后H继续依靠自己的socket引用、ehash和bind ownership存活。
#. ``sock_graft``建立H到AS的socket、wait queue、uid与inode identity。
#. H在accept前已经TCP_ESTABLISHED；AS在graft后才SS_CONNECTED。
#. peer地址是client endpoint，不是listener本地endpoint。
#. peer copy在fd发布前进行；失败会关闭已经取出的H并释放fd reservation。
#. ``fd_install``是fd 8从预留槽位变为可查找file的发布点。
#. accept不产生任何TCP packet或softirq。
#. 下一批不得重新讲accept，应直接进入client data write与server receive。

下一任务
--------

::

   write(7,"hello",5)
   → resolve F7/CS/C
   → tcp_sendmsg_locked copies five bytes
   → append skb to client write queue
   → tcp_push/tcp_write_xmit assigns seq C_ISN+1
   → send data through IPv4 output and lo
   → established lookup finds H
   → tcp_rcv_established validates ACK and sequence
   → queue hello on H.sk_receive_queue
   → H.sk_data_ready exposes readability on fd 8
   → write returns 5
   → read(8,buf,5) consumes hello

开始前必须固定data segment flags、client send queue与write sequence、loopback NET_RX嵌套时序、H receive queue字段、ACK生成策略、write返回时点和server read是否发生真实等待。
