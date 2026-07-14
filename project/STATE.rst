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

最新三章：

#. ``LK-TIMERFD-146``：timerfd怎样建立一次性hrtimer并让parent阻塞在epoll_wait？
#. ``LK-TIMERFD-147``：local APIC定时器中断怎样让timerfd callback唤醒epoll_wait？
#. ``LK-TIMERFD-148``：parent怎样从epoll event进入timerfd read并取出expiration count？

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
#. one-shot monotonic timerfd通过local APIC、hrtimer与epoll交付expiration count。

本批固定场景
------------

::

   runtime relation    = independent scenario after LK-SIGNALFDCLOSE-145
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   scheduling          = both SCHED_NORMAL
   high-res timers     = enabled
   PREEMPT_RT          = disabled
   clock-event         = CPU0 local APIC one-shot
   timerfd call        = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC)
   timerfd fd          = 6, blocking, close-on-exec
   timer value         = relative 20ms
   timer interval      = 0, one-shot
   settime flags       = 0
   cancel-on-set       = disabled
   epoll call          = epoll_create1(EPOLL_CLOEXEC)
   epoll fd            = 7
   registration        = level-triggered EPOLLIN
   event data          = 0x71FD6
   callback entry      = P on timerfd ctx T.wqh
   parent wait         = epoll_wait(7, events, 1, -1)
   scheduler order     = parent blocks; CPU0 idles; LAPIC IRQ wakes parent
   read call           = read(6, &expirations, 8)
   failure policy      = no fd/copy/allocation/timer/signal/scheduler failure

完整控制流
----------

