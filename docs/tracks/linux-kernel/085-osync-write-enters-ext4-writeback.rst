第八十五章：O_SYNC write 怎样进入 ext4 writeback？
====================================================

第八十四章结束时，用户数据已经复制到 page-cache folio，folio 处于 dirty、uptodate、unlocked 状态，``kiocb->ki_pos`` 已推进到 4096。普通 buffered write 此时可以较快返回，让 background writeback 稍后处理磁盘 I/O。

固定文件以 ``O_SYNC`` 打开，所以本次系统调用不能在这里只报告成功。本章追踪 ``generic_write_sync()`` 怎样把本次 byte range 交给 ext4 ``fsync``，再通过 ``file_write_and_wait_range()`` 启动 ``WB_SYNC_ALL`` writeback，停在 ``ext4_writepages()`` 取得控制权的位置。

``generic_write_sync`` 怎样计算同步范围
--------------------------------------

``ext4_buffered_write_iter()`` 调用：

.. code-block:: c

   generic_write_sync(iocb, 4096);

此时：

.. code-block:: text

   iocb->ki_pos = 4096
   count        = 4096

``generic_write_sync()`` 因而计算 inclusive range：

.. code-block:: text

   start = iocb->ki_pos - count = 0
   end   = iocb->ki_pos - 1     = 4095

文件 open flags 中包含 ``O_SYNC``，``init_sync_kiocb()`` 已设置 ``IOCB_SYNC`` 和 ``IOCB_DSYNC``。因此函数调用：

.. code-block:: c

   vfs_fsync_range(file, 0, 4095, 0);

最后的 ``datasync = 0`` 很重要：

* ``O_DSYNC`` 只要求数据和访问这些数据所必需的 metadata；
* ``O_SYNC`` 要求普通 fsync 级别的同步语义。

本场景固定为 ``O_SYNC``，所以不走 datasync-only 分支。

``vfs_fsync_range`` 怎样进入 ext4
--------------------------------

VFS 先确认 file operations 提供 ``fsync`` callback。普通 ext4 regular file 的 callback 是：

.. code-block:: c

   ext4_sync_file(file, start, end, datasync)

``vfs_fsync_range()`` 在 ``datasync == 0`` 时还会处理 lazy-time inode state，然后调用 filesystem callback。它本身不遍历 dirty folio，也不构造 bio；这些工作由 ext4 与 page-cache writeback 完成。

为什么 ``ext4_sync_file`` 先同步 data range
------------------------------------------

固定 ext4 filesystem 启用了 journal。``ext4_sync_file()`` 排除只读、emergency state 和 no-journal 分支后，先执行：

.. code-block:: c

   file_write_and_wait_range(file, 0, 4095);

顺序必须是：

.. code-block:: text

   dirty file data writeback
   → wait for data I/O
   → commit required journal transaction
   → optional device cache flush

在 ``data=ordered`` 模式中，journal commit 不能先于相关 file data 达到规定的 writeout 顺序。直接跳到 JBD2 commit 会把“metadata 已提交”误写成“文件数据已经持久化”。

``file_write_and_wait_range`` 为什么既 write 又 wait
----------------------------------------------------

函数检查当前 mapping 是否需要 writeback。第八十四章已经建立：

.. code-block:: text

   PAGECACHE_TAG_DIRTY present
   target folio dirty

所以进入：

.. code-block:: c

   filemap_fdatawrite_range(mapping, 0, 4095);
   __filemap_fdatawait_range(mapping, 0, 4095);

第一步启动 writeback，第二步等待该范围内已经进入 writeback 的 folio 完成。两者不能合并成一句“刷盘”：

* fdatawrite 负责把 dirty state 转换为具体 filesystem writeback work；
* fdatawait 负责等待 ``PG_writeback`` 清除并收集错误。

本章只追踪到 writeback 被交给 ext4；等待与 storage completion 留给后续章节。

``filemap_fdatawrite_range`` 怎样构造 writeback_control
------------------------------------------------------

``filemap_fdatawrite_range()`` 调用内部 ``filemap_writeback()``，建立：

.. code-block:: c

   struct writeback_control wbc = {
       .sync_mode  = WB_SYNC_ALL,
       .nr_to_write= LONG_MAX,
       .range_start= 0,
       .range_end  = 4095,
   };

``WB_SYNC_ALL`` 表示 data-integrity writeback：不能仅做 opportunistic background flushing。调用者最终会等待该范围完成。

函数确认 mapping 支持 writeback 且仍带 dirty tag，然后把 ``wbc`` 附着到 inode/backing-device writeback context，执行：

