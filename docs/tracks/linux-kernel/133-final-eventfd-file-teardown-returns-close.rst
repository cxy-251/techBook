第一百三十三章：__fput() 怎样释放anon-inode path并让close()返回0？
================================================================================

上一章结束时，eventfd-specific private state已经结束生命周期：

::

   fd 6                 = closed
   eventfd ctx E        = freed
   eventfd internal id  = returned to IDA
   eventfd file F       = final __fput still running
   F->f_path            = still active

parent仍在CPU0、CPL 0中执行同一次 ``close(6)``。本章完成 ``__fput(F)`` 的通用file/path teardown，并返回用户态。

固定条件：

* eventfd file ``F`` 是普通 ``anon_inode_getfile_fmode`` 创建的pseudo file；
* 它复用全局singleton ``anon_inode_inode``，没有独立eventfd inode；
* ``F`` 拥有一个 ``[eventfd]`` pseudo dentry和一个per-file mount reference；
* 没有epoll link、file owner、FASYNC、write access或额外path reference；
* 全局 ``anon_inode_mnt`` 与singleton inode仍被anon_inodefs基础设施持有；
* dcache、mount和file slab清理均正常完成；
* 不发生filesystem writeback、journal或block I/O。

本章结束在parent回到CPL 3， ``close(6)`` 返回0；eventfd file、ctx、pseudo dentry与per-file path references均不可再访问，anon_inodefs全局mount和singleton inode继续服务其他anonymous files。

release返回后__fput继续做什么
----------------------------

``eventfd_release`` 返回后， ``__fput`` 继续固定顺序：

::

   fops_put(F->f_op)
   file_f_owner_release(F)
   put_file_access(F)
   dput(F->f_path.dentry)
   mntput(F->f_path.mnt)
   file_free(F)

eventfd ctx已经释放，后续步骤只处理通用VFS与file对象状态。

fops_put为什么不会卸载一个eventfd模块
------------------------------------

``eventfd_fops`` 属于built-in ``fs/eventfd.c``，其 ``owner`` 不对应一个可卸载外部module。 ``fops_put`` 仍是通用 ``__fput`` 顺序的一部分，用于对可能存在的file_operations module reference执行配对下降。

固定结果没有module unload，也没有额外控制流。 ``F->f_op`` 在此步骤之后不应再被file teardown代码调用。

file owner与access引用为何没有额外工作
-------------------------------------

``file_f_owner_release`` 清理异步I/O信号owner关系。本场景从未设置 ``F_SETOWN``、 ``O_ASYNC`` 或FASYNC，因此没有task、pid或signal reference需要释放。

``put_file_access`` 处理 ``FMODE_READ``、 ``FMODE_WRITE`` 与inode access bookkeeping。eventfd file以 ``O_RDWR`` 打开，但它是复用singleton anon inode的pseudo file，不是普通磁盘文件：

* 不写inode size；
* 不提交dirty pages；
* 不触发writeback；
* 不执行ext4或其他磁盘filesystem callback。

这一步只完成VFS通用引用计数配对。

[eventfd] pseudo dentry怎样消失
------------------------------

创建eventfd时：

::

   anon_inode_getfile_fmode("[eventfd]", ...)
   → __anon_inode_getfile
   → ihold(anon_inode_inode)
   → alloc_file_pseudo
   → d_alloc_pseudo
   → d_instantiate

因此每个eventfd file拥有自己的pseudo dentry，但普通eventfd复用同一个全局anon inode。

``__fput`` 现在执行：

.. code-block:: c

   dput(F->f_path.dentry);

固定没有其他dentry reference，所以该 ``[eventfd]`` pseudo dentry失去最后活动引用。dcache将它从活动对象图中拆除，并下降它对singleton anon inode持有的reference。

需要区分：

::

   per-file [eventfd] pseudo dentry = ends here
   global anon_inode_inode          = remains alive

普通eventfd没有创建一个需要随close销毁的独立inode。 ``anon_inode_inode`` 在 ``anon_inode_init`` 中从 ``anon_inode_mnt->mnt_sb`` 分配，并保存在全局只读指针中。它还要继续被eventpoll、signalfd、timerfd及其他anonymous file类型复用。

因此不能写成“close eventfd释放了anon inode”。准确结果是：

* 本file的pseudo dentry消失；
* 本dentry持有的singleton inode reference下降；
* singleton inode与anon_inodefs superblock继续存在。

mntput为什么不会卸载anon_inodefs
-------------------------------

``alloc_file_pseudo`` 在创建path时执行：

::

   path->mnt = mntget(anon_inode_mnt)

每个pseudo file因此持有一个mount reference。最终 ``__fput`` 调用：

.. code-block:: c

   mntput(F->f_path.mnt);

这只归还eventfd file ``F`` 的per-file reference。全局：

::

   anon_inode_mnt

由 ``anon_inode_init`` 通过 ``kern_mount(&anon_inode_fs_type)`` 建立并长期保留。本次 ``mntput`` 不会卸载整个anon_inodefs，也不会执行 ``kill_anon_super``。

固定结果：

::

   F per-file mount ref = dropped
   global anon_inode_mnt = remains mounted

这与anonymous pipe上一条主线中的 ``pipe_mnt`` 边界类似：最后一个用户file reference不等于内核全局pseudo filesystem被卸载。

file_free结束哪个对象的生命周期
-------------------------------

path references处理完后， ``__fput`` 到达：

.. code-block:: c

   file_free(F);

``struct file F`` 从此退出活动对象图。以下字段不能再访问：

* ``F->f_op``；
* ``F->private_data``；
* ``F->f_path``；
* ``F->f_flags`` 与 ``F->f_mode``；
* file reference state；
* file owner与mapping pointers。

