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

最新三章：

#. ``LK-EPOLLCLOSE-137``：eventfd read() 怎样清零counter却暂时留下ready epitem？
#. ``LK-EPOLLCLOSE-138``：零超时epoll_wait() 怎样重新poll并清理stale-ready item？
#. ``LK-EPOLLCLOSE-139``：EPOLL_CTL_DEL与close()怎样拆除callback并释放eventfd/eventpoll？

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
#. eventfd readiness消费、stale-ready清理、registration删除与eventpoll final teardown。

本批固定场景
------------

::

   runtime relation    = continuation of LK-EPOLL-134..136
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   scheduling          = both SCHED_NORMAL
   current executor    = parent
   eventfd fd          = 6
   epoll fd            = 7
   eventfd count       = 5 at entry
   eventfd mode        = blocking, non-semaphore
   registration        = one level-triggered EPOLLIN epitem I
   stored mask         = EPOLLIN | EPOLLERR | EPOLLHUP
   event data          = 0xEFD6
   callback entry      = P, non-exclusive, attached to E.wqh
   ready state         = I initially on EP.rdllist
   parent read         = read(6, &value, 8)
   stale check         = epoll_wait(7, events2, 1, 0)
   delete call         = epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   final closes        = close(6), then close(7)
   concurrency         = no writer, waiter, ctl or close race
   failure policy      = no fd, copy, signal, VFS, slab or scheduler failure

完整控制流
----------

::

   parent read(6, &value, 8)
   → eventfd_read locks E.wqh.lock with IRQ disabled
   → count is 5, so no wait path
   → non-semaphore eventfd_ctx_do_read returns full value 5
   → E.count 5 -> 0
   → wake_up_locked_poll(E.wqh, EPOLLOUT)
   → callback P invokes ep_poll_callback
   → EPOLLOUT does not match I interest
   → no ready-list mutation and no task wake
   → P remains attached to E.wqh
   → copy value 5 to userspace
   → read returns 8

   parent epoll_wait(7, events2, 1, 0)
   → zero timeout sets timed_out=1
   → initial ep_events_available is true because I is still queued
   → ep_send_events locks EP.mtx
   → ep_start_scan moves I from EP.rdllist to local scan batch
   → ep_deliver_event removes I from scan batch
   → ep_item_poll re-polls eventfd
   → E.count=0 reports EPOLLOUT only
   → mask with EPOLLIN|ERR|HUP yields zero
   → no event copied and no level-triggered requeue
   → ep_done_scan leaves EP.rdllist empty
   → epoll_wait returns 0 without sleeping

   parent epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → resolve F7 and F6 with temporary file references
   → lock EP.mtx and find I in EP.rbr
   → ep_unregister_pollwait removes P from E.wqh
   → free P synchronously from pwq_cache
   → epi_fget temporarily pins F6
   → under F6.f_lock clear F6.f_ep and remove I.fllink
   → free last epitems_head
   → erase I from EP.rbr
   → I is already absent from EP.rdllist
   → kfree_rcu(I)
   → EP.refcount 2 -> 1
   → epoll_ctl returns 0

   parent close(6)
   → remove shared fd 6 publication and cloexec bit
   → final synchronous __fput(F6)
   → eventpoll_release sees F6.f_ep=NULL
   → eventfd_release sends EPOLLHUP to empty E.wqh
   → E.kref 1 -> 0
   → return internal id and free eventfd ctx
   → release [eventfd] pseudo path and file
   → close(6) returns 0

   parent close(7)
   → remove shared fd 7 publication and cloexec bit
   → final synchronous __fput(F7)
   → ep_eventpoll_release / ep_clear_and_put
   → EP.poll_wait empty
   → empty pollwait and tree drain passes under EP.mtx
   → EP.refcount 1 -> 0
   → ep_free destroys mutex/user/wakeup-source state
   → kfree_rcu(EP)
   → release [eventpoll] pseudo path and file
   → close(7) returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：level-triggered eventfd/epoll lifecycle complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* last syscall：``close(7)``；
* last result/RAX：0；
* eventfd read result：8，userspace value=5；
* zero-time epoll_wait result：0；
* ``EPOLL_CTL_DEL`` result：0；
* ``close(6)`` result：0；
* shared fd 6：closed and unallocated；
* shared fd 7：closed and unallocated；
* callback entry ``P``：freed synchronously during DEL；
* eventfd file ``F6``：freed；
* eventfd ctx ``E``：freed；
* eventfd internal id：returned to ``eventfd_ida``；
* epitem ``I``：unregistered and no longer accessible；
* ``I`` storage：queued/freed through ``kfree_rcu`` grace period；
* eventpoll file ``F7``：freed；
* eventpoll ``EP``：logical lifetime ended；
* ``EP`` storage：queued/freed through ``kfree_rcu`` grace period；
* ``EP->rbr`` 与 ``EP->rdllist``：释放前均为空；
* singleton ``anon_inode_inode``：仍active；
* global ``anon_inode_mnt``：仍mounted；
* helper：仍阻塞在eventfd之外；
* shared ``files_struct``：仍active，fd 0..5保持原状；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. eventfd read清除counter，但不直接扫描或清除epoll ready list。
#. read发送 ``EPOLLOUT`` wake；不匹配 ``EPOLLIN`` interest时callback不改变ready state。
#. epoll ready list保存需要重新验证的candidate，不是永久readiness事实。
#. 零超时epoll_wait仍会re-poll现有candidate，只是不等待新事件。
#. re-poll不匹配时只清除ready membership，不删除registration。
#. ``EPOLL_CTL_DEL`` 不读取用户event结构，event参数可以为NULL。
#. callback entry必须先从目标wait queue移除，之后才能释放epitem。
#. ``epi_fget`` 临时pin target file，防止与final ``__fput`` 竞态。
#. 最后watcher移除时 ``F6->f_ep`` 被设为NULL。
#. DEL只删除relationship，不关闭fd 6或fd 7。
#. epitem为eventpoll增加一个ref；DEL使 ``EP->refcount`` 从2降回1。
#. ``kfree_rcu(I)`` 与 ``kfree_rcu(EP)`` 结束合法访问，但physical memory回收可晚于syscall返回。
#. 显式DEL使close eventfd时无需走反向registration清理。
#. eventpoll close在空RB tree上完成两遍空drain，再释放基础reference。
#. 两份anon-inode pseudo file各自释放per-file dentry与mount reference；全局anon_inodefs继续存在。

下一任务
--------

当前没有已选定场景。优先候选是 ``signalfd4`` 与epoll组合：

::

   block SIGUSR1 in parent/helper
   → signalfd4(-1, mask(SIGUSR1), SFD_CLOEXEC) creates fd 6
   → epoll_create1 creates fd 7
   → EPOLL_CTL_ADD signalfd EPOLLIN
   → parent epoll_wait blocks
   → helper tgkill sends SIGUSR1 to parent
   → blocked signal becomes pending
   → signalfd poll callback marks epitem ready
   → epoll_wait returns EPOLLIN
   → read signalfd_siginfo consumes pending signal

开始前必须固定signal target、private/shared pending queue、thread masks、signalfd wait queue、task wake规则、epoll callback与read dequeue顺序。
