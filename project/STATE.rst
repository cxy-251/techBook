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

最新三章：

#. ``LK-PIDFDCLOSE-155``：reap之后的pidfd为什么让epoll_wait返回EPOLLIN|EPOLLHUP？
#. ``LK-PIDFDCLOSE-156``：EPOLL_CTL_DEL怎样拆除pidfd callback与epitem？
#. ``LK-PIDFDCLOSE-157``：close()怎样释放pidfs inode、旧struct pid与eventpoll？

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

   runtime relation = continuation of LK-PIDFD-152..154
   CPU               = CPU0 only
   executor          = parent
   child task        = already reaped
   numeric PID C     = reusable but not reused in this batch
   pidfd fd          = 6, O_RDWR, blocking, close-on-exec
   pidfd file        = F6
   pidfs dentry      = D
   pidfs inode       = N, N->i_private=P
   old struct pid    = P, no task linkage
   exit metadata     = P->attr contains 42 << 8
   eventpoll fd      = 7
   eventpoll         = EP, refcount=2 initially
   registration      = level-triggered EPOLLIN epitem I
   callback          = CB on P->wait_pidfd
   ready state       = I initially on EP.rdllist
   calls             = epoll_wait(...,0), DEL, close(6), close(7)
   failures/races    = none

完整控制流
----------

::

   epoll_wait(7, events2, 1, 0)
   → existing I enters scan
   → pidfd_poll sees pid_task(P, PIDTYPE_PID) == NULL
   → returns EPOLLIN|EPOLLRDNORM|EPOLLHUP
   → interest filtering leaves EPOLLIN|EPOLLHUP
   → copy event data 0x50494436
   → level-triggered I returns to EP.rdllist
   → epoll_wait returns 1

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → lock EP.mtx and find I
   → remove CB from P->wait_pidfd
   → free CB synchronously
   → set F6->f_ep=NULL for last watcher
   → erase I from EP.rbr and EP.rdllist
   → kfree_rcu(I)
   → EP.refcount 2 -> 1
   → return 0

   close(6)
   → remove fd 6 and cloexec bit
   → synchronous final __fput(F6)
   → eventpoll release uses F6->f_ep=NULL fast path
   → pidfs_file_release returns 0; no PIDFD_AUTOKILL
   → dput D and stashed_dentry_prune clears P->stashed
   → pidfs_evict_inode(N) calls put_pid(P)
   → combine with free_pid's delayed_put_pid RCU drop
   → pidfs_free_pid frees exit metadata and old P
   → release pidfs path/file
   → close(6) returns 0

   close(7)
   → remove fd 7 and cloexec bit
   → empty ep_clear_and_put
   → EP.refcount 1 -> 0
   → ep_free / kfree_rcu(EP)
   → release eventpoll pseudo path/file
   → close(7) returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU mode：x86-64 CPL 3 on CPU0；
* parent：``TASK_RUNNING``， ``on_rq=1``、 ``on_cpu=1``；
* last syscall/result：``close(7) = 0``；
* post-reap ``epoll_wait`` result：1；
* delivered event：``EPOLLIN|EPOLLHUP``，data ``0x50494436``；
* ``EPOLL_CTL_DEL`` result：0；
* ``close(6)`` result：0；
* fd 6/7：closed and unallocated；
* child task：不存在；
* numeric PID ``C``：可复用，本批未重新分配；
* pidfd file与pidfs ``D/N``：freed；
* old ``struct pid P``：logical lifetime ended；
* ``P->attr`` exit metadata：freed；
* callback ``CB``：freed synchronously；
* epitem ``I``：logical lifetime ended，storage经RCU回收；
* eventpoll ``EP``：logical lifetime ended，storage经RCU回收；
* global ``pidfs_mnt``：mounted；
* global anon_inodefs：active；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. post-reap pidfd永久返回 ``EPOLLIN|EPOLLRDNORM|EPOLLHUP``。
#. ``EPOLLHUP`` 即使未由用户显式请求也会被epoll报告。
#. level-triggered永久ready item会在每次交付后重新入ready list。
#. DEL先拆callback，再移除file reverse link与epitem。
#. callback同步释放，epitem通过RCU延迟释放。
#. pidfd close不会在未设置 ``PIDFD_AUTOKILL`` 时发送SIGKILL。
#. pid identity reference由pidfs inode持有，在inode eviction中归还。
#. stashed dentry必须在 ``struct pid`` final free前清零。
#. 数字PID可复用与旧 ``struct pid`` storage是否仍存活是两件事。
#. inode put与 ``delayed_put_pid`` 的先后可交换，refcount保证只释放一次。
#. pidfs全局mount不会因最后一个pidfd关闭而卸载。
#. close返回不要求RCU callback已经执行，但对象已不可由用户访问。

下一任务
--------

优先候选是inotify与epoll组合：

::

   inotify_init1(IN_CLOEXEC) -> fd 6
   inotify_add_watch(fd 6, /work, IN_CREATE|IN_CLOSE_WRITE)
   epoll_create1(EPOLL_CLOEXEC) -> fd 7
   epoll_ctl ADD inotify fd EPOLLIN
   → parent blocks in epoll_wait
   → helper creates and closes /work/new.txt
   → fsnotify queues inotify events
   → callback wakes parent
   → epoll_wait returns and read(6) copies inotify_event records

开始前固定watch mask、文件操作、event合并规则、name长度、queue状态与scheduler顺序。