::

   parent timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC)
   → allocate zeroed timerfd_ctx T
   → initialize T.wqh and T.cancel_lock
   → initialize embedded monotonic hrtimer with timerfd_tmrproc
   → create [timerfd] anon-inode file F6
   → publish blocking close-on-exec fd 6

   parent timerfd_settime(6, 0, relative 20ms one-shot, NULL)
   → validate timerfd file and itimerspec
   → monotonic timer does not join cancel-on-set list
   → lock T.wqh
   → hrtimer_try_to_cancel returns 0 for inactive timer
   → reset T.expired=0, T.ticks=0, T.tintv=0
   → hrtimer_setup in HRTIMER_MODE_REL
   → convert relative 20ms to absolute monotonic expiry
   → enqueue timer on CPU0 monotonic hard-hrtimer base
   → reprogram local APIC clock-event when required
   → unlock T.wqh
   → return 0

   parent epoll_create1(EPOLL_CLOEXEC)
   → allocate eventpoll EP and [eventpoll] file F7
   → publish close-on-exec fd 7

   parent epoll_ctl(7, ADD, 6, {EPOLLIN,data=0x71FD6})
   → allocate epitem I keyed by (F6, fd 6)
   → store EPOLLIN | EPOLLERR | EPOLLHUP
   → insert I into EP.rbr and F6 reverse links
   → EP.refcount 1 -> 2
   → timerfd_poll installs non-exclusive callback P on T.wqh
   → T.ticks=0, so EP.rdllist remains empty

   parent epoll_wait(7, events, 1, -1)
   → create stack waiter W
   → set parent TASK_INTERRUPTIBLE
   → add W exclusively to EP.wq
   → schedule parent out
   → CPU0 enters idle

   local APIC deadline interrupt
   → sysvec_apic_timer_interrupt
   → apic_eoi
   → local_apic_timer_interrupt
   → lapic clock-event handler hrtimer_interrupt
   → lock CPU0 hrtimer base
   → remove expired T.t.tmr from active tree
   → mark base running timer
   → release CPU-base lock around callback
   → timerfd_tmrproc / timerfd_triggered
   → lock T.wqh
   → T.expired 0 -> 1
   → T.ticks 0 -> 1
   → wake_up_locked_poll(T.wqh, EPOLLIN)
   → callback P queues I on EP.rdllist
   → wake exclusive W on EP.wq
   → parent TASK_INTERRUPTIBLE -> TASK_RUNNING
   → W auto-removes from EP.wq
   → callback returns HRTIMER_NORESTART
   → T.t.tmr remains inactive
   → hrtimer core recomputes next hardware deadline

   scheduler restores parent epoll_wait stack
   → ep_send_events scans I
   → timerfd_poll rechecks T.ticks=1
   → copy events[0]={EPOLLIN,data=0x71FD6}
   → level-triggered I returns to EP.rdllist
   → epoll_wait returns 1

   parent read(6, &expirations, 8)
   → timerfd_read_iter
   → lock T.wqh
   → wait condition already true
   → local expiration count=1
   → T.expired 1 -> 0
   → T.ticks 1 -> 0
   → no periodic restart because T.tintv=0
   → unlock T.wqh
   → copy u64 1 to userspace
   → read returns 8

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：one-shot monotonic timerfd + epoll delivery complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* helper：阻塞在timerfd/epoll之外；
* timerfd create result：fd 6；
* timerfd_settime result：0；
* epoll create result：fd 7；
* epoll ADD result：0；
* ``epoll_wait`` result：1；
* ``events[0].events``：``EPOLLIN``；
* ``events[0].data.u64``：``0x71FD6``；
* timerfd ``read`` result：8；
* userspace ``expirations``：1；
* fd 6：open blocking timerfd file ``F6``，close-on-exec；
* timerfd ctx ``T``：active；
* embedded hrtimer：inactive、not queued；
* ``T.tintv``：0；
* ``T.expired``：0；
* ``T.ticks``：0；
* ``T.wqh``：包含callback ``P``；
* fd 7：open eventpoll file ``F7``，close-on-exec；
* eventpoll ``EP``：active， ``refcount=2``；
* callback ``P``：active；
* ``EP.rbr``：包含epitem ``I``；
* ``EP.rdllist``：包含stale-ready ``I``；
* ``EP.ovflist``：``EP_UNACTIVE_PTR``；
* ``EP.wq``：无parent waiter；
* actual timerfd ``EPOLLIN`` readiness：false；
* parent/helper blocked mask：仍包含上一实验留下的 ``SIGUSR1``；
* private/shared pending ``SIGUSR1``：none；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. timerfd ctx内嵌hrtimer、ticks、expired、interval与wait queue。
#. create初始化hrtimer，settime才arm并进入CPU hrtimer tree。
#. relative expiration由hrtimer core转换为absolute monotonic deadline。
#. local APIC只产生clock-event interrupt，不直接理解timerfd。
#. ``hrtimer_interrupt`` 选择到期软件timer并在CPU-base lock之外运行callback。
#. callback在 ``T.wqh.lock`` 下把ticks从0增到1。
#. target callback ``P`` 与sleeping task waiter ``W`` 属于两条不同wait queue。
#. callback唤醒parent只建立ready candidate，交付前仍需 ``timerfd_poll`` re-poll。
#. one-shot callback返回 ``HRTIMER_NORESTART``。
#. epoll交付不消费ticks；timerfd read才清零ticks与expired。
#. timerfd read要求至少8字节并返回字节数8。
#. ``tintv=0`` 使read不执行periodic restart。
#. read后epitem可能暂留ready list，但actual ``EPOLLIN`` 已经为false。
#. fd 6/7和registration仍active，本批没有DEL或close。
#. 整个场景没有磁盘filesystem、journal或block I/O。

下一任务
--------

当前没有已选定场景。优先接续是timerfd/epoll cleanup：

::

   epoll_wait(7, events2, 1, 0)
   → timerfd_poll sees T.ticks=0
   → remove stale-ready I
   → return 0

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → remove P from T.wqh
   → erase I and kfree_rcu

   close(6)
   → hrtimer_cancel sees inactive timer
   → timerfd_release kfree_rcu(T)

   close(7)
   → empty eventpoll drain
   → kfree_rcu(EP)
