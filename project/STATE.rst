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

最新三章：

#. ``LK-TIMERFDCLOSE-149``：零超时epoll_wait() 怎样清理timerfd的stale-ready item？
#. ``LK-TIMERFDCLOSE-150``：EPOLL_CTL_DEL 怎样拆除timerfd callback与epitem？
#. ``LK-TIMERFDCLOSE-151``：close() 怎样释放timerfd与eventpoll并结束两套RCU生命周期？

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
#. timerfd stale-ready清理、registration删除与timerfd/eventpoll final teardown。

本批固定场景
------------

::

   runtime relation    = continuation of LK-TIMERFD-146..148
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   scheduling          = both SCHED_NORMAL
   current executor    = parent
   timerfd fd          = 6, blocking, close-on-exec
   timerfd file        = F6
   timerfd ctx         = T
   timer clock         = CLOCK_MONOTONIC
   timer interval      = 0, one-shot
   embedded hrtimer    = inactive and not queued
   timer state         = T.ticks=0, T.expired=0, T.tintv=0
   epoll fd            = 7, close-on-exec
   eventpoll file      = F7
   eventpoll object    = EP
   registration        = one level-triggered EPOLLIN epitem I
   event data          = 0x71FD6
   callback entry      = P on T.wqh
   entry ready state   = I initially stale-ready on EP.rdllist
   stale check         = epoll_wait(7, events2, 1, 0)
   delete call         = epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   final closes        = close(6), then close(7)
   concurrency         = no expiration/callback/ctl/wait/close race
   failure policy      = no fd/copy/VFS/slab/timer/scheduler failure

完整控制流
----------

::

   parent epoll_wait(7, events2, 1, 0)
   → zero timeout sets timed_out=1
   → stale I makes initial ready check true
   → ep_send_events locks EP.mtx
   → ep_start_scan moves I into local scan batch
   → ep_deliver_event removes I from scan batch
   → ep_item_poll calls timerfd_poll with no queue callback
   → timerfd_poll locks T.wqh and sees T.ticks=0
   → no EPOLLIN returned
   → no event copied and I is not level-triggered requeued
   → EP.rdllist remains empty
   → epoll_wait returns 0 without sleeping

   parent epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → resolve F7 and F6 with temporary file references
   → lock EP.mtx and find I by key (F6, fd 6)
   → ep_unregister_pollwait removes P from T.wqh
   → T.wqh lock synchronizes callback removal with wake path
   → free P synchronously
   → epi_fget pins F6 against final __fput
   → under F6.f_lock publish F6.f_ep=NULL for last watcher
   → remove reverse hlist link
   → erase I from EP.rbr
   → I already absent from EP.rdllist
   → kfree_rcu(I)
   → EP.refcount 2 -> 1
   → epoll_ctl returns 0

   parent close(6)
   → remove shared fd 6 publication and close-on-exec bit
   → filp_flush returns 0
   → fput_close_sync enters final __fput(F6)
   → eventpoll_release sees F6.f_ep=NULL and uses fast path
   → timerfd_release
   → timerfd_remove_cancel sees might_cancel=false
   → hrtimer_cancel sees inactive one-shot timer and returns 0
   → kfree_rcu(T)
   → release [timerfd] pseudo dentry and per-file mount ref
   → file_free(F6)
   → close(6) returns 0

   parent close(7)
   → remove shared fd 7 publication and close-on-exec bit
   → filp_flush returns 0
   → fput_close_sync enters final __fput(F7)
   → ep_eventpoll_release / ep_clear_and_put
   → eventpoll wait queues are empty
   → lock EP.mtx
   → empty pollwait drain pass
   → empty rbtree drain pass
   → unlock EP.mtx
   → EP.refcount 1 -> 0
   → ep_free destroys mutex/user/wakeup-source state
   → kfree_rcu(EP)
   → release [eventpoll] pseudo dentry and per-file mount ref
   → file_free(F7)
   → close(7) returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：timerfd + eventpoll lifecycle complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* last syscall：``close(7)``；
* last result/RAX：0；
* zero-time ``epoll_wait`` result：0；
* ``EPOLL_CTL_DEL`` result：0；
* ``close(6)`` result：0；
* shared fd 6：closed and unallocated；
* shared fd 7：closed and unallocated；
* timerfd file ``F6``：freed；
* timerfd ctx ``T``：logical lifetime ended；
* ``T`` storage：queued/freed through ``kfree_rcu`` grace period；
* embedded hrtimer：inactive before ctx teardown；
* callback ``P``：freed synchronously during DEL；
* epitem ``I``：logical lifetime ended；
* ``I`` storage：queued/freed through ``kfree_rcu`` grace period；
* eventpoll file ``F7``：freed；
* eventpoll ``EP``：logical lifetime ended；
* ``EP`` storage：queued/freed through ``kfree_rcu`` grace period；
* ``[timerfd]`` / ``[eventpoll]`` per-file pseudo paths：released；
* singleton ``anon_inode_inode``：active；
* global ``anon_inode_mnt``：mounted；
* helper：阻塞在旧timerfd/eventpoll之外；
* parent/helper blocked mask：仍包含之前实验留下的 ``SIGUSR1``；
* private/shared pending ``SIGUSR1``：none；
* shared ``files_struct``：active，fd 0..5保持原状；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. zero-time epoll会重新验证ready candidate，但不会等待未来event。
#. ready-list membership不等于目标当前仍ready。
#. re-poll返回0只删除ready membership，不删除registration。
#. ``EPOLL_CTL_DEL`` 使用 ``(file, fd)`` key；event参数可以为NULL。
#. callback entry必须先从target wait queue移除，再释放epitem。
#. waitqueue lock串行化timerfd wake callback与callback removal。
#. ``P`` 同步释放； ``I`` 使用 ``kfree_rcu`` 延迟回收storage。
#. 最后watcher删除时 ``F6->f_ep=NULL``。
#. epitem持有一个eventpoll reference；DEL使 ``EP->refcount`` 从2降到1。
#. CLOCK_MONOTONIC relative timerfd不进入cancel-on-set list。
#. 已到期one-shot hrtimer为inactive，release中的 ``hrtimer_cancel`` 返回0。
#. timerfd ctx通过 ``kfree_rcu`` 结束storage生命周期。
#. eventpoll close在空tree上仍执行pollwait-first、tree-second两遍drain。
#. ``EP->refcount`` 从1归零后由 ``ep_free`` 结束逻辑生命周期。
#. ``I``、 ``T``、 ``EP`` 的RCU callback彼此独立。
#. per-file pseudo path结束，全局anon_inodefs继续存在。
#. 整个场景没有磁盘I/O、journal或writeback。

下一任务
--------

当前没有已选定场景。优先候选是pidfd与epoll组合：

::

   fork/clone child
   → pidfd_open(child_pid, 0) publishes fd 6
   → epoll_create1(EPOLL_CLOEXEC) publishes fd 7
   → epoll_ctl ADD pidfd EPOLLIN
   → parent blocks in epoll_wait
   → child exits and becomes waitable
   → pidfd poll callback queues epitem and wakes parent
   → epoll_wait returns one event
   → waitid(P_PIDFD, fd 6, ...) consumes exit status

开始前必须固定clone flags、child exit status、pidfd type、wait semantics、zombie/reap时点、poll mask、callback和scheduler顺序。
