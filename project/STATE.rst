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

最新三章：

#. ``LK-EPOLL-134``：epoll_ctl(ADD) 怎样把eventfd callback挂进wait queue？
#. ``LK-EPOLL-135``：epoll_wait() 怎样把parent挂到eventpoll自己的wait queue？
#. ``LK-EPOLL-136``：eventfd write怎样触发epoll callback并让epoll_wait返回1？

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
#. eventfd通过level-triggered epoll callback唤醒 ``epoll_wait``。

本批固定场景
------------

::

   runtime relation    = independent scenario
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   scheduling          = both SCHED_NORMAL
   occupied fds        = 0..5
   eventfd call        = eventfd2(0, EFD_CLOEXEC)
   eventfd fd          = 6
   epoll call          = epoll_create1(EPOLL_CLOEXEC)
   epoll fd            = 7
   registration        = EPOLL_CTL_ADD fd 6 to epfd 7
   user interest       = EPOLLIN
   stored interest     = EPOLLIN | EPOLLERR | EPOLLHUP
   trigger mode        = level-triggered
   event data          = 0xEFD6
   EPOLLEXCLUSIVE      = disabled
   EPOLLONESHOT        = disabled
   EPOLLET             = disabled
   initial counter     = 0
   parent wait         = epoll_wait(7, events, 1, -1)
   helper write        = write(6, &five, 8), five=5
   signal state        = none pending
   scheduler order     = parent blocks; helper writes and blocks; parent resumes
   failure policy      = no fd, quota, allocation, copy, signal or scheduler failure

完整控制流
----------

::

   parent eventfd2(0, EFD_CLOEXEC)
   → allocate eventfd_ctx E
   → publish O_RDWR blocking fd 6 with E.count=0

   parent epoll_create1(EPOLL_CLOEXEC)
   → do_epoll_create / ep_alloc
   → initialize eventpoll EP
   → EP.mtx, EP.lock, EP.wq, EP.poll_wait
   → EP.rbr empty, EP.rdllist empty
   → publish [eventpoll] file as fd 7

   parent epoll_ctl(7, EPOLL_CTL_ADD, 6, {EPOLLIN, data=0xEFD6})
   → resolve eventpoll file F7 and eventfd file F6
   → add EPOLLERR | EPOLLHUP to stored mask
   → allocate epitem I
   → I key = (F6, fd 6)
   → attach I to F6->f_ep reverse hlist
   → insert I into EP.rbr
   → EP.refcount 1 -> 2
   → eventfd_poll with ep_ptable_queue_proc
   → allocate eppoll_entry P
   → P.wait.func = ep_poll_callback
   → add P non-exclusively to E.wqh
   → eventfd count 0 reports only EPOLLOUT
   → masked readiness is zero
   → I remains off EP.rdllist
   → epoll_ctl returns 0

   parent epoll_wait(7, events, 1, -1)
   → timeout converts to NULL
   → ready list initially empty
   → stack wait entry W
   → W.func = ep_autoremove_wake_function
   → lock EP.lock
   → parent TASK_INTERRUPTIBLE
   → final ready recheck still false
   → add W exclusively to EP.wq
   → unlock EP.lock
   → schedule_hrtimeout_range(NULL)
   → parent leaves CPU0
   → helper becomes current

   helper write(6, &five, 8)
   → eventfd_write
   → lock E.wqh.lock
   → E.count 0 -> 5
   → wake_up_locked_poll(E.wqh, EPOLLIN)
   → invoke P.wait.func = ep_poll_callback
   → lock EP.lock
   → incoming EPOLLIN matches I interest
   → append I to EP.rdllist
   → wake EP.wq
   → W default wake makes parent runnable
   → W auto-removes from EP.wq
   → unlock EP.lock
   → unlock E.wqh.lock
   → helper write returns 8
   → helper blocks outside eventfd

   scheduler restores parent original epoll_wait stack
   → schedule_hrtimeout_range returns
   → parent TASK_RUNNING
   → W already removed
   → ep_try_send_events / ep_send_events
   → lock EP.mtx
   → ep_start_scan moves I to local scan batch
   → re-poll eventfd
   → E.count=5 reports EPOLLIN | EPOLLOUT
   → interest mask yields EPOLLIN
   → copy events[0] = {EPOLLIN, data=0xEFD6}
   → level-triggered I requeued to EP.rdllist
   → ep_done_scan
   → unlock EP.mtx
   → epoll_wait returns 1

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：eventfd level-triggered epoll wake complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* parent latest syscall：``epoll_wait(7, events, 1, -1)``；
* parent return/RAX：1；
* ``events[0].events``：``EPOLLIN``；
* ``events[0].data.u64``：``0xEFD6``；
* helper write result：8；
* helper：阻塞在eventfd之外；
* shared fd 6：eventfd file ``F6``，open、blocking、close-on-exec；
* eventfd ctx ``E``：active；
* ``E->count``：5；
* ``E->wqh``：包含non-exclusive callback entry ``P``；
* shared fd 7：eventpoll file ``F7``，open、close-on-exec；
* eventpoll ``EP``：active；
* ``EP->refcount``：2；
* ``EP->rbr``：包含epitem ``I``；
* ``EP->rdllist``：包含 ``I``；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``EP->wq``：不含parent waiter；
* ``EP->poll_wait``：empty；
* ``I->event.events``：``EPOLLIN|EPOLLERR|EPOLLHUP``；
* ``I->event.data``：``0xEFD6``；
* ``I->pwqlist``：包含 ``P``；
* parent stack wait entry ``W``：生命周期结束；
* eventfd counter consumption：none；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. eventfd ``E->wqh`` 与eventpoll ``EP->wq`` 是两条不同wait queue。
#. ``P`` 是readiness callback entry， ``W`` 才是阻塞parent的task entry。
#. ``P`` 为non-exclusive， ``W`` 为exclusive。
#. interest rbtree与ready list保存同一个epitem的不同成员关系。
#. ``epoll_ctl`` 自动加入 ``EPOLLERR|EPOLLHUP``。
#. eventfd count为0时只报告 ``EPOLLOUT``，不会使EPOLLIN注册项ready。
#. ``epoll_wait`` 睡眠前在 ``EP->lock`` 下设置状态、重查ready并入队。
#. eventfd先修改counter，再发出 ``EPOLLIN`` wake。
#. callback先把item加入ready list，再唤醒parent。
#. parent恢复原kernel stack后才重新poll并复制用户event。
#. event data来自注册时的 ``data.u64``，不是fd或counter。
#. ``epoll_wait`` 返回1表示一个event，不表示一个字节。
#. level-triggered交付不消费eventfd，counter仍为5，item仍在ready list。

下一任务
--------

当前没有已选定场景。优先候选是消费counter并清理level-triggered stale-ready状态：

::

   parent read(6, &value, 8)
   → E.count 5 -> 0
   → eventfd emits EPOLLOUT wake
   → EPOLLOUT does not match I interest
   → I still remains on EP.rdllist from prior level delivery
   parent epoll_wait(7, events, 1, 0)
   → scan I and re-poll eventfd
   → no EPOLLIN remains
   → remove I from ready list
   → return 0

之后可继续 ``EPOLL_CTL_DEL``，再关闭fd 6与fd 7，释放 ``P``、 ``I`` 与 ``EP``。
