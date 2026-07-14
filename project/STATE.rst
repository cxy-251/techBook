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

最新三章：

#. ``LK-SIGNALFD-140``：signalfd4() 怎样把阻塞信号变成可poll的fd并挂进epoll？
#. ``LK-SIGNALFD-141``：tgkill() 怎样让blocked SIGUSR1经signalfd callback唤醒epoll_wait？
#. ``LK-SIGNALFD-142``：parent怎样从epoll event进入signalfd read并取出128字节siginfo？

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
#. blocked ``SIGUSR1`` 通过signalfd与epoll交付并读取 ``signalfd_siginfo``。

本批固定场景
------------

::

   runtime relation    = independent scenario after LK-EPOLLCLOSE-139
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   signal structures   = shared signal_struct and sighand_struct
   scheduling          = both SCHED_NORMAL
   occupied fds        = 0..5
   blocked masks       = parent/helper both contain SIGUSR1
   initial pending     = no private/shared SIGUSR1
   signalfd call       = signalfd4(-1, mask(SIGUSR1), SFD_CLOEXEC)
   signalfd fd         = 6, blocking
   epoll call          = epoll_create1(EPOLL_CLOEXEC)
   epoll fd            = 7
   registration        = EPOLL_CTL_ADD fd 6 with EPOLLIN
   stored mask         = EPOLLIN | EPOLLERR | EPOLLHUP
   trigger mode        = level-triggered
   event data          = 0x51FD6
   callback entry      = P, non-exclusive, on sighand->signalfd_wqh
   parent wait         = epoll_wait(7, events, 1, -1)
   helper signal       = tgkill(tgid, parent_tid, SIGUSR1)
   read call           = read(6, &ssi, 128)
   scheduler order     = parent blocks; helper sends and blocks; parent resumes
   failure policy      = no fd, copy, allocation, permission, signal or scheduler failure

完整控制流
----------