.. code-block:: c

   do_writepages(mapping, &wbc);

``do_writepages`` 是 address-space writeback dispatcher。它根据：

.. code-block:: text

   mapping->a_ops->writepages

把控制权交给 filesystem。

为什么目标 callback 是 ``ext4_writepages``
-----------------------------------------

固定 inode 使用 ext4 delayed-allocation address-space operations，其 writeback callback 是：

.. code-block:: c

   ext4_writepages(mapping, wbc)

这是真正开始把 dirty page-cache state 转换为 ext4 block mapping、journal credits、writeback extent、bio 和 storage request 的入口。

进入 ``ext4_writepages()`` 前，系统只拥有：

* dirty folio；
* buffer/mapping state；
* ``writeback_control`` 描述的范围与同步要求；
* 已存在的 ext4 logical block mapping。

此刻还没有本次 WRITE 对应的 bio、blk-mq request、SCSI command、ATA taskfile 或 AHCI command slot。

O_SYNC task 为什么仍是当前执行者
-------------------------------

这一阶段仍在原 ``write()`` task 的 process context 中同步调用：

.. code-block:: text

   write syscall task
   → generic_write_sync
   → vfs_fsync_range
   → ext4_sync_file
   → file_write_and_wait_range
   → filemap_fdatawrite_range
   → do_writepages
   → ext4_writepages

它不是 background flusher thread。writeback framework 可以在其他场景由 ``wb_workfn`` 或 memory reclaim 触发，但固定 O_SYNC 路径由 syscall task 主动发起，并将在后续等待 I/O 和 journal durability。

``file->f_pos`` 为什么仍是 0
---------------------------

虽然 ``kiocb->ki_pos`` 已是 4096，但调用栈尚未从 ``ext4_file_write_iter()`` 返回到 ``new_sync_write()``：

.. code-block:: text

   ext4_file_write_iter
   └── ext4_buffered_write_iter
       └── generic_write_sync
           └── ext4_sync_file
               └── ext4_writepages  ← current

因此：

.. code-block:: text

   kiocb->ki_pos = 4096
   local pos     = 0
   file->f_pos   = 0

只有同步阶段成功返回后，``new_sync_write()`` 才把 ``kiocb->ki_pos`` 写入 local ``pos``，随后 ``ksys_write()`` 才提交 ``file->f_pos``。

当前精确边界
------------

控制流即将进入：

.. code-block:: c

   ext4_writepages(mapping, &wbc);

当前状态：

* 当前执行者：调用 ``write()`` 的 task；
* CPU mode：CPL 0，process context；
* sync policy：``WB_SYNC_ALL``；
* writeback range：file offset 0..4095；
* target folio：dirty、uptodate、unlocked；
* inode ``i_rwsem``：已释放；
* superblock freeze protection：仍 held；
* ``kiocb->ki_pos``：4096；
* local ``pos``：0；
* ``file->f_pos``：0；
* ext4 data mode：ordered；
* ext4 journal commit：尚未等待；
* folio ``PG_writeback``：尚未由本次 writepages 设置；
* WRITE bio：尚未建立；
* block/SCSI/ATA/AHCI objects：尚未建立；
* ``write()``：尚未返回。

关键边界
--------

#. ``O_SYNC`` buffered write 仍先修改 page cache，再执行同步范围 writeback。
#. ``generic_write_sync()`` 对 ``O_SYNC`` 使用 ``datasync = 0``。
#. ``vfs_fsync_range()`` 只是 filesystem callback 分派，不直接构造 bio。
#. ``file_write_and_wait_range()`` 的 write 与 wait 是两个不同阶段。
#. ``WB_SYNC_ALL`` 表示 data-integrity writeback，不表示 I/O 已完成。
#. ``do_writepages()`` 才根据 ``mapping->a_ops`` 进入 ext4 writeback。
#. 当前仍没有 WRITE bio；下一章才从 dirty folio 建立 ext4 writeback extent 与 block mapping。
#. 同步完成前，local ``pos`` 与共享 ``file->f_pos`` 仍未提交。

资料
----

* `Linux 7.2-rc1 include/linux/fs.h <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/fs.h>`_
* `Linux 7.2-rc1 fs/sync.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/sync.c>`_
* `Linux 7.2-rc1 fs/ext4/fsync.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/fsync.c>`_
* `Linux 7.2-rc1 mm/filemap.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
* `Linux 7.2-rc1 fs/ext4/inode.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/inode.c>`_
