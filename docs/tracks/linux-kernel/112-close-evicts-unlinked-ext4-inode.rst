第一百一十二章：close(6) 怎样触发最后一次 __fput() 并回收 ext4 inode？
================================================================================

第一百一十一章结束时，pathname已经消失，但parent仍持有：

.. code-block:: text

   fd 6
   → struct file
   → unhashed dentry
   → ext4 inode: nlink=0, size=4096
   → written extent: logical 0 → physical P

本章固定parent随后执行：

.. code-block:: c

   close(6);

固定条件：

* fd 6是该 ``struct file`` 的最后一个file reference；
* 没有dup、SCM_RIGHTS、io_uring fixed file、mmap或其他task引用；
* target inode没有其他dentry、open file、export handle或kernel reference；
* page-cache folio clean，data writeback与extent conversion均已完成；
* 没有delalloc reservation、preallocation、xattr、ACL、quota或project quota；
* orphan tracking仍active；
* filesystem为 ``data=ordered,barrier``，fast commit关闭；
* block/inode bitmap、group descriptor、inode table与extent metadata已缓存；
* 当前不触发background JBD2 commit；
* 不发生flush callback error、journal error、I/O error或allocation failure。

fd slot 为什么先消失
--------------------

native x86-64 ``close`` 进入：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_close

``SYSCALL_DEFINE1(close)`` 首先执行：

.. code-block:: c

   file = file_close_fd(6);

``file_close_fd`` 在 ``files_struct`` 的fdtable保护下：

.. code-block:: text

   fd[6] = NULL
   open_fds bit 6 = clear
   close_on_exec bit 6 = clear

并把原 ``struct file *`` 返回给close路径。

从这个publication boundary开始，其他fd lookup已经无法再通过数字6取得该file；fd 6也可以被后续open重新分配。file对象本身尚未释放，因为close syscall持有刚从table中取出的reference。

``filp_flush`` 是否会写回文件
----------------------------

close随后调用：

.. code-block:: c

   filp_flush(file, current->files);

普通ext4 regular file没有 ``file_operations.flush`` callback，因此这里主要清理：

.. code-block:: text

   dnotify state
   POSIX locks owned by current files_struct

它不会因为close自动执行 ``fsync``，也不会重新写出已经clean的data folio。

为什么本次是同步 ``__fput``
--------------------------

系统调用close即将返回userspace，源码调用：

.. code-block:: c

   fput_close_sync(file);

固定这是最后一个file reference，``file_ref_put_close()`` 返回true，立即进入：

.. code-block:: c

   __fput(file);

这与普通 ``fput()`` 可能安排task_work或delayed work不同。本场景的file release、dentry drop与由此触发的inode eviction都在当前parent的close syscall context中完成。

``__fput`` 按什么顺序拆 open file description
---------------------------------------------

``__fput()`` 保存：

.. code-block:: text

   dentry = file->f_path.dentry
   mnt    = file->f_path.mnt
   inode  = file->f_inode

随后依次执行：

.. code-block:: text

   fsnotify_close
   → eventpoll_release
   → locks_remove_file
   → security_file_release
   → file->f_op->release
   → fops_put
   → file_f_owner_release
   → put_file_access
   → dput(dentry)
   → mntput(mnt)
   → file_free

对固定ext4 file，``file->f_op->release`` 是：

.. code-block:: c

   ext4_release_file(inode, file);

它看到没有 ``EXT4_STATE_DA_ALLOC_CLOSE``、没有reserved delalloc blocks，也没有preallocation，只完成last-writer检查，不产生data I/O。

``put_file_access`` 与 ``dput`` 各释放什么
------------------------------------------

``put_file_access(file)`` 撤销write-open取得的inode write access，并把 ``i_writecount`` 从1降到0。

随后 ``dput(dentry)`` 释放open file对unhashed dentry的最后reference。固定没有其他dentry user，因此dcache销毁该dentry并释放它持有的inode reference，最终进入最后一次：

.. code-block:: text

   iput(inode)
   → evict(inode)
   → sb->s_op->evict_inode
   → ext4_evict_inode(inode)

这里才是“unlink后仍open”的inode真正进入删除路径的时刻。

``ext4_evict_inode`` 为什么先丢page cache
----------------------------------------

函数确认：

.. code-block:: text

   inode->i_nlink == 0

于是选择delete分支。``ext4_begin_ordered_truncate(inode, 0)`` 与ordered-data tracking协调；固定data早已完成fsync，没有outstanding write range。

接着：

.. code-block:: c

   truncate_inode_pages_final(&inode->i_data);

page-cache index 0 folio是clean、not under writeback，所以直接从mapping移除并释放folio引用，不提交WRITE bio。

final truncate transaction包含什么
----------------------------------

ext4取得freeze protection并建立：

.. code-block:: c

   ext4_journal_start(inode, EXT4_HT_TRUNCATE,
                      ext4_blocks_for_truncate(inode)
                      + extra_credits - 3);

transaction需要覆盖：

* inode record；
* extent metadata；
* physical block P对应的block bitmap；
* block-group descriptor/free-block counters；
* orphan tracking metadata；
* inode bitmap；
* free-inode counters与inode-table deletion time。

随后先设置：

.. code-block:: text

   inode->i_size = 0
   mark inode dirty

