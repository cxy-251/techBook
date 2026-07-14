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

最新三章：

#. ``LK-EVENTFD-128``：eventfd2() 怎样建立counter并发布fd 6？
#. ``LK-EVENTFD-129``：eventfd read() 怎样在counter为0时进入locked wait queue？
#. ``LK-EVENTFD-130``：eventfd write() 怎样唤醒reader并让read()返回counter？

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
#. eventfd counter blocking read与writer wakeup。

本批固定场景
------------

::

   runtime relation    = independent scenario
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   scheduling          = both SCHED_NORMAL
   occupied fds        = 0..5
   create call         = eventfd2(0, EFD_CLOEXEC)
   returned fd         = 6
   access mode         = O_RDWR
   nonblocking         = disabled
   semaphore mode      = disabled
   initial counter     = 0
   reader call         = parent read(6, &value, 8)
   writer call         = helper write(6, &three, 8), three=3
   wait entry          = non-exclusive TASK_INTERRUPTIBLE
   signal state        = none pending
   scheduler order     = parent blocks; helper writes and blocks outside eventfd; parent resumes
   failure policy      = no allocation, fd, copy, signal or scheduler failure

完整控制流
----------

::

   parent eventfd2(0, EFD_CLOEXEC)
   → __x64_sys_eventfd2 / do_eventfd
   → allocate eventfd_ctx E
   → kref_init, init_waitqueue_head
   → E.count=0, E.flags=EFD_CLOEXEC
   → anon_inode_getfile_fmode("[eventfd]", eventfd_fops, E, O_RDWR, FMODE_NOWAIT)
   → reserve fd 6 and set close-on-exec
   → publish fd 6 into shared files_struct
   → parent returns CPL3 with RAX=6

   parent read(6, &value, 8)
   → ksys_read / vfs_read / new_sync_read
   → eventfd_read
   → lock E.wqh.lock with local IRQ disabled
   → count==0, blocking mode
   → wait_event_interruptible_locked_irq(E.wqh, E.count)
   → stack wait entry, non-exclusive
   → parent TASK_INTERRUPTIBLE
   → unlock E.wqh.lock and enable IRQ
   → schedule / __schedule
   → parent leaves CPU0 and helper runs

   helper write(6, &three, 8)
   → ksys_write / vfs_write / eventfd_write
   → copy userspace u64 value 3
   → lock E.wqh.lock with local IRQ disabled
   → E.count 0 -> 3
   → wake_up_locked_poll(E.wqh, EPOLLIN)
   → parent TASK_RUNNING and enqueued on CPU0
   → unlock E.wqh.lock and enable IRQ
   → helper write returns 8
   → helper blocks outside eventfd

   scheduler restores parent original read stack
   → do_wait_intr_irq returns from schedule
   → reacquire E.wqh.lock with IRQ disabled
   → condition E.count!=0 is true
   → remove parent wait entry
   → eventfd_ctx_do_read
   → non-semaphore read returns entire count 3
   → E.count 3 -> 0
   → no actual EPOLLOUT waiter
   → unlock E.wqh.lock and enable IRQ
   → copy u64 value 3 to userspace
   → parent read returns 8

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：eventfd counter blocking read/writer wakeup complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、``on_cpu=1``；
* parent read result/RAX：8；
* parent userspace ``value``：3；
* helper write result：8；
* helper：阻塞在eventfd之外；
* shared fd 6：open、close-on-exec；
* eventfd file：``O_RDWR``、blocking；
* eventfd ctx E：仍active；
* E ``count``：0；
* E semaphore mode：disabled；
* E wait queue：没有本次waiter；
* E waitqueue spinlock：unlocked；
* parent栈上wait entry：生命周期结束；
* anon-inode pseudo file：仍由fd 6引用；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. eventfd用一个 ``O_RDWR`` fd同时完成read与write。
#. counter和wait queue由 ``ctx->wqh.lock`` 同时保护。
#. ``EFD_CLOEXEC`` 设置fdtable close-on-exec bit，不启用nonblocking。
#. eventfd read/write都要求8字节用户对象。
#. count为0且blocking时，reader使用non-exclusive locked wait entry。
#. locked wait在睡眠前释放waitqueue lock并重新打开本地IRQ。
#. writer先在锁内增加counter，再执行wake。
#. wake只让reader runnable，不直接执行read后半段。
#. 非semaphore模式read取得整个counter并清零。
#. read返回8是字节数，counter值3写入用户buffer。
#. read完成不会自动close fd或释放eventfd ctx。
#. anon-inode eventfd不产生磁盘filesystem、journal或block I/O。

下一任务
--------

当前没有已选定场景。优先候选是eventfd final close：

::

   parent close(6)
   → remove shared fd publication
   → fput_close_sync / final __fput
   → eventfd_release
   → wake poll waiters with EPOLLHUP
   → eventfd_ctx_put
   → ctx kref reaches zero
   → free eventfd id and eventfd_ctx
   → release anon-inode file/path

开始前必须固定是否存在poll/epoll引用、额外 ``eventfd_ctx_fdget`` 引用、close执行线程、waiter状态与最终file/path引用顺序。
