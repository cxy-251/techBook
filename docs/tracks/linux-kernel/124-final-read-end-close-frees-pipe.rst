第一百二十四章：最后一次 close(6) 怎样释放pipe page、ring与pseudo inode？
================================================================================

上一章结束时，parent已经从空且没有writer的pipe读到EOF：

::

   read(6, eofbuf, 5) = 0

read endpoint仍保持打开：

::

   fd 6          = open read end
   readers       = 1
   writers       = 0
   files         = 1
   head          = 1
   tail          = 1
   occupancy     = 0
   tmp_page[0]   = Q

parent现在执行：

.. code-block:: c

   close(6);

固定条件：

* fd 6是read-side ``struct file`` 的唯一剩余引用；
* 没有dup、SCM_RIGHTS、epoll、io_uring、splice或正在进行的read；
* fd 7已经关闭，write-side file已经销毁；
* pipe wait queues没有waiter；
* ring中没有active ``pipe_buffer``；
* page Q只由 ``pipe->tmp_page[0]`` 缓存；
* close、VFS与allocator路径都不失败。

本章结束在fd 6、read-side file、``pipe_inode_info``、ring、page Q、pseudo dentry和pseudo inode均不再属于活动pipe对象；parent返回用户态并得到close result 0。

fd 6 怎样先从共享fdtable消失
---------------------------

native x86-64路径再次进入：

::

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_close(6)
   → file_close_fd(6)

``file_close_fd_locked()`` 在 ``files->file_lock`` 下执行：

::

   read_file = fdt->fd[6]
   fdt->fd[6] = NULL
   clear fd 6 open bookkeeping
   update files->next_fd

锁释放后，fd 6已经无法由parent或helper再次解析。read-side file尚未销毁，因为close syscall持有刚从fdtable取出的最后file引用。

与write end一样，close随后执行：

::

   filp_flush(read_file, current->files)
   → fput_close_sync(read_file)

pipe没有flush callback，固定retval为0。``fput_close_sync()`` 发现这是read-side file的最后引用，立即调用 ``__fput()``。

最后一个 pipe_release 做了什么
-----------------------------

``__fput()`` 调用：

::

   pipeanon_fops.release
   → pipe_release(inode, read_file)

``pipe_release()`` 获取 ``pipe->mutex``。read-side file包含 ``FMODE_READ``，因此：

::

   pipe->readers: 1 → 0
   pipe->writers: 保持 0

endpoint计数现在是：

::

   readers = 0
   writers = 0

partner-wakeup条件是：

.. code-block:: c

   !pipe->readers != !pipe->writers

当前两侧都为0：

::

   true != true  → false

所以最后一个endpoint关闭时，不需要再次执行“仅一侧消失”的partner wake。固定wait queue本来也没有waiter。

``pipe_release()`` 随后释放 ``pipe->mutex`` 并调用：

::

   put_pipe_info(inode, pipe)

files 从 1 变成 0 是最终释放边界
--------------------------------

``put_pipe_info()`` 在 ``inode->i_lock`` 下执行：

::

   pipe->files: 1 → 0
   inode->i_pipe = NULL
   kill = 1

这是pipe object真正失去最后一个endpoint file引用的边界。

``readers==0 && writers==0`` 只描述endpoint计数；触发 ``free_pipe_info()`` 的直接条件是：

::

   pipe->files == 0

两者在本固定场景同时成立，但它们表达不同对象层次：

* ``readers/writers`` 决定I/O语义与partner notification；
* ``files`` 决定共享 ``pipe_inode_info`` 是否仍被file objects引用。

page Q 为什么在这里才归还allocator
---------------------------------

``free_pipe_info(pipe)`` 首先撤销创建pipe时登记的user pipe-page accounting。默认ring有16个slot，因此对应的accounted page quota也在这里归还。

随后它扫描16个ring slot：

.. code-block:: c

   for each pipe_buffer:
       if (buf->ops)
           pipe_buf_release(pipe, buf)

上一章消费最后5字节时，``pipe_buf_release()`` 已先把slot的 ``buf->ops`` 设置为NULL，再把page Q缓存到 ``tmp_page[0]``。所以当前ring没有active buffer需要再次release，也不会对Q重复put。

接着 ``free_pipe_info()`` 扫描：

::

   pipe->tmp_page[0]
   pipe->tmp_page[1]

固定结果：

::

   tmp_page[0] = Q
   tmp_page[1] = NULL

因此执行：

.. code-block:: c

   __free_page(Q);

page Q现在归还page allocator。之前把Q放进 ``tmp_page[]`` 是pipe内部的热page缓存；只有整个pipe对象结束时，这个缓存才必须释放。

ring与pipe_inode_info怎样消失
----------------------------

page处理完成后，``free_pipe_info()`` 执行：

::

   kfree(pipe->bufs)
   kfree(pipe)

由此释放：

