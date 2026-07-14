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

最新三章：

#. ``LK-UNIXSOCKCLOSE-167``：EPOLL_CTL_DEL怎样从persistent-ready Unix socket拆除callback与epitem？
#. ``LK-UNIXSOCKCLOSE-168``：close(6)怎样释放socket A，却让dead SA继续被peer reference保持？
#. ``LK-UNIXSOCKCLOSE-169``：close(7)与close(8)怎样释放两端Unix socket和空eventpoll？

进度
----

当前已经完成169章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

   runtime relation    = continuation of LK-UNIXSOCK-164..166
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   mm/files            = shared
   scheduling          = both SCHED_NORMAL
   socket fd           = 6 and 7 before close
   eventpoll fd        = 8 before close
   socket A / SA       = fd 6 endpoint, RCV_SHUTDOWN initially
   socket B / SB       = fd 7 endpoint, SEND_SHUTDOWN initially
   peer relation       = SA <-> SB initially
   registration        = fd 6, EPOLLIN|EPOLLRDHUP, persistent-ready
   callback            = P on socket A wait queue
   epitem              = I in EP.rbr and EP.rdllist
   eventpoll refcount  = 2 initially
   calls               = epoll_ctl DEL, close(6), close(7), close(8)
   failures/races      = none

完整控制流
----------

::

   parent epoll_ctl(8, EPOLL_CTL_DEL, 6, NULL)
   → resolve F8/EP and F6
   → lock EP.mtx and find I by (F6,fd6)
   → ep_unregister_pollwait removes P from A.wq.wait
   → free P synchronously
   → epi_fget temporarily pins F6
   → under F6.f_lock clear last watcher and publish F6.f_ep=NULL
   → remove I target-file reverse link
   → erase I from EP.rbr
   → remove persistent-ready I from EP.rdllist
   → kfree_rcu(I)
   → EP.refcount 2 -> 1
   → return 0

   parent close(6)
   → remove fd 6 and close-on-exec bit from shared fdtable
   → final synchronous __fput(F6)
   → F6.f_ep=NULL, so eventpoll target-release fastpath does nothing
   → sock_close
   → __sock_release(socket A)
   → unix_release(SA)
   → unix_release_sock removes SA from Unix socket table
   → sock_orphan(SA)
   → SA.sk_shutdown=SHUTDOWN_MASK
   → SA.sk_state=TCP_CLOSE
   → save skpair=SB and clear unix_peer(SA)
   → SB.sk_shutdown becomes SHUTDOWN_MASK
   → empty SA receive queue means SB.sk_err remains 0
   → SB.sk_state_change and async HUP notification
   → drop A-held peer reference to SB
   → drop A file/socket reference
   → SA remains alive because unix_peer(SB)=SA still holds a reference
   → release F6 and socket A sockfs VFS objects
   → close(6) returns 0

   parent close(7)
   → remove fd 7 and close-on-exec bit
   → final __fput(F7)
   → unix_release_sock(SB)
   → SB becomes orphan, TCP_CLOSE and SHUTDOWN_MASK
   → save skpair=SA and clear unix_peer(SB)
   → drop final peer reference to SA
   → unix_sock_destructor frees SA/UA
   → drop final SB reference
   → unix_sock_destructor frees SB/UB
   → release F7 and socket B sockfs VFS objects
   → close(7) returns 0

   parent close(8)
   → remove fd 8 and close-on-exec bit
   → final __fput(F8)
   → ep_eventpoll_release
   → ep_clear_and_put sees empty EP.rbr and EP.rdllist
   → no callback or epitem remains to drain
   → EP.refcount 1 -> 0
   → ep_free and kfree_rcu(EP)
   → release F8 and eventpoll pseudo path
   → close(8) returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：Unix stream socketpair data、half-close与最终teardown complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、``on_cpu=1``；
* helper：blocked outside released objects；
* ``EPOLL_CTL_DEL`` result：0；
* ``close(6)`` result：0；
* ``close(7)`` result：0；
* final syscall/result：``close(8)=0``；
* fd 6/7/8：closed and unallocated；
* callback ``P``：freed synchronously；
* epitem ``I``：logical lifetime ended，storage through RCU；
* socket files ``F6/F7``：freed；
* socket A/B sockfs VFS objects：freed；
* ``SA/UA``：freed；
* ``SB/UB``：freed；
* Unix peer references：none；
* eventpoll ``EP``：logical lifetime ended，storage through RCU；
* eventpoll file ``F8``：freed；
* global sockfs：active；
* global anon_inodefs：active；
* filesystem/block/device/network packet I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. persistent-ready registration可以直接通过DEL删除，无需先消费readiness。
#. callback在DEL中同步free；epitem通过RCU延迟free。
#. ``F6.f_ep=NULL`` 使close(6)跳过eventpoll target-release慢路径。
#. ``unix_release_sock`` 把关闭端设为orphan、``TCP_CLOSE``和``SHUTDOWN_MASK``。
#. close(6)只清除 ``unix_peer(SA)``，不会同步清除 ``unix_peer(SB)``。
#. fd 6关闭后，dead SA仍由SB的peer reference保持。
#. peer B得到完整shutdown/HUP语义，但直到close(7)才进入 ``TCP_CLOSE``。
#. close(7)清除最后peer pointer并释放SA的最后peer reference。
#. socket file、sockfs VFS对象和 ``struct sock`` 具有不同生命周期边界。
#. 两端queue为空，因此关闭不产生 ``ECONNRESET`` 或skb丢弃分支。
#. eventpoll file持有最后base reference；close(8)使EP refcount归零。
#. sockfs与anon_inodefs是全局pseudo filesystems，不随本场景fd关闭而卸载。

下一任务
--------

当前场景完整闭环。优先候选是TCP/IPv4 loopback连接建立：

::

   server socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0)
   → bind(127.0.0.1:fixed_port)
   → listen(backlog)
   client socket(AF_INET, SOCK_STREAM|SOCK_CLOEXEC, 0)
   → connect(127.0.0.1:fixed_port)
   → loopback route and SYN/SYN-ACK/ACK processing
   → accept4 publishes connected server fd

开始前必须固定network namespace、loopback device、route、port、socket states、request socket、softirq与scheduler顺序。
