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

最新三章：

#. ``LK-PIDFD-152``：pidfd_open() 怎样建立pidfs file并让epoll_wait监视child？
#. ``LK-PIDFD-153``：child _exit(42) 怎样通过pid->wait_pidfd唤醒epoll_wait？
#. ``LK-PIDFD-154``：waitid(P_PIDFD) 怎样读取退出状态并回收child？

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

已完成的运行期实验
------------------

#. cold-miss ``read(fd, buf, 4096)``；
#. ext4 ``O_SYNC write(fd, buf, 4096)``；
#. native x86-64 ``fork()``；
#. child private-anonymous COW write fault；
#. child static ELF ``execve()``；
#. child ``_exit(42)`` 与 parent ``wait4()`` 回收；
#. ext4 ``openat(O_CREAT|O_EXCL)``；
#. 新文件首次delalloc buffered write与显式 ``fsync``；
#. open-unlinked ext4文件的final close与inode/extent回收；
#. monotonic ``clock_nanosleep`` 自然到期；
#. ``SIGUSR1`` 中断nanosleep、signal frame与 ``rt_sigreturn``；
#. anonymous pipe blocking read与writer wakeup；
#. pipe write-end close、EOF与final teardown；
#. private futex wait/release-store/wake；
#. eventfd counter blocking read与writer wakeup；
#. eventfd final close与anon-inode file teardown；
#. eventfd通过level-triggered epoll callback唤醒 ``epoll_wait``；
#. eventfd readiness消费、stale-ready清理、registration删除与eventpoll final teardown；
#. blocked ``SIGUSR1`` 通过signalfd与epoll交付并读取 ``signalfd_siginfo``；
#. signalfd stale-ready清理、registration删除与signalfd/eventpoll final teardown；
#. one-shot monotonic timerfd通过local APIC、hrtimer与epoll交付expiration count；
#. timerfd stale-ready清理、registration删除与timerfd/eventpoll final teardown；
#. pidfd通过pidfs与epoll观察child退出，再由 ``waitid(P_PIDFD)`` 回收child。

本批固定场景
------------

::

   runtime relation    = independent scenario after LK-TIMERFDCLOSE-151
   CPUs online         = CPU0 only
   processes           = parent and one direct child, separate TGIDs
   process shape       = both single-threaded
   files tables        = separate after ordinary fork
   scheduling          = both SCHED_NORMAL
   initial executor    = parent
   child PID           = C in parent's active pid namespace
   child state         = TASK_RUNNING before parent blocks
   child exit signal   = SIGCHLD
   SIGCHLD disposition = default; no explicit SIG_IGN or SA_NOCLDWAIT
   pidfd call          = pidfd_open(C, 0)
   pidfd fd            = 6, O_RDWR, blocking, close-on-exec
   pid object          = P
   pidfs inode         = N, i_private=P
   epoll fd            = 7, close-on-exec
   registration        = level-triggered EPOLLIN epitem I
   event data          = 0x50494436
   callback entry      = CB on P->wait_pidfd
   parent wait         = epoll_wait(7, events, 1, -1)
   child action        = _exit(42)
   wait action         = waitid(P_PIDFD, 6, &si, WEXITED, NULL)
   concurrency         = no ptrace, concurrent wait, ctl, close or exec race
   failure policy      = no fd, pidfs, copy, slab, signal or scheduler failure

完整控制流
----------

::

   ordinary fork has already created child PID C
   → parent and child have separate files_struct objects
   → child is runnable but has not executed _exit yet

   parent pidfd_open(C, 0)
   → find_get_pid(C) resolves stable struct pid P
   → pidfd_prepare locks P->wait_pidfd.lock
   → verify PIDTYPE_PID and PIDTYPE_TGID task linkages
   → reserve close-on-exec fd 6
   → pidfs_alloc_file(P)
   → create/reuse stashed pidfs dentry and inode N
   → N.i_private=P and N holds a pid reference
   → create O_RDWR pidfd file F6
   → fd_install publishes fd 6
   → return 6

   parent epoll_create1(EPOLL_CLOEXEC)
   → allocate eventpoll EP and file F7
   → publish fd 7

   parent epoll_ctl(7, ADD, 6, {EPOLLIN,data=0x50494436})
   → allocate epitem I keyed by (F6, fd 6)
   → EP.refcount 1 -> 2
   → pidfd_poll installs callback CB on P->wait_pidfd
   → child exit_state=0, so initial poll mask is zero
   → EP.rbr contains I and EP.rdllist remains empty

   parent epoll_wait(7, events, 1, -1)
   → add exclusive task waiter W to EP.wq
   → parent becomes TASK_INTERRUPTIBLE and schedules out
   → scheduler selects child on CPU0

   child _exit(42)
   → do_exit(42 << 8)
   → release runtime resources
   → exit_notify under tasklist_lock
   → child exit_state 0 -> EXIT_ZOMBIE
   → do_notify_parent
   → do_notify_pidfd(child)
   → wake P->wait_pidfd with EPOLLIN|EPOLLRDNORM key
   → ep_poll_callback CB queues I on EP.rdllist
   → eventpoll wake changes parent TASK_INTERRUPTIBLE -> TASK_RUNNING
   → default SIGCHLD semantics leave child as zombie
   → child enters dead scheduling path
   → scheduler restores parent epoll_wait stack

   parent ep_send_events
   → pidfd_poll rechecks zombie child
   → report EPOLLIN|EPOLLRDNORM
   → copy events[0]={EPOLLIN,data=0x50494436}
   → level-triggered I returns to EP.rdllist
   → epoll_wait returns 1

   parent waitid(P_PIDFD, 6, &si, WEXITED, NULL)
   → pidfd_get_pid obtains P from pidfs inode and takes temporary pid ref
   → prepare wait_opts with PIDTYPE_PID and WEXITED
   → verify target is an effective child of current parent
   → wait_task_zombie cmpxchg EXIT_ZOMBIE -> EXIT_DEAD
   → collect status 42 << 8 and child accounting
   → fill CLD_EXITED, status 42, PID C and child UID
   → release_task(child)
   → pidfs_exit stores exit metadata in P->attr
   → remove child task and PID linkages
   → free_pid removes numeric PID C from namespace IDR
   → numeric PID C becomes reusable
   → open pidfs inode keeps old struct pid P alive
   → waitid copies siginfo and returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：pidfd exit notification and ``P_PIDFD`` reap complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* ``epoll_wait`` result：1；
