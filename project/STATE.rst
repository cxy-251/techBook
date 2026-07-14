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

最新三章：

#. ``LK-INOTIFY-158``：inotify怎样建立目录watch并让parent阻塞在epoll_wait？
#. ``LK-INOTIFY-159``：helper创建并关闭new.txt时，fsnotify怎样排入两条inotify事件？
#. ``LK-INOTIFY-160``：parent怎样从epoll event读取两条inotify_event记录？

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

   runtime relation    = independent scenario after LK-PIDFDCLOSE-157
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   mm/files            = shared
   scheduling          = both SCHED_NORMAL
   watched path        = existing ext4 directory /work
   inotify call        = inotify_init1(IN_CLOEXEC)
   inotify fd          = 6, O_RDONLY, blocking, close-on-exec
   fsnotify group      = G, max_events=16384
   watch call          = inotify_add_watch(6,/work,IN_CREATE|IN_CLOSE_WRITE)
   watch descriptor    = 1
   directory mark      = M on /work inode D
   internal mark mask  = FS_CREATE|FS_CLOSE_WRITE|FS_UNMOUNT|FS_EVENT_ON_CHILD
   epoll fd            = 7, close-on-exec
   registration        = level-triggered EPOLLIN epitem I
   event data          = 0x494E4F36
   callback            = P on G.notification_waitq
   parent wait         = epoll_wait(7,events,1,-1)
   helper file call    = openat(/work/new.txt,O_CREAT|O_WRONLY|O_TRUNC,0644)
   helper fd           = 8
   helper write        = write(8,"data",4)
   helper close        = close(8)
   read call           = read(6,buf,4096)
   event failures      = no allocation, queue overflow, copy or scheduler failure
   concurrency         = no other event producer, reader, watch update, ctl or close race

完整控制流
----------

::

   parent inotify_init1(IN_CLOEXEC)
   → allocate fsnotify group G
   → init empty notification list and notification_waitq
   → preallocate unqueued overflow event
   → init watch IDR and user-instance accounting
   → create anon-inode inotify file F6
   → publish blocking close-on-exec fd 6

   parent inotify_add_watch(6,/work,IN_CREATE|IN_CLOSE_WRITE)
   → resolve /work ext4 directory inode D
   → check MAY_READ and security_path_notify
   → allocate inotify_inode_mark M
   → derive mask FS_CREATE|FS_CLOSE_WRITE|FS_UNMOUNT|FS_EVENT_ON_CHILD
   → idr_alloc_cyclic from 1 assigns wd 1
   → connect M to G and D
   → update directory child-watch state
   → return wd 1

   parent epoll_create1(EPOLL_CLOEXEC) -> fd 7
   → eventpoll EP refcount starts at 1
   → epoll_ctl ADD fd 6 EPOLLIN data 0x494E4F36
   → allocate epitem I and raise EP refcount 1 -> 2
   → inotify_poll installs callback P on G.notification_waitq
   → queue empty, initial poll mask zero
   → EP.rbr contains I, EP.rdllist empty

   parent epoll_wait(7,events,1,-1)
   → stack waiter W enters EP.wq exclusively
   → parent TASK_INTERRUPTIBLE and schedules out
   → helper runs on CPU0

   helper openat creates /work/new.txt as fd 8
   → successful namespace create reaches fsnotify_create
   → inotify backend allocates wd1 FS_CREATE name new.txt cookie0 event
   → queue q_len 0 -> 1
   → wake G.notification_waitq
   → callback P links I to EP.rdllist
   → wake EP.wq and parent becomes TASK_RUNNING

   helper write(8,"data",4)
   → FS_MODIFY hook does not match M, so no user event

   helper close(8)
   → final __fput invokes fsnotify_close
   → write-mode F8 selects FS_CLOSE_WRITE
   → fsnotify_parent supplies D and name new.txt
   → inotify backend allocates wd1 close-write event
   → mask differs from queue tail create event, so no merge
   → queue q_len 1 -> 2
   → second wake does not duplicate already-linked I
   → close returns 0 and helper blocks outside objects

   parent resumes epoll_wait
   → remove W from EP.wq
   → re-poll inotify queue under G.notification_lock
   → q_len=2 reports EPOLLIN|EPOLLRDNORM
   → copy events[0]={EPOLLIN,data=0x494E4F36}
   → level-triggered I returns to EP.rdllist
   → epoll_wait returns 1

   parent read(6,buf,4096)
   → temporarily add read waiter R to G.notification_waitq
   → remove CREATE from FIFO, q_len 2 -> 1
   → copy 16-byte header + 16-byte padded new.txt name area
   → destroy CREATE allocation
   → remove CLOSE_WRITE from FIFO, q_len 1 -> 0
   → copy second 32-byte record and destroy allocation
   → queue empty after copied data, so do not block
   → remove R and return 64

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：inotify directory create/close-write delivery complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* helper：阻塞在inotify之外；
* ``epoll_wait`` result：1；
* ``events[0].events``：``EPOLLIN``；
* ``events[0].data.u64``：``0x494E4F36``；
* ``read(6)`` result：64；
* first record：wd1、``IN_CREATE``、cookie0、len16、name ``new.txt``；
* second record：wd1、``IN_CLOSE_WRITE``、cookie0、len16、name ``new.txt``；
* fd 6：open blocking inotify file ``F6``；
* group ``G``：active， ``q_len=0``，notification list empty；
* overflow event：allocated but not queued；
* watch wd1 / mark ``M``：active on ``/work`` inode ``D``；
* ``G.notification_waitq``：只包含epoll callback ``P``；
* fd 7：open eventpoll file ``F7``；
* ``EP.refcount``：2；
* ``EP.rbr``：包含 ``I``；
* ``EP.rdllist``：包含stale-ready ``I``；
* ``EP.wq``：empty；
* ``/work/new.txt``：存在；
* fd 8：closed；
* ``IN_CLOSE_WRITE`` durability guarantee：none；
* next runtime scenario：unselected。

关键边界
--------

#. inotify fd持有fsnotify group，不是watched directory file。
#. directory mark自动加入 ``FS_EVENT_ON_CHILD`` 和 ``FS_UNMOUNT``。
#. 新group的首个watch descriptor由IDR从1开始分配。
#. epoll callback与parent task waiter位于两条不同wait queue。
#. CREATE在目录项成功建立后排队。
#. WRITE产生的MODIFY hook因未订阅而不会形成用户record。
#. CLOSE_WRITE由file write mode选择，不表示数据durable。
#. create与close-write mask不同，inotify队尾merge不会合并它们。
#. 两条notification records只对应一个fd-level epitem readiness。
#. 每条 ``new.txt`` record是16字节头加16字节padded name，共32字节。
#. 内部 ``FS_EVENT_ON_CHILD`` 不输出到用户mask。
#. blocking inotify read在已复制event后看到empty queue会立即返回。
#. read清空queue不会主动清除eventpoll ready membership。
#. 读取event不删除watch。

下一任务
--------

优先接续显式watch销毁与cleanup：

::

   epoll_wait(7,events2,1,0)
   → re-poll empty queue
   → remove stale-ready I and return 0
   → inotify_rm_watch(6,1)
   → destroy mark and queue IN_IGNORED
   → callback places I back on ready list
   → epoll_wait delivers IN_IGNORED readiness
   → read(6) consumes 16-byte no-name IN_IGNORED record
   → EPOLL_CTL_DEL and close fd 6/7

开始前必须固定mark destroy worker、 ``IN_IGNORED`` queue时序、watch ucount、IDR removal与group final teardown顺序。