因为 ``inode->i_blocks != 0``，进入：

.. code-block:: text

   ext4_truncate(inode)
   → extent truncate path
   → ext4_ext_remove_space(...)
   → remove logical extent [0,1)
   → ext4_free_blocks(... physical P ...)

结果是：

.. code-block:: text

   extent tree     = empty
   i_blocks        = 0
   i_disksize      = 0
   physical P      = pending free in current JBD2 transaction

“pending free”很重要：extent mapping已经从该inode移除，block-free metadata也已journaled；ext4仍要防止P在释放transaction commit前被不安全地重新分配，避免crash后旧metadata重新指向已复用的数据块。

orphan 为什么在释放block后删除
------------------------------

只要truncate未完成，nlink-zero inode必须保持orphan状态，mount recovery才能继续清理。全部extent与xattr释放成功后才执行：

.. code-block:: c

   ext4_orphan_del(handle, inode);

随后设置：

.. code-block:: text

   i_dtime = current real seconds

并再次把最终inode record加入transaction。

inode bitmap何时清除
--------------------

最终：

.. code-block:: c

   ext4_free_inode(handle, inode);

它定位target inode所在block group，在journal保护下：

.. code-block:: text

   clear inode bitmap bit
   → update free-inode counter
   → update group descriptor checksum
   → update superblock/percpu free-inode accounting
   → mark bitmap and descriptor metadata dirty

此后该inode number在当前运行内核中已进入free状态，但与physical block P一样，安全持久化与重新使用仍受当前JBD2 transaction commit约束。

VFS inode对象何时真正消失
-------------------------

``ext4_evict_inode()`` 完成filesystem-specific清理并执行 ``ext4_clear_inode()``。generic inode eviction随后把inode从hash/LRU等结构中移除，并通过filesystem inode allocator的RCU/slab释放机制最终回收 ``struct ext4_inode_info`` 内存。

因此需要区分：

.. code-block:: text

   inode在VFS/filesystem中不再可访问 = close路径内完成
   inode slab字节最终被重用          = 可以经过RCU延迟

同理，``file_free()`` 使 ``struct file`` 不再可用，实际allocator重用也不构成userspace可观察的close语义。

close为什么不等于删除已持久化
-----------------------------

``ext4_journal_stop(handle)`` 结束truncate handle，但固定inode没有 ``S_SYNC``，调用方也没有执行directory ``fsync``、``syncfs`` 或block-device flush。因此 ``close(6)`` 返回0时：

.. code-block:: text

   pathname inaccessible             = yes
   fd inaccessible                   = yes
   inode/extent removed in running FS= yes
   deletion transaction committed    = not guaranteed
   journal commit stable             = not guaranteed
   block/inode bitmap home checkpoint= not guaranteed

后续background JBD2 commit会把删除、block free、orphan removal和inode free作为一致的metadata状态推进到stable storage。

当前精确状态
------------

parent从close syscall返回CPL 3，``RAX=0``：

* fd 6：free，可被复用；
* ``struct file``：final ``__fput`` 已完成，不再可访问；
* pathname ``/work/demo.txt``：不存在；
* target dentry：已释放；
* target inode：已完成ext4 eviction，不再位于可访问inode状态；
* ``i_nlink``：删除前已为0；
* page-cache folio：已从mapping移除；
* extent logical [0,1)：已删除；
* physical block P：已加入当前transaction的free处理，等待commit安全完成；
* inode bitmap bit：已在journaled metadata中清除；
* orphan tracking：已删除；
* target inode number：等待transaction commit后安全复用；
* unlink/truncate/free metadata：位于JBD2 transaction；
* forced journal commit：未发生；
* forced device flush：未发生；
* fixed syscall-path storage I/O：未发生；
* file lifecycle scenario：complete；
* next runtime scenario：unselected。

关键边界
--------

#. ``file_close_fd`` 先撤销fd publication，file teardown随后进行。
#. close普通文件不隐含fsync。
#. ``fput_close_sync`` 在最后reference时同步执行 ``__fput``。
#. ``ext4_release_file`` 与 ``ext4_evict_inode`` 是两个不同阶段。
#. final dput/iput把open-unlinked inode送入eviction。
#. clean folio删除不需要data I/O。
#. extent removal、block free、orphan removal和inode free位于journal transaction中。
#. physical block和inode number在transaction commit前不能视为已安全复用。
#. VFS对象不可访问与slab内存最终重用不是同一时刻。
#. ``close(6)=0`` 不保证删除事务已经durable。

资料
----

* `Linux 7.2-rc1 fs/open.c：close、file_close_fd、filp_flush与fput_close_sync <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/open.c>`_
* `Linux 7.2-rc1 fs/file_table.c：__fput、dput、mntput与file_free <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/file_table.c>`_
* `Linux 7.2-rc1 fs/ext4/file.c：ext4_release_file <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/file.c>`_
* `Linux 7.2-rc1 fs/ext4/inode.c：ext4_evict_inode与ext4_truncate <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/inode.c>`_
* `Linux 7.2-rc1 fs/ext4/extents.c：extent remove与physical block free <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/extents.c>`_
* `Linux 7.2-rc1 fs/ext4/ialloc.c：ext4_free_inode与inode bitmap更新 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/ialloc.c>`_
