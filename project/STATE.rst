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

最新三章：

#. ``LK-SIGNALFDCLOSE-143``：零超时epoll_wait() 怎样清理signalfd的stale-ready item？
#. ``LK-SIGNALFDCLOSE-144``：EPOLL_CTL_DEL 怎样拆除signalfd callback与epitem？
#. ``LK-SIGNALFDCLOSE-145``：close() 怎样释放signalfd与eventpoll，却保留共享sighand wait queue？

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
#. signalfd stale-ready清理、registration删除与signalfd/eventpoll final teardown。

本批固定场景
------------

::

   runtime relation    = continuation of LK-SIGNALFD-140..142
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   signal structures   = shared signal_struct and sighand_struct
   scheduling          = both SCHED_NORMAL
   current executor    = parent
   blocked masks       = parent/helper both contain SIGUSR1
   pending state       = no private/shared SIGUSR1
   signalfd fd         = 6, blocking, close-on-exec
   signalfd file       = F6
   signalfd ctx        = S
   epoll fd            = 7, close-on-exec
   eventpoll file      = F7
   eventpoll object    = EP
   registration        = one level-triggered EPOLLIN epitem I
   event data          = 0x51FD6
   callback entry      = P on shared sighand->signalfd_wqh
   entry ready state   = I initially stale-ready on EP.rdllist
   stale check         = epoll_wait(7, events2, 1, 0)
   delete call         = epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   final closes        = close(6), then close(7)
   concurrency         = no signal, callback, ctl, wait or close race
   failure policy      = no fd, copy, VFS, slab, signal or scheduler failure

完整控制流
----------

::

   parent epoll_wait(7, events2, 1, 0)
   → zero timeout sets timed_out=1
   → initial ready check sees stale I on EP.rdllist
   → ep_send_events locks EP.mtx
   → ep_start_scan moves I to local scan batch
   → ep_deliver_event removes I from scan batch
   → ep_item_poll temporarily pins F6
   → signalfd_poll uses shared sighand siglock
   → parent private pending has no SIGUSR1
   → shared pending has no SIGUSR1
   → signalfd reports no EPOLLIN
   → no event copied and I is not requeued
   → EP.rdllist remains empty
   → epoll_wait returns 0 without sleeping

   parent epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → resolve F7 and F6 with temporary references
   → lock EP.mtx and find I in EP.rbr
   → ep_unregister_pollwait removes P from shared signalfd_wqh
   → waitqueue lock synchronizes with possible callback execution
   → free P synchronously
   → epi_fget temporarily pins F6
   → under F6.f_lock set F6.f_ep=NULL and remove reverse link
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
   → signalfd_release kfree(S)
   → release [signalfd] pseudo dentry and per-file mount ref
   → file_free(F6)
   → close(6) returns 0
   → shared sighand->signalfd_wqh remains active and empty

   parent close(7)
   → remove shared fd 7 publication and close-on-exec bit
   → fput_close_sync enters final __fput(F7)
   → ep_eventpoll_release / ep_clear_and_put
   → EP.poll_wait empty
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
* runtime scenario：signalfd + eventpoll lifecycle complete；
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
* signalfd file ``F6``：freed；
* signalfd ctx ``S``：freed synchronously；
* callback ``P``：freed synchronously during DEL；
* epitem ``I``：logical lifetime ended；
* ``I`` storage：queued/freed through ``kfree_rcu`` grace period；
* eventpoll file ``F7``：freed；
* eventpoll ``EP``：logical lifetime ended；
* ``EP`` storage：queued/freed through ``kfree_rcu`` grace period；
* shared ``sighand_struct``：active；
* shared ``sighand->signalfd_wqh``：active、empty；
* parent/helper blocked mask：仍包含 ``SIGUSR1``；
* parent private pending：无 ``SIGUSR1``；
* shared pending：无 ``SIGUSR1``；
* singleton ``anon_inode_inode``：active；
* global ``anon_inode_mnt``：mounted；
* helper：阻塞在旧signalfd/eventpoll之外；
* shared ``files_struct``：active，fd 0..5保持原状；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. zero-time epoll仍会重新验证已经在ready list中的candidate。
#. ready-list membership不是永久readiness事实。
#. re-poll没有匹配event时，只移除ready membership，不删除registration。
#. ``EPOLL_CTL_DEL`` 使用 ``(file, fd)`` key，不读取用户event对象。
#. callback entry必须先从共享wait queue移除，再释放epitem。
#. waitqueue lock把callback执行与callback removal串行化。
#. ``P`` 同步释放； ``I`` 使用 ``kfree_rcu`` 延迟回收storage。
#. 最后watcher删除时 ``F6->f_ep`` 被设为NULL。
#. epitem持有一个eventpoll reference；DEL使 ``EP->refcount`` 从2降为1。
#. signalfd ctx与shared sighand wait queue属于不同对象。
#. ``signalfd_release`` 只释放private ctx，不销毁 ``signalfd_wqh``。
#. ``signalfd_cleanup/wake_up_pollfree`` 属于sighand teardown，不属于file close。
#. eventpoll close在空tree上仍执行pollwait-first、tree-second两遍drain。
#. ``EP->refcount`` 从1归零后， ``ep_free`` 结束EP逻辑生命周期。
#. 关闭signalfd不会解除 ``SIGUSR1`` block或恢复旧signal mask。
#. per-filepseudo path结束，全局anon_inodefs继续存在。
#. 整个场景没有磁盘filesystem、journal或block I/O。

下一任务
--------

当前没有已选定场景。优先候选是 ``timerfd_create`` 与epoll组合：

::

   timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC) -> fd 6
   timerfd_settime(one-shot relative 20ms)
   epoll_create1(EPOLL_CLOEXEC) -> fd 7
   epoll_ctl ADD timerfd EPOLLIN
   parent epoll_wait blocks
   → local APIC timer interrupt
   → hrtimer callback increments expirations
   → timerfd poll callback queues epitem and wakes parent
   → epoll_wait returns EPOLLIN
   → read(fd 6, &expirations, 8) returns one expiration

开始前必须固定absolute/relative mode、clockid、cancel-on-set、interval、hrtimer base、expiration count、callback与scheduler顺序。