* 16个 ``struct pipe_buffer`` 组成的ring array；
* ``rd_wait`` 与 ``wr_wait`` 所在的 ``pipe_inode_info`` memory；
* pipe mutex、head/tail、endpoint counters等全部pipe私有状态。

从这一刻起，不能再读取 ``pipe->head``、``pipe->files`` 或 ``tmp_page``；相关memory已经结束生命周期。

pseudo dentry与inode为什么稍后才释放
-----------------------------------

``pipe_release()`` 返回后，``__fput()`` 仍持有read file中保存的path：

::

   file->f_path.dentry
   file->f_path.mnt

它继续执行：

::

   dput(pseudo_dentry)
   mntput(pipe_mnt reference)
   file_free(read_file)

固定场景没有其他file或外部path reference，因此该 ``dput`` 是anonymous pipe pseudo dentry的最后活动引用。VFS将dentry从inode与dentry tree关系中拆除，并向inode执行最后引用下降。

pipefs pseudo inode不是磁盘inode：

* 没有ext4 inode table更新；
* 没有journal transaction；
* 没有writeback；
* 没有block I/O。

inode与dentry退出活动对象图后，其slab memory释放可以按VFS/RCU规则延后；这不改变用户可观察结果：close返回前，pipe endpoint、pipe private state和file object已经全部不可访问。

``mntput`` 只下降这个file持有的pipefs mount引用。全局 ``pipe_mnt`` 仍由内核运行期pipefs设施持有，本次close不会卸载整个pipefs。

close(6) 怎样返回
-----------------

同步 ``__fput()`` 全部完成后，``fput_close_sync()`` 返回。固定 ``filp_flush`` result为0，所以：

::

   __x64_sys_close returns 0
   → exit_to_user_mode
   → parent CPL 3, RAX=0

此时再次使用fd 6或fd 7都会因为fdtable slot为空而得到 ``-EBADF``。内核不会保留一个“EOF pipe”供后续访问；EOF read与endpoint close是两个独立步骤，最终close已经结束pipe生命周期。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* close result/RAX：0；
* shared fd 6：closed；
* shared fd 7：closed；
* read-side ``struct file``：released；
* write-side ``struct file``：此前已经released；
* ``pipe_inode_info``：freed；
* 16-slot ring：freed；
* page Q：已通过 ``__free_page`` 归还allocator；
* pseudo dentry：已失去最后活动引用并进入VFS释放流程；
* pseudo inode：不再可达并进入inode释放流程；
* per-file pipefs mount refs：已下降；
* global pipefs mount：仍存在；
* pipe wait queues/mutex/counters：对象已不存在，不能继续访问；
* filesystem/block I/O：未发生；
* next runtime scenario：unselected。

关键边界
--------

#. fdtable撤销、file refcount下降、 ``pipe_release`` 和pipe memory释放是连续但不同的边界。
#. 用户态close的 ``fput_close_sync`` 保证最后 ``__fput`` 在syscall返回前执行。
#. ``readers/writers`` 管理pipe I/O语义，``files`` 管理 ``pipe_inode_info`` lifetime。
#. 最后一个endpoint使 ``files`` 从1降到0，才调用 ``free_pipe_info``。
#. 已消费pipe buffer的 ``buf->ops`` 已清空，避免final free重复release同一page。
#. ``tmp_page`` 是pipe私有page缓存；pipe销毁时Q才真正归还allocator。
#. anonymous pipe teardown不涉及磁盘filesystem、journal或block device。
#. pseudo dentry/inode memory可能按RCU规则延后回收，但用户已无法再引用它们。
#. 最后file的 ``mntput`` 不等于卸载全局pipefs。

下一任务
--------

当前没有已选定场景。优先候选是private futex的阻塞与唤醒：

::

   user word = 0
   parent futex(FUTEX_WAIT_PRIVATE, expected=0)
   → key construction and hash-bucket enqueue
   → parent TASK_INTERRUPTIBLE and schedule out
   → helper stores user word = 1
   → futex(FUTEX_WAKE_PRIVATE, 1)
   → remove waiter and wake parent
   → parent returns 0 after rechecking userspace state

开始前必须固定用户地址映射、atomic store顺序、futex flags、hash bucket、signal状态与scheduler顺序。

资料
----

* `Linux 7.2-rc1 fs/open.c：close syscall与同步fput <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 fs/file.c：最后fdtable slot撤销 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file.c>`_
* `Linux 7.2-rc1 fs/file_table.c：__fput release、dput、mntput与file_free顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 fs/pipe.c：pipe_release、put_pipe_info与free_pipe_info <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/pipe.c>`_
* `Linux 7.2-rc1 include/linux/pipe_fs_i.h：pipe_buf_release清空ops <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/pipe_fs_i.h>`_
* `Linux 7.2-rc1 fs/dcache.c：dput后的dentry eviction与inode unlink <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/dcache.c>`_
