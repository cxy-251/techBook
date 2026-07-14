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

最新三章：

#. ``LK-INOTIFYCLOSE-161``：零超时epoll_wait怎样清除inotify的stale-ready item？
#. ``LK-INOTIFYCLOSE-162``：inotify_rm_watch怎样先排入IN_IGNORED再销毁mark？
#. ``LK-INOTIFYCLOSE-163``：读取IN_IGNORED后，close怎样释放inotify group与eventpoll？

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

   runtime relation    = continuation of LK-INOTIFY-158..160
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   mm/files            = shared
   scheduling          = both SCHED_NORMAL
   current executor    = parent
   inotify fd          = 6, O_RDONLY, blocking, close-on-exec
   inotify file        = F6
   fsnotify group      = G
   watch descriptor    = 1
   directory mark      = M on /work inode
   initial queue       = empty
   initial ready state = level-triggered epitem I stale-ready
   epoll fd            = 7, close-on-exec
   eventpoll           = EP, refcount=2 initially
   registration        = EPOLLIN, data=0x494E4F36
   callback            = P on G.notification_waitq
   helper              = blocked outside inotify objects
   watched file        = /work/new.txt remains present
   calls               = epoll_wait(...,0), rm_watch, epoll_wait, read, DEL, close(6), close(7)
   failures/races      = none

完整控制流
----------

::

   parent epoll_wait(7,events2,1,0)
   → scan stale-ready I
   → inotify_poll under G.notification_lock sees q_len=0
   → return poll mask 0
   → do not requeue I
   → EP.rdllist becomes empty
   → epoll_wait returns 0

   parent inotify_rm_watch(6,1)
   → find M in G.inotify_data.idr and take temporary mark ref
   → fsnotify_destroy_mark
   → clear M ATTACHED and remove from G.marks_list
   → fsnotify_free_mark clears ALIVE
   → inotify_ignored_and_remove_idr
   → queue wd1 FS_IN_IGNORED record before wd invalidation
   → G.q_len 0 -> 1
   → wake G.notification_waitq
   → callback P links I to EP.rdllist
   → remove idr[1], set M.wd=-1 and decrement watch ucount
   → drop final active mark refs
   → remove M from /work inode connector
   → clear /work fsnotify mask and release watch inode pin
   → queue M and connector storage for SRCU-safe destruction
   → inotify_rm_watch returns 0

   parent epoll_wait(7,events3,1,0)
   → re-poll q_len=1
   → copy {EPOLLIN,data=0x494E4F36}
   → level-triggered I requeues
   → return 1

   parent read(6,buf,4096)
   → remove one IN_IGNORED event
   → copy 16-byte record {wd=1,mask=IN_IGNORED,cookie=0,len=0}
   → G.q_len 1 -> 0
   → destroy event allocation
   → return 16

   parent epoll_ctl(7,EPOLL_CTL_DEL,6,NULL)
   → remove callback P from G.notification_waitq
   → free P synchronously
   → erase I from EP.rbr and EP.rdllist
   → EP.refcount 2 -> 1
   → kfree_rcu(I)
   → return 0

   parent close(6)
   → remove fd 6 and close-on-exec bit
   → final synchronous __fput(F6)
   → inotify_release
   → fsnotify_destroy_group(G)
   → set G.shutdown=true
   → no active mark remains in G.marks_list
   → wait G.user_waits=0
   → flush mark reaper work
   → synchronize fsnotify_mark_srcu
   → free mark M and drop its group reference
   → flush empty notification queue
   → free overflow event
   → destroy empty watch IDR and decrement instance ucount
   → free G and inotify anon-inode file/path
   → close(6) returns 0

   parent close(7)
   → remove fd 7 and close-on-exec bit
   → empty eventpoll teardown
   → EP.refcount 1 -> 0
   → kfree_rcu(EP)
   → free eventpoll file/path
   → close(7) returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：inotify watch removal and final teardown complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* helper：blocked outside inotify objects；
* stale-ready cleanup ``epoll_wait`` result：0；
* ``inotify_rm_watch(6,1)`` result：0；
* ``IN_IGNORED`` delivery ``epoll_wait`` result：1；
* delivered event：``EPOLLIN``、data ``0x494E4F36``；
* ``read(6)`` result：16；
* copied record：wd1、``IN_IGNORED``、cookie0、len0；
* ``EPOLL_CTL_DEL`` result：0；
* ``close(6)`` result：0；
* final syscall/result：``close(7) = 0``；
* fd 6/7：closed and unallocated；
* wd 1：invalid and absent from IDR；
* mark ``M``：freed before close(6) returns；
* ``/work`` fsnotify connector：detached；storage freed or pending independent connector reaper；
* fsnotify group ``G``：freed；
* notification queue：destroyed after empty flush；
* overflow event：freed；
* inotify file ``F6``：freed；
* callback ``P``：freed synchronously；
* epitem ``I``：logical lifetime ended，storage through RCU；
* eventpoll ``EP``：logical lifetime ended，storage through RCU；
* eventpoll file ``F7``：freed；
* global anon_inodefs：active；
* ``/work/new.txt``：exists；
* filesystem/block I/O caused by cleanup：none；
* next runtime scenario：unselected。

关键边界
--------

#. eventpoll ready membership与inotify queue readiness必须通过re-poll重新核对。
#. empty queue使zero-time ``epoll_wait`` 返回0并清除stale-ready membership。
#. rm_watch用临时mark reference稳定对象，再执行detach。
#. mark先退出group list，再通过backend callback生成 ``IN_IGNORED``。
#. ``IN_IGNORED`` 在IDR removal前入队，因此record保存原wd 1。
#. 已排队event的wd快照不受随后 ``M.wd=-1`` 影响。
#. callback在parent未睡眠时只建立ready membership，不发生task wakeup。
#. IDR、group list、syscall临时ref和inode connector是不同mark lifetime边界。
#. mark最后reference下降后才退出inode connector。
#. watch removal归还fsnotify对目录inode的pin，不删除目录或文件。
#. mark和connector storage需要SRCU安全期；rm_watch不等待物理free。
#. group close通过 ``fsnotify_wait_marks_destroyed`` 等待mark reaper完成。
#. connector由独立worker释放，close返回不要求其storage已经kfree。
#. no-name ``IN_IGNORED`` record为16字节。
#. DEL同步free callback，epitem通过RCU延迟free。
#. inotify group final free销毁空IDR、overflow event与instance accounting。
#. anon_inodefs是全局对象，不因fd 6/7关闭而卸载。
#. cleanup不删除 ``/work/new.txt``，也不产生额外磁盘I/O。

下一任务
--------

当前没有已选定场景。优先候选是Unix domain stream socket与epoll：

::

   socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, sv)
   → fd 6/7 form one connected unix socket pair
   epoll_create1(EPOLL_CLOEXEC) → fd 8
   epoll_ctl(8, ADD, 6, EPOLLIN|EPOLLRDHUP)
   → parent blocks in epoll_wait
   → helper write(7, "hello", 5)
   → unix receive queue wakes parent
   → parent epoll_wait returns and read(6) consumes 5 bytes
   → helper shutdown(7, SHUT_WR)
   → parent observes EPOLLRDHUP and read EOF

开始前必须固定socket state、sk_receive_queue、socket wait queue、memory accounting、shutdown flags、callback顺序与scheduler顺序。