filp slab何时复用这块memory属于allocator/RCU实现细节。用户可观察的lifetime边界已经明确： ``file_free`` 返回后，不存在任何合法引用可以继续操作旧 ``F``。

fput_close_sync怎样回到close syscall
----------------------------------

``__fput(F)`` 返回后：

::

   fput_close_sync(F) returns
   → __x64_sys_close continues

第一百三十一章已经固定：

::

   filp_flush retval = 0

close因此执行：

.. code-block:: c

   if (likely(retval == 0))
       return 0;

release callback的返回值没有参与这个判断。随后：

::

   do_syscall_64
   → syscall exit work
   → exit_to_user_mode
   → SYSRET/IRET-compatible return path
   → parent CPL 3

固定没有signal、reschedule、ptrace、seccomp或user-return work，因此最终用户寄存器：

::

   RAX = 0
   RIP = instruction after close syscall

fd数字6之后意味着什么
---------------------

close返回时，数字6只是当前fdtable中的空slot：

* 立即再次 ``read(6, ...)`` 会得到 ``-EBADF``，前提是期间没有新fd复用6；
* 新的open、eventfd、epoll或timerfd创建可能重新分配fd 6；
* 若fd 6被复用，新对象与旧eventfd没有任何identity或lifetime关系；
* 用户态保存的旧整数6不是对象reference。

这也是fd与内核对象之间最重要的边界：fd只是某个 ``files_struct`` 中可复用的索引。

为什么整个close没有磁盘I/O
--------------------------

本场景经过VFS通用 ``struct file`` 与path teardown，但anonymous inode不对应磁盘目录项：

* 没有ext4/xfs/btrfs inode；
* 没有page cache data；
* 没有dirty folio；
* 没有journal transaction；
* 没有bio、request、SCSI或AHCI command；
* 没有filesystem writeback。

``dput``、 ``mntput`` 与 ``file_free`` 处理内存对象及引用计数。它们不是“写回一个eventfd文件”。

完整对象释放顺序
----------------

本批三个章节的顺序可以压缩为：

::

   parent close(6)
   → file_close_fd
   → fdtable[6] = NULL
   → clear open/cloexec bookkeeping
   → filp_flush = 0
   → fput_close_sync
   → final __fput(F)
   → eventpoll_release(F), no links
   → eventfd_release
   → wake_up_poll(EPOLLHUP), empty queue
   → eventfd_ctx_put
   → E kref 1 → 0
   → ida_free(E->id)
   → kfree(E)
   → fops_put / owner / access cleanup
   → dput([eventfd] pseudo dentry)
   → drop per-file singleton-inode ref
   → mntput(per-file anon_inode_mnt ref)
   → file_free(F)
   → close returns 0

对象不是同时消失的。精确lifetime次序是：

::

   fd publication
   → eventfd private ctx
   → pseudo dentry/path references
   → struct file
   → userspace syscall frame

全局anon_inodefs设施不在这条释放链中结束。

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
* shared fd 6：closed and currently unallocated；
* close-on-exec bit 6：cleared；
* eventfd file ``F``：freed；
* eventfd ctx ``E``：freed；
* eventfd internal id：returned to ``eventfd_ida``；
* eventfd counter/wait queue：对象已不存在；
* ``[eventfd]`` pseudo dentry：已失去最后活动引用；
* singleton ``anon_inode_inode``：仍active；
* global ``anon_inode_mnt``：仍mounted；
* per-file anon-inode mount reference：released；
* helper：仍阻塞在eventfd之外；
* shared ``files_struct``：仍active，fd 0..5保持原状；
* task_work/delayed_fput：未使用；
* filesystem/block I/O：none；
* next runtime scenario：unselected。

关键边界
--------

#. eventfd ctx可以在 ``struct file`` 与path之前释放。
#. 普通eventfd复用singleton anonymous inode，不拥有独立inode。
#. ``dput`` 结束per-file pseudo dentry并下降singleton inode reference。
#. singleton ``anon_inode_inode`` 在eventfd close后继续存在。
#. ``mntput`` 只归还per-file mount reference，不卸载全局anon_inodefs。
#. ``file_free`` 结束 ``struct file`` 的合法访问生命周期。
#. close result来自 ``filp_flush``，不是 ``release`` callback返回值。
#. ``fput_close_sync`` 保证全部teardown在用户态close返回前完成。
#. fd 6是可复用索引，不是eventfd对象identity。
#. anonymous inode teardown不产生磁盘filesystem或block I/O。

下一任务
--------

当前没有已选定场景。优先候选是用epoll真正观察eventfd wake：

::

   eventfd2(0, EFD_CLOEXEC) → fd 6
   epoll_create1(EPOLL_CLOEXEC) → fd 7
   epoll_ctl(7, EPOLL_CTL_ADD, 6, EPOLLIN)
   → eventpoll item attaches callback to eventfd wait queue
   parent epoll_wait(7, events, 1, -1)
   → parent blocks on eventpoll wait queue
   helper write(6, u64 5)
   → eventfd EPOLLIN callback marks item ready
   → wake parent
   → epoll_wait copies one event to userspace

开始前必须固定event mask、edge/level-trigger mode、event data、epoll nesting、exclusive flag、fd references、wait queue callback顺序与scheduler顺序。

资料
----

* `Linux 7.2-rc1 fs/file_table.c：__fput后半段、dput、mntput与file_free <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 fs/anon_inodes.c：singleton anon inode、pseudo file与global mount <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/anon_inodes.c>`_
* `Linux 7.2-rc1 fs/open.c：close返回值与同步fput <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 fs/eventfd.c：eventfd file与ctx teardown入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/eventfd.c>`_