* ``events[0].events``：``EPOLLIN``；
* ``events[0].data.u64``：``0x50494436``；
* ``waitid(P_PIDFD)`` result/RAX：0；
* ``si_signo``：``SIGCHLD``；
* ``si_code``：``CLD_EXITED``；
* ``si_pid``：旧数字PID ``C``；
* ``si_status``：42；
* child task：已从活动process图回收；
* child exit state最终转换：``EXIT_ZOMBIE -> EXIT_DEAD``；
* numeric PID ``C``：已从namespace IDR移除，可复用；
* parent fd 6：open pidfd file ``F6``，close-on-exec、blocking；
* pidfs inode ``N``：active， ``N->i_private=P``；
* old ``struct pid P``：active because pidfs inode/file still holds references；
* ``P`` task linkage：none；
* ``P->attr``：exit bit已设置，保存 ``42 << 8``；
* ``P->wait_pidfd``：仍包含callback ``CB``；
* parent fd 7：open eventpoll file ``F7``；
* eventpoll ``EP``：active， ``refcount=2``；
* ``EP.rbr``：包含epitem ``I``；
* ``EP.rdllist``：仍包含level-triggered ``I``；
* ``EP.wq``：empty；
* next pidfd poll mask：``EPOLLIN|EPOLLRDNORM|EPOLLHUP``；
* pidfd/eventpoll close：本批未执行；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. pidfd固定 ``struct pid`` identity，不固定可复用的数字PID值。
#. 当前pidfd由pidfs inode承载，不是singleton anonymous inode。
#. pidfs inode ``i_private`` 指向 ``struct pid`` 并持有pid reference。
#. 普通fork后parent与child的files table分离，child看不到稍后创建的fd 6/7。
#. ``pidfd_prepare`` 在 ``wait_pidfd.lock`` 下确认task linkages仍存在。
#. ``pidfd_poll`` 的target wait queue是 ``P->wait_pidfd``。
#. callback ``CB`` 与parent sleeping waiter ``W`` 位于两条不同wait queue。
#. child先进入 ``EXIT_ZOMBIE``，随后发送pidfd wake。
#. pidfd wake与SIGCHLD/``wait_chldexit`` 是不同通知通道。
#. epoll event只通知readiness，不消费退出状态或reap child。
#. ``waitid(P_PIDFD)`` 的upid参数是fd number，不是numeric PID。
#. 持有pidfd不会绕过自然parent/ptrace wait权限检查。
#. ``cmpxchg(EXIT_ZOMBIE, EXIT_DEAD)`` 让一个waiter独占reap。
#. ``waitid`` 成功返回0；child PID和status通过 ``siginfo_t`` 返回。
#. ``pidfs_exit`` 在task linkage移除前保存exit metadata。
#. child被reap后numeric PID可以复用，而旧pidfd仍指向旧 ``struct pid``。
#. task linkage消失后，pidfd poll增加 ``EPOLLHUP``。
#. level-triggeredepitem仍在ready list，下一次wait会继续交付post-reap readiness。
#. pidfs是内存pseudo filesystem，本场景没有磁盘I/O、journal或writeback。

下一任务
--------

当前pidfd在reap后仍为永久ready。优先接续：

::

   epoll_wait(7, events2, 1, 0)
   → pidfd_poll sees no task linkage
   → report EPOLLIN|EPOLLRDNORM|EPOLLHUP
   → copy one post-reap event and return 1

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → remove CB from P->wait_pidfd
   → erase epitem I and drop EP.refcount 2 -> 1

   close(6)
   → release pidfs file/path/inode
   → pidfs_evict_inode put_pid(P)
   → old struct pid and pidfs attr may reach final release

   close(7)
   → drain empty eventpoll and end EP lifetime

开始前必须核对pidfs dentry stash/prune、inode eviction、pid references、attr free时点、post-reap poll mask与eventpoll teardown顺序。
