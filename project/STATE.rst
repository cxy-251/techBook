项目状态
========

最后更新
--------

2026-07-14

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

最新三章：

#. ``LK-TCPLISTEN-170``：socket(AF_INET,SOCK_STREAM)怎样创建TCP endpoint并发布fd 6？
#. ``LK-TCPLISTEN-171``：bind(127.0.0.1:28080)怎样验证本地地址并占用TCP端口？
#. ``LK-TCPLISTEN-172``：listen(8)怎样建立空请求队列并把socket加入TCP监听哈希？

进度
----

当前已经完成172章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

本批固定场景
------------

::

   runtime relation     = new TCP/IPv4 loopback scenario after chapter 169
   CPUs online          = CPU0 only
   executor             = parent
   helper               = blocked outside listener objects
   scheduling           = parent remains SCHED_NORMAL and running
   network namespace    = N
   loopback device      = lo UP
   loopback address     = 127.0.0.1/8
   local route          = present before scenario
   occupied fds         = 0..5
   server fd            = 6
   server file          = F6
   server socket        = S
   TCP control block    = L/LINET/LICSK/LTP
   bind address         = 127.0.0.1
   bind port            = 28080
   listen backlog       = 8
   somaxconn            = at least 8
   SO_REUSEADDR         = disabled
   SO_REUSEPORT         = disabled
   server TCP Fast Open = disabled
   failures/races       = none
   packet I/O           = none in chapters 170..172

完整控制流
----------

::

   parent socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0)
   → __sys_socket_create validates family, type and flags
   → __sock_create allocates sockfs inode IS and struct socket S
   → inet_create selects inet_stream_ops and tcp_prot
   → sk_alloc creates one tcp_sock object LTP
   → sock_init_data links S and L
   → S.state=SS_UNCONNECTED
   → L.sk_state=TCP_CLOSE
   → tcp_v4_init_sock and tcp_init_sock initialize TCP control state
   → sock_map_fd reserves fd 6 with close-on-exec
   → sock_alloc_file creates blocking socket file F6
   → fd_install publishes F6 at fd 6
   → socket returns 6

   parent bind(6,127.0.0.1:28080)
   → resolve F6/S/L
   → copy sockaddr_in into kernel storage
   → inet_bind enters __inet_bind under socket lock
   → local table classifies 127.0.0.1 as RTN_LOCAL
   → verify TCP_CLOSE and inet_num=0
   → set inet_rcv_saddr and inet_saddr
   → tcp_prot.get_port enters inet_csk_get_port
   → create/find inet_bind_bucket TB for N/28080/l3mdev0
   → create/find inet_bind2_bucket TB2 for 127.0.0.1:28080
   → conflict check succeeds
   → inet_bind_hash attaches L to TB2 owners
   → inet_num=28080; inet_sport=htons(28080)
   → set SOCK_BINDADDR_LOCK and SOCK_BINDPORT_LOCK
   → remain SS_UNCONNECTED/TCP_CLOSE
   → bind returns 0

   parent listen(6,8)
   → __sys_listen_socket keeps effective backlog at 8
   → inet_listen validates SS_UNCONNECTED and SOCK_STREAM
   → __inet_listen_sk sets sk_max_ack_backlog=8
   → server Fast Open branch remains disabled
   → inet_csk_listen_start initializes empty request/accept queue
   → sk_ack_backlog=0
   → TCP_CLOSE→TCP_LISTEN
   → inet_csk_get_port revalidates port 28080
   → existing bind ownership remains unchanged
   → inet_hash chooses exact-address lhash2 bucket ILB2
   → set SOCK_RCU_FREE
   → RCU-publish L in ILB2
   → listen returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：TCP/IPv4 loopback server listener setup complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、``on_cpu=1``；
* helper：blocked outside listener objects；
* final syscall/result：``listen(6,8)=0``；
* fd 6：open、blocking、close-on-exec；
* file ``F6``：active sockfs socket file；
* socket ``S``：``SS_UNCONNECTED``、``SOCK_STREAM``；
* TCP socket ``L/LTP``：``TCP_LISTEN``；
* local endpoint：``127.0.0.1:28080``；
* remote endpoint：unset；
* bind bucket ``TB``：active；
* bind2 bucket ``TB2``：active，owners包含 ``L``；
* listener bucket ``ILB2``：active，包含 ``L``；
* ``sk_max_ack_backlog=8``；
* ``sk_ack_backlog=0``；
* request queue：empty；
* accept queue：empty；
* Fast Open queue：empty；
* request socket：none；
* accepted child：none；
* route/dst cache：empty；
* skb/packet：none；
* filesystem/block/device packet I/O：none；
* next runtime entry：client ``socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)``。

关键边界
--------

#. protocol 0在AF_INET/``SOCK_STREAM``下选择TCP。
#. sockfs inode/``struct socket``、socket file与``struct tcp_sock``具有不同对象边界。
#. ``SS_UNCONNECTED``与``TCP_CLOSE``/``TCP_LISTEN``属于不同状态层。
#. 单个socket在协议对象创建完成后才reserve并发布fd。
#. ``SOCK_CLOEXEC``由fdtable close-on-exec bit实现。
#. bind验证local address并建立bind ownership，不发布listener lookup身份。
#. ``inet_bind_bucket``与``inet_bind2_bucket``分别表达port domain与address-specific ownership。
#. ``inet_num``为host order，``inet_sport``为network order。
#. 第一次listen初始化空request/accept queue，backlog不等于预分配对象数量。
#. listen在hash发布前写``TCP_LISTEN``，lookup可见性仍由lhash2 membership决定。
#. listen重新验证bound port，不重复插入已有bind owner。
#. exact-address listener优先于``INADDR_ANY``回退查找。
#. listener设置``SOCK_RCU_FREE``并通过RCU可见的nulls list发布。
#. socket/bind/listen阶段没有route output、skb、SYN或loopback packet。

下一任务
--------

服务器listener已经建立。下一批优先进入client connect与普通三次握手前半段：

::

   client socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0)
   → publish fd 7
   → connect(fd 7,127.0.0.1:28080)
   → choose loopback route and ephemeral source port
   → enter TCP_SYN_SENT
   → build and transmit SYN
   → listener lookup finds L
   → allocate and hash request_sock
   → send SYN-ACK

开始前必须固定client ephemeral port、route result、initial sequence numbers、TCP options、softirq/NAPI边界、request socket引用、CPU0执行顺序与parent在blocking connect中的睡眠位置。
