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

最新三章：

#. ``LK-UNIXSOCK-164``：socketpair怎样建立双向Unix stream并让parent阻塞在epoll_wait？
#. ``LK-UNIXSOCK-165``：helper写入hello时，Unix stream skb怎样唤醒epoll并让read返回5？
#. ``LK-UNIXSOCK-166``：shutdown(SHUT_WR)怎样让peer收到EPOLLRDHUP并让read返回EOF？

进度
----

当前已经完成166章。项目没有预设固定总章数，也没有固定195章目标。后续按源码主线与必要场景自然推进，完成条件由内容覆盖与叙事闭环决定，因此当前不计算“剩余章数”。

当前主线已经完成启动、VFS读写、进程/内存、调度/信号、多种fd通知机制，并开始进入Unix socket网络IPC路径。

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

   runtime relation      = independent scenario after LK-INOTIFYCLOSE-163
   CPUs online           = CPU0 only
   process               = parent + helper threads, same TGID
   mm/files              = shared
   scheduling            = both SCHED_NORMAL
   socketpair call       = socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,sv)
   socket fd             = 6 and 7, blocking, close-on-exec
   socket A / sock SA    = fd 6 receive endpoint
   socket B / sock SB    = fd 7 helper endpoint
   unix peer relation    = SA <-> SB
   protocol state        = both TCP_ESTABLISHED
   initial shutdown      = both 0
   eventpoll fd          = 8, close-on-exec
   registration          = level-triggered EPOLLIN|EPOLLRDHUP
   event data            = 0x554E4958
   callback              = P on socket A wait queue
   first helper call     = write(7,"hello",5)
   first parent read     = read(6,buf,5)
   second helper call    = shutdown(7,SHUT_WR)
   final parent read     = read(6,buf,5)
   failures/races        = none

完整控制流
----------

::

   parent socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, sv)
   → reserve fd 6 and fd 7 with close-on-exec bits
   → copy numeric fd values to user sv
   → create two PF_UNIX SOCK_STREAM sockets
   → unix_create1 initializes SA/UA and SB/UB
   → unix_socketpair takes peer references
   → unix_peer(SA)=SB and unix_peer(SB)=SA
   → SA/SB.sk_state=TCP_ESTABLISHED
   → allocate two sockfs files F6/F7
   → fd_install(6,F6), fd_install(7,F7)
   → return 0 with sv={6,7}

   parent epoll_create1(EPOLL_CLOEXEC) -> fd 8
   → eventpoll EP refcount starts at 1
   → epoll_ctl ADD fd 6 EPOLLIN|EPOLLRDHUP data 0x554E4958
   → allocate epitem I; EP refcount 1 -> 2
   → sock_poll_wait installs callback P on socket A wait queue
   → initial unix_poll sees empty queue, shutdown=0 and only writable readiness
   → interest filter returns 0
   → EP.rbr contains I, EP.rdllist empty

   parent epoll_wait(8,events,1,-1)
   → exclusive waiter W enters EP.wq
   → parent TASK_INTERRUPTIBLE and schedules out
   → helper runs on CPU0

   helper write(7,"hello",5)
   → sock_write_iter
   → unix_stream_sendmsg on socket B
   → unix_peer(SB) resolves SA directly
   → allocate one 5-byte skb and copy "hello"
   → lock SA receive queue
   → UA.inq_len 0 -> 5
   → queue skb on SA.sk_receive_queue
   → call SA.sk_data_ready
   → callback P links I to EP.rdllist and wakes parent
   → write returns 5
   → helper blocks outside socket objects

   parent resumes first epoll_wait
   → remove W from EP.wq
   → unix_poll sees non-empty SA receive queue
   → deliver {EPOLLIN,data=0x554E4958}
   → level-triggered I requeues
   → epoll_wait returns 1

   parent read(6,buf,5)
   → sock_read_iter
   → unix_stream_read_generic under UA.iolock
   → copy 5 bytes "hello"
   → UA.inq_len 5 -> 0
   → unlink and consume skb
   → SA receive queue becomes empty
   → read returns 5
   → I remains stale-ready

   parent epoll_wait(8,events2,1,-1)
   → re-poll stale I
   → empty queue and shutdown=0 produce no requested readiness
   → remove I from EP.rdllist
   → parent installs exclusive waiter W2 and sleeps

   helper shutdown(7,SHUT_WR)
   → generic shutdown resolves socket B
   → unix_shutdown maps SHUT_WR to SEND_SHUTDOWN
   → SB.sk_shutdown 0 -> SEND_SHUTDOWN
   → peer SA.sk_shutdown 0 -> RCV_SHUTDOWN
   → peer and local sk_state remain TCP_ESTABLISHED
   → SA.sk_state_change wakes socket A wait queue
   → callback P links I and wakes parent
   → shutdown returns 0

   parent resumes second epoll_wait
   → unix_poll sees SA RCV_SHUTDOWN
   → poll mask contains EPOLLIN|EPOLLRDNORM|EPOLLRDHUP
   → deliver {EPOLLIN|EPOLLRDHUP,data=0x554E4958}
   → persistent level-triggered I requeues
   → epoll_wait returns 1

   parent read(6,buf,5)
   → receive queue empty
   → RCV_SHUTDOWN detected before sleeping
   → return EOF 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：Unix stream socketpair data and half-close delivery complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* helper：blocked outside socket objects；
