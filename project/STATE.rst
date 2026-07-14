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

最新三章：

#. ``LK-PIPECLOSE-122``：close(7) 怎样撤销 write end 并把 writers 降为 0？
#. ``LK-PIPECLOSE-123``：空管道在 writers=0 时，read() 为什么直接返回 EOF？
#. ``LK-PIPECLOSE-124``：最后一次 close(6) 怎样释放pipe page、ring与pseudo inode？

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
#. anonymous pipe创建、空pipe阻塞read、writer插入buffer与reader wakeup；
#. pipe write-end close、EOF read与final pipe object teardown。

本批固定场景
------------

::

   runtime relation    = continuation of LK-PIPE-119..121
   CPUs online         = CPU0 only
   process             = parent + helper threads, same TGID
   files table         = shared through CLONE_FILES
   scheduling          = both SCHED_NORMAL
   initial fds         = fd 6 read end, fd 7 write end
   initial endpoints   = readers=1, writers=1, files=2
   initial ring        = head=tail=1, occupancy=0
   cached page         = Q in pipe->tmp_page[0]
   wait queues         = no waiter
   first call          = helper close(7)
   second call         = parent read(6, eofbuf, 5)
   eofbuf initial      = five 'X' bytes
   final call          = parent close(6)
   extra refs          = no dup/SCM_RIGHTS/epoll/io_uring/splice/in-flight I/O
   signal state        = none pending
   failure policy      = no close, copy, VFS or allocator failure

完整控制流
----------

::

   helper close(7)
   → __x64_sys_close
   → file_close_fd under shared files->file_lock
   → fdt->fd[7] = NULL
   → remove fd 7 publication for both threads
   → filp_flush returns 0
   → fput_close_sync(write_file)
   → synchronous __fput
   → pipe_release
   → lock pipe->mutex
   → writers 1 -> 0; readers stays 1
   → wake rd_wait and wr_wait because only one endpoint side remains
   → no actual waiter in fixed state
   → unlock pipe->mutex
   → put_pipe_info
   → files 2 -> 1
   → release write-side path and file object
   → helper returns CPL3 with RAX=0

   parent read(6, eofbuf, 5)
   → ksys_read / vfs_read / new_sync_read
   → anon_pipe_read
   → lock pipe->mutex
   → head==tail and writers==0
   → break with ret=0
   → no wait entry, no schedule, no copy_to_iter
   → unlock pipe->mutex
   → parent returns CPL3 with RAX=0 EOF
   → eofbuf remains "XXXXX"

   parent close(6)
   → file_close_fd removes shared fd 6
   → fput_close_sync(read_file)
   → synchronous __fput
   → pipe_release
   → readers 1 -> 0; writers remains 0
   → no asymmetric endpoint wake
   → put_pipe_info
   → files 1 -> 0
   → inode->i_pipe = NULL
   → free_pipe_info
   → release 16-page user pipe accounting
   → active ring buffers already zero and buf->ops NULL
   → __free_page(Q) from tmp_page[0]
   → kfree 16-slot pipe_buffer ring
   → kfree pipe_inode_info
   → dput final pseudo dentry path reference
   → drop pseudo inode reference; VFS/RCU may defer slab free
   → mntput per-file pipefs mount reference
   → file_free(read_file)
   → parent returns CPL3 with RAX=0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* runtime scenario：anonymous pipe endpoint close、EOF与final teardown complete；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq=1``、``on_cpu=1``；
* final syscall：``close(6)``；
* final result/RAX：0；
* previous EOF read result：0；
* ``eofbuf``：仍为 ``"XXXXX"``；
* shared fd 6：closed；
* shared fd 7：closed；
* write-side ``struct file``：released；
* read-side ``struct file``：released；
* ``pipe_inode_info``：freed；
* ring：freed；
* page Q：已归还page allocator；
* active pipe wait queues/mutex/counters：对象已不存在；
* pseudo dentry/inode：已退出活动对象图；memory可按VFS/RCU规则延后释放；
* global ``pipe_mnt``：仍存在，本场景没有卸载pipefs；
* helper：仍阻塞在pipe之外；
* shared ``files_struct``：仍存在，fd 0..5保持原状；
* filesystem/block I/O：未发生；
* next runtime scenario：unselected。

关键边界
--------

#. ``file_close_fd`` 撤销共享fd publication；另一个thread也立即失去该fd number。
#. fdtable slot清空与 ``pipe_release`` endpoint计数下降不是同一个动作。
#. 用户态close通过 ``fput_close_sync`` 同步执行最后 ``__fput``。
#. ``writers`` 从1降到0会wake partner queues，即使固定场景没有waiter。
#. ``empty && writers==0`` 的pipe read立即返回0 EOF，不进入wait queue。
#. EOF不会向用户buffer复制零字节，也不会自动关闭read endpoint。
#. ``readers/writers`` 决定I/O语义；``files`` 决定 ``pipe_inode_info`` lifetime。
#. ``files==0`` 才触发 ``free_pipe_info``。
#. consumed ring slot的 ``buf->ops`` 已清空，final teardown不会重复release Q。
#. cached page Q直到pipe object销毁才通过 ``__free_page`` 归还allocator。
#. anonymous pipe teardown不涉及磁盘filesystem、journal或block I/O。
#. pseudo dentry/inode最终memory free可被RCU延后，但用户已经无法引用它们。
#. per-file ``mntput`` 不会卸载全局pipefs mount。

下一任务
--------

当前没有已选定场景。优先候选是private futex阻塞与唤醒：

::

   shared private user word = 0
   parent futex(FUTEX_WAIT_PRIVATE, expected=0)
   → construct private futex key
   → hash bucket lookup and waiter enqueue
   → verify user word still equals 0
   → parent TASK_INTERRUPTIBLE and schedule out
   → helper atomic_store(word, 1)
   → futex(FUTEX_WAKE_PRIVATE, 1)
   → find and remove one waiter
   → wake parent
   → parent returns 0

开始前必须固定user address、mapping、alignment、memory ordering、futex flags、hash bucket、signal状态与scheduler顺序。
