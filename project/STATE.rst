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

最新三章：

#. ``LK-EVENTFDCLOSE-131``：close(6) 怎样撤销eventfd fd并同步进入最后一次__fput()？
#. ``LK-EVENTFDCLOSE-132``：eventfd_release() 怎样发送EPOLLHUP并释放eventfd_ctx？
#. ``LK-EVENTFDCLOSE-133``：__fput() 怎样释放anon-inode path并让close()返回0？

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
#. eventfd final close、HUP wake与anon-inode file teardown。

本批固定场景
------------

::

   runtime relation    = continuation of LK-EVENTFD-128..130
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   scheduling          = both SCHED_NORMAL
   current executor    = parent
   close call          = parent close(6)
   fd 6                = unique eventfd file reference
   file mode           = O_RDWR, blocking, close-on-exec
   eventfd count       = 0
   semaphore mode      = disabled
   ctx kref            = 1
   internal id         = valid non-negative eventfd_ida allocation
   wait queue          = empty
   poll/epoll          = no registration or callback
   extra ctx refs      = none
   in-flight fd refs   = none
   helper              = blocked outside eventfd
   global anon inode   = singleton anon_inode_inode remains active
   failure policy      = no close, VFS, dcache, mount or allocator failure

完整控制流
----------

::

   parent close(6)
   → entry_SYSCALL_64 / do_syscall_64 / __x64_sys_close
   → file_close_fd(6)
   → lock shared files->file_lock
   → fdt->fd[6] = NULL
   → clear open_fds bit and close_on_exec bit
   → update next_fd
   → unlock files->file_lock
   → fd 6 becomes unavailable to parent and helper
   → filp_flush(eventfd file F) returns 0
   → fput_close_sync(F)
   → file_ref_put_close consumes final file reference
   → synchronous __fput(F)
   → fsnotify_close / eventpoll_release / locks / security cleanup
   → no epoll link, lock or FASYNC state
   → eventfd_release(inode, F)
   → wake_up_poll(E.wqh, EPOLLHUP)
   → lock E.wqh.lock and scan empty queue
   → zero task or epoll callback awakened
   → eventfd_ctx_put(E)
   → E.kref 1 -> 0
   → eventfd_free / eventfd_free_ctx
   → ida_free(E.id)
   → kfree(E)
   → eventfd count, flags, id and wait queue cease to exist
   → return to __fput
   → fops_put / file owner / access cleanup
   → dput per-file [eventfd] pseudo dentry
   → drop this dentry's singleton anon-inode reference
   → singleton anon_inode_inode remains active
   → mntput per-file anon_inode_mnt reference
   → global anon_inode_mnt remains mounted
   → file_free(F)
   → fput_close_sync returns
   → close uses filp_flush retval 0
   → parent returns CPL3 with RAX=0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：eventfd final close complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、 ``on_cpu=1``；
* final syscall：``close(6)``；
* final result/RAX：0；
* userspace RIP：close syscall之后的下一条指令；
* shared fd 6：closed and unallocated；
* fd 6 open bit：cleared；
* fd 6 close-on-exec bit：cleared；
* helper：仍阻塞在eventfd之外；
* eventfd file ``F``：freed；
* eventfd ctx ``E``：freed；
* eventfd internal id：returned to ``eventfd_ida``；
* eventfd counter、flags与wait queue：对象已不存在；
* HUP wake callbacks/tasks：0；
* ``[eventfd]`` pseudo dentry：已失去最后活动引用；
* singleton ``anon_inode_inode``：仍active；
* global ``anon_inode_mnt``：仍mounted；
* per-file anon-inode mount reference：released；
* shared ``files_struct``：仍active，fd 0..5保持原状；
* task_work/delayed_fput：未使用；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. fdtable publication、file reference、ctx kref和path reference是四套不同lifetime。
#. ``file_close_fd`` 撤销共享fd 6，但当前close仍持有转交出来的file reference。
#. ``EFD_CLOEXEC`` 只属于fdtable bookkeeping，显式close时与open bit一起清理。
#. ``fput_close_sync`` 保证final ``__fput`` 在close返回前同步完成。
#. ``eventpoll_release`` 位于file-specific ``release`` 之前。
#. ``wake_up_poll(EPOLLHUP)`` 的HUP是wake key；空queue时不会产生实际observer。
#. eventfd使用 ``wake_up_poll``，不是 ``wake_up_pollfree``。
#. ctx kref与file refcount互相独立；无额外ctx引用时kref从1直接到0。
#. eventfd internal id与userspace fd number属于不同编号空间。
#. ``kfree(E)`` 之后不能再读取counter或wait queue状态。
#. ``release`` callback返回值不会覆盖close retval；close结果来自 ``filp_flush``。
#. 普通eventfd复用singleton anon inode，不拥有独立inode。
#. ``dput`` 结束per-file pseudo dentry，不释放全局singleton inode。
#. ``mntput`` 归还per-file mount reference，不卸载全局anon_inodefs。
#. anonymous inode file teardown不产生磁盘I/O、journal或writeback。

下一任务
--------

当前没有已选定场景。优先候选是用epoll实际观察eventfd wake：

::

   eventfd2(0, EFD_CLOEXEC) -> fd 6
   epoll_create1(EPOLL_CLOEXEC) -> fd 7
   epoll_ctl(7, EPOLL_CTL_ADD, 6, EPOLLIN)
   → eventpoll item attaches callback to eventfd wait queue
   parent epoll_wait(7, events, 1, -1)
   → parent blocks on eventpoll wait queue
   helper write(6, u64 5)
   → eventfd EPOLLIN callback marks item ready
   → wake parent
   → epoll_wait copies one event to userspace

开始前必须固定event mask、level/edge trigger mode、event data、epoll exclusive flag、fd references、callback顺序、ready-list状态与scheduler顺序。