* ``socketpair`` result：0， ``sv={6,7}``；
* helper ``write(7)`` result：5；
* first ``epoll_wait`` result：1；
* first delivered event：``EPOLLIN``、data ``0x554E4958``；
* first ``read(6)`` result：5，bytes ``hello``；
* helper ``shutdown(7,SHUT_WR)`` result：0；
* second ``epoll_wait`` result：1；
* second delivered event：``EPOLLIN|EPOLLRDHUP``、data ``0x554E4958``；
* final syscall/result：``read(6)=0``；
* fd 6/7/8：open；
* socket files ``F6/F7``：active sockfs files；
* ``SA/SB.sk_state``：``TCP_ESTABLISHED``；
* ``SA.sk_shutdown``：``RCV_SHUTDOWN``；
* ``SB.sk_shutdown``：``SEND_SHUTDOWN``；
* ``unix_peer(SA)=SB``、 ``unix_peer(SB)=SA``；
* SA/SB receive queues：empty；
* ``UA.inq_len=0``、 ``UB.inq_len=0``；
* callback ``P``：active on socket A wait queue；
* epitem ``I``：active in ``EP.rbr`` and persistent-ready in ``EP.rdllist``；
* ``EP.refcount=2``；
* ``EP.wq``：empty；
* fd 6向fd 7发送方向：open；
* fd 7从fd 6接收方向：open；
* fd 7向fd 6发送方向：closed；
* filesystem/block/device I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. socketpair reserve fd、copy用户数字与安装file是三个不同阶段。
#. 两个Unix stream endpoints互相持有peer reference。
#. AF_UNIX stream使用skb和socket wait queue，但不进入IP或设备层。
#. socket file由sockfs承载，不是anon_inodefs。
#. 初始socket可写不会触发只监听IN/RDHUP的registration。
#. callback位于socket A wait queue，sleeping parent位于eventpoll wait queue。
#. sendmsg把数据复制到skb并排入peer receive queue。
#. ``UA.inq_len`` 在本批为0→5→0。
#. ``sk_data_ready`` 只建立candidate readiness，delivery仍需 ``unix_poll`` re-check。
#. Unix stream不保证write、skb和read之间的一一消息边界。
#. 第一次read清空queue不会主动删除epoll ready membership。
#. 第二次epoll_wait先清stale item，再真正睡眠等待shutdown。
#. ``SHUT_WR`` 本端设置SEND_SHUTDOWN、peer设置RCV_SHUTDOWN。
#. half-close不清除peer pointers，也不把状态改成TCP_CLOSE。
#. RCV_SHUTDOWN同时产生EPOLLIN与EPOLLRDHUP，便于read取得EOF。
#. 单向half-close不产生EPOLLHUP。
#. EOF来自空queue加RCV_SHUTDOWN，不是零长度skb。
#. RDHUP为persistent readiness，EOF read不会消费它。

下一任务
--------

优先接续Unix socketpair cleanup：

::

   epoll_ctl(8,EPOLL_CTL_DEL,6,NULL)
   → remove callback P and epitem I
   close(6)
   → release socket A and notify peer B of disconnect/full shutdown
   close(7)
   → release socket B and mutual peer references
   close(8)
   → release empty eventpoll

开始前固定close(6)触发的peer状态、wake mask、peer reference下降、sockfs inode/file teardown、skb queue清理与eventpoll RCU边界。
