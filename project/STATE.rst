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

最新三章：

#. ``LK-PIPE-119``：pipe2() 怎样建立匿名管道并发布 fd 6/7？
#. ``LK-PIPE-120``：空管道 read() 怎样进入 exclusive wait queue 并阻塞？
#. ``LK-PIPE-121``：pipe write() 怎样唤醒reader并让 read() 返回5？

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
#. monotonic ``clock_nanosleep`` 自然到期、hrtimer/APIC/scheduler唤醒；
#. ``SIGUSR1`` 中断relative nanosleep、remaining copyout、rt signal frame与 ``rt_sigreturn``；
#. anonymous pipe创建、空pipe阻塞read、writer插入buffer与reader wakeup。

本批固定场景
------------

::

   runtime relation    = independent scenario
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   scheduling          = both SCHED_NORMAL
   occupied fds        = 0..5
   pipe call           = pipe2(pipefd, O_CLOEXEC)
   returned fds        = pipefd[0]=6, pipefd[1]=7
   pipe flags          = blocking stream; no O_NONBLOCK/O_DIRECT/notification mode
   page size           = 4096
   default ring        = 16 slots, 65536 bytes
   endpoints           = readers=1, writers=1, files=2
   reader call         = parent read(6, buf, 5)
   writer call         = helper write(7, "hello", 5)
   signal state        = none pending; no SIGPIPE
   allocation          = first anonymous page Q succeeds
   scheduler order     = parent blocks; helper writes; helper then blocks outside pipe; parent resumes
   failure policy      = no fd, inode, page, copy, waitqueue or scheduler failure

完整控制流
----------

::

   parent pipe2(pipefd, O_CLOEXEC)
   → __x64_sys_pipe2 / do_pipe2
   → create_pipe_files
   → new pipefs pseudo inode
   → alloc_pipe_info
   → allocate 16 pipe_buffer ring entries
   → initialize rd_wait, wr_wait and pipe mutex
   → readers=1, writers=1, files=2
   → create read/write struct file objects using pipeanon_fops
   → reserve fd 6 and fd 7 with close-on-exec
   → copy {6,7} to userspace
   → fd_install both ends
   → pipe2 returns 0

   parent read(6, buf, 5)
   → ksys_read / vfs_read / new_sync_read
   → anon_pipe_read
   → head=tail=0 and writers=1
   → blocking path, not EOF and not EAGAIN
   → unlock pipe mutex
   → wait_event_interruptible_exclusive(rd_wait, pipe_readable)
   → WQ_FLAG_EXCLUSIVE wait entry on parent kernel stack
   → parent TASK_INTERRUPTIBLE
   → schedule / __schedule
   → dequeue parent and switch CPU0 to helper

   helper write(7, "hello", 5)
   → ksys_write / vfs_write / new_sync_write
   → anon_pipe_write
   → empty ring with reader endpoint present
   → alloc anonymous page Q
   → copy 5 bytes into Q
   → head 0 -> 1
   → slot 0 = {page=Q, offset=0, len=5, CAN_MERGE}
   → unlock pipe mutex
   → wake_up_interruptible_sync_poll(rd_wait)
   → parent TASK_RUNNING and enqueued on CPU0
   → write returns 5
   → helper blocks outside pipe

   scheduler restores parent original read stack
   → wait condition now true
   → finish_wait removes exclusive entry
   → lock pipe mutex
   → copy_page_to_iter(Q, 0, 5)
   → parent buf becomes "hello"
   → buffer len becomes zero
   → anon_pipe_buf_release
   → cache Q in pipe->tmp_page[0]
   → tail 0 -> 1
   → head=tail=1, occupancy=0
   → read returns 5

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、``on_cpu=1``；
* parent read result/RAX：5；
* parent user buffer：``"hello"``；
* helper：write result为5，随后阻塞在pipe之外；
* fd 6：anonymous pipe read end，open，close-on-exec；
* fd 7：anonymous pipe write end，open，close-on-exec；
* ``pipe->files``：2；
* ``pipe->readers``：1；
* ``pipe->writers``：1；
* ``ring_size=max_usage``：16；
* byte capacity：65536；
* ``head=1``、``tail=1``、occupancy=0；
* active pipe buffers：0；
* page ``Q``：缓存于 ``pipe->tmp_page[0]``；
* ``tmp_page[1]``：NULL；
* reader wait entry：已移除；
* pipe wait queues：没有本次waiter；
* pipe mutex：unlocked；
* filesystem/block I/O：未发生；
* next runtime scenario：unselected。

关键边界
--------

#. anonymous pipe使用pipefs pseudo inode，不触发磁盘filesystem。
#. 16-slot ring metadata在pipe创建时分配，data page按write需求分配。
#. read/write end是两个file object，共享一个 ``pipe_inode_info``。
#. pipe是stream，read/write没有普通文件position语义。
#. 空pipe且writers存在会阻塞；空pipe且writers为0才返回EOF。
#. reader在等待前释放pipe mutex，并以exclusive TASK_INTERRUPTIBLE entry加入 ``rd_wait``。
#. wakeup只把reader变为runnable，不直接执行reader代码。
#. ``WF_SYNC`` 是调度提示，不保证立即handoff。
#. 5-byte write成功后形成一个anonymous ``pipe_buffer``。
#. buffer完全消费后tail推进，pipe重新为空。
#. page count允许时，anonymous page缓存到 ``tmp_page[]`` 而非立即释放给buddy。
#. pipe empty与pipe object释放是不同状态；两个endpoint仍open。

下一任务
--------

当前没有已选定场景。优先候选是继续追踪pipe endpoint关闭、EOF与最终对象释放：

::

   helper/parent close(7)
   → remove shared fd 7 publication
   → pipe_release decrements writers 1 -> 0
   → wake rd_wait
   → parent read(6, buf, 5) sees empty pipe and writers=0
   → read returns 0 EOF without sleeping
   → close(6)
   → readers 1 -> 0, files 1 -> 0
   → free tmp_page Q, ring, pipe_inode_info and pseudo inode

开始前必须固定close执行线程、共享fd table影响、是否存在正在sleep的reader、fput执行上下文，以及final inode/file reference顺序。