::

   parent/helper already block SIGUSR1

   parent signalfd4(-1, {SIGUSR1}, SFD_CLOEXEC)
   → validate size and flags
   → remove SIGKILL/SIGSTOP from selectable set
   → invert user set for next_signal/dequeue_signal mask semantics
   → allocate signalfd_ctx S
   → create [signalfd] anon-inode file F6
   → publish blocking close-on-exec fd 6

   parent epoll_create1(EPOLL_CLOEXEC)
   → allocate eventpoll EP
   → initialize EP.mtx/lock/wq/poll_wait/rbr/rdllist
   → publish [eventpoll] file F7 as fd 7

   parent epoll_ctl(7, ADD, 6, {EPOLLIN,data=0x51FD6})
   → allocate epitem I keyed by (F6, fd 6)
   → store EPOLLIN | EPOLLERR | EPOLLHUP
   → attach I to F6.f_ep and EP.rbr
   → EP.refcount 1 -> 2
   → signalfd_poll installs eppoll_entry P
   → P.wait.func = ep_poll_callback
   → add P non-exclusively to shared sighand->signalfd_wqh
   → no private/shared SIGUSR1, so initial readiness is zero
   → EP.rdllist remains empty

   parent epoll_wait(7, events, 1, -1)
   → create stack wait entry W
   → under EP.lock set TASK_INTERRUPTIBLE
   → add W exclusively to EP.wq
   → parent schedules out
   → helper becomes current

   helper tgkill(tgid, parent_tid, SIGUSR1)
   → prepare SI_TKILL info
   → locate exact parent task and validate TGID
   → choose parent private pending queue
   → allocate sigqueue Q with sender TGID/UID
   → signalfd_notify(parent, SIGUSR1)
   → ordinary wake_up on shared signalfd_wqh with NULL poll key
   → P invokes ep_poll_callback
   → callback appends I to EP.rdllist
   → callback wakes exclusive W on EP.wq
   → parent TASK_INTERRUPTIBLE -> TASK_RUNNING
   → W auto-removes from EP.wq
   → signal path sets parent pending SIGUSR1 bit
   → complete_signal sees blocked PIDTYPE_PID signal and performs no signal_wake_up
   → helper tgkill returns 0 and helper blocks outside objects

   scheduler restores parent epoll_wait stack
   → parent re-enters epoll ready scan
   → signalfd_poll locks shared sighand siglock
   → parent private pending contains selectable SIGUSR1
   → target reports EPOLLIN
   → copy events[0] = {EPOLLIN, data=0x51FD6}
   → level-triggered I returns to EP.rdllist
   → epoll_wait returns 1

   parent read(6, &ssi, 128)
   → signalfd_read_iter accepts one-record buffer
   → signalfd_dequeue locks sighand siglock
   → dequeue_signal removes parent private pending SIGUSR1 and Q
   → no blocking read wait path
   → signalfd_copyinfo zeroes 128-byte record
   → ssi_signo=SIGUSR1, ssi_code=SI_TKILL
   → ssi_pid=shared TGID, ssi_uid=sender UID, ssi_tid=0
   → copy one record to userspace
   → read returns 128
   → read does not remove I from EP.rdllist

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：blocked SIGUSR1 signalfd+epoll delivery complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* helper：阻塞在signalfd/epoll之外；
* helper ``tgkill`` result：0；
* parent ``epoll_wait`` result：1；
* ``events[0].events``：``EPOLLIN``；
* ``events[0].data.u64``：``0x51FD6``；
* parent signalfd ``read`` result：128；
* ``ssi_signo``：``SIGUSR1``；
* ``ssi_code``：``SI_TKILL``；
* ``ssi_pid``：shared TGID；
* ``ssi_uid``：sender UID；
* ``ssi_tid``：0；
* parent/helper blocked mask：仍包含 ``SIGUSR1``；
* parent private pending：不含 ``SIGUSR1``；
* shared pending：不含 ``SIGUSR1``；
* sigqueue ``Q``：已dequeue；
* shared fd 6：open blocking signalfd file ``F6``，close-on-exec；
* signalfd ctx ``S``：active；
* shared fd 7：open eventpoll file ``F7``，close-on-exec；
* eventpoll ``EP``：active， ``refcount=2``；
* callback ``P``：仍挂在共享 ``sighand->signalfd_wqh``；
* ``EP->rbr``：包含epitem ``I``；
* ``EP->rdllist``：包含stale-ready ``I``；
* ``EP->ovflist``：``EP_UNACTIVE_PTR``；
* ``EP->wq``：无parent waiter；
* actual signalfd EPOLLIN readiness：false；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. signalfd不会自动block signal；blocked mask由用户程序管理。
#. signalfd ctx保存用户集合的内部反转mask。
#. shared signalfd fd不意味着thread-private pending queue共享。
#. callback ``P`` 挂在sighand signalfd queue，task waiter ``W`` 挂在eventpoll queue。
#. ``P`` non-exclusive； ``W`` exclusive。
#. tgkill把SIGUSR1放进parent private pending， ``si_code=SI_TKILL``。
#. ``SI_TKILL`` 的sender pid字段是TGID，不是helper TID。
#. ``signalfd_notify`` 先于pending bit设置，并使用NULL poll key。
#. NULL key只把epitem标成candidate，最终readiness必须重新poll。
#. parent由epoll callback链唤醒，不是由普通 ``signal_wake_up`` 唤醒。
#. blocked PIDTYPE_PID signal不会建立用户signal frame。
#. epoll交付不消费signal；signalfd read才执行dequeue。
#. ``signalfd_siginfo`` 固定为128 bytes。
#. signalfd read不修改blocked mask或registration。
#. read后level-triggered epitem可能暂留ready list，等待下次scan重新验证。

下一任务
--------

当前没有已选定场景。优先接续是清理stale-ready并释放对象：

::

   epoll_wait(7, events, 1, 0)
   → re-poll signalfd and remove stale-ready I
   → return 0

   epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → unregister P and erase I

   close(6)
   → signalfd_release frees S

   close(7)
   → eventpoll release ends EP through kfree_rcu
