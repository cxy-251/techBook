第一百零八章：fsync() 怎样让 writeback 分配第一个 unwritten extent 并提交数据？
==========================================================================================

第一百零七章结束时，fd 6的4-KiB数据只存在于dirty page-cache folio中：

.. code-block:: text

   i_size                    = 4096
   i_disksize                = 0
   delayed logical extent    = [0,1)
   i_reserved_data_blocks    = 1
   physical block            = none

parent现在调用：

.. code-block:: c

   fsync(6);

固定allocator从空闲空间中选择一个4-KiB physical block ``P``。``P`` 的具体数字不影响控制流，但它位于 ``/dev/sda1`` 合法范围内，相关block bitmap、group descriptor与extent-tree metadata均已cache resident。

fsync怎样进入ext4
-----------------

native x86-64控制流是：

.. code-block:: text

   entry_SYSCALL_64
   → __x64_sys_fsync
   → do_fsync
   → vfs_fsync
   → vfs_fsync_range
   → file->f_op->fsync
   → ext4_sync_file

``fsync`` 不使用或改变 ``file->f_pos``。当前fd 6仍指向同一个write-only ``struct file``。

为什么先执行 ``file_write_and_wait_range``
------------------------------------------

有journal的ext4在提交metadata前先调用：

.. code-block:: c

   file_write_and_wait_range(file, 0, LLONG_MAX);

该helper先发起mapping writeback，再等待指定range中的writeback结束。发起阶段最终进入：

.. code-block:: text

   filemap_fdatawrite_range
   → do_writepages
   → mapping->a_ops->writepages
   → ext4_writepages
   → ext4_do_writepages

因为这是fsync路径，``writeback_control.sync_mode`` 是 ``WB_SYNC_ALL``。它要求等待目标数据完成，并使后续ext4 data bio带 ``REQ_SYNC``。

writeback怎样发现delayed buffer
-------------------------------

``ext4_do_writepages()`` 初始化 ``mpage_da_data``，然后：

.. code-block:: text

   mpage_prepare_extent_to_map
   → lock dirty folio index 0
   → folio_wait_writeback
   → mpage_process_page_bufs
   → collect logical block 0 with BH_Delay

收集结果是：

.. code-block:: text

   mpd.map.m_lblk  = 0
   mpd.map.m_len   = 1
   mpd.map.m_flags = delayed

folio仍locked，writeback尚未提交。

为什么writeback此时必须启动JBD2 transaction
------------------------------------------

把delayed state变成真实extent会修改：

* data block bitmap；
* block-group descriptor；
* inode extent tree；
* inode ``i_blocks`` 与 ``i_disksize``；
* extent-status tree与reservation accounting。

因此 ``ext4_do_writepages()`` 调用：

.. code-block:: text

   ext4_journal_start_with_reserve
   → transaction type EXT4_HT_WRITE_PAGE

随后：

.. code-block:: text

   mpage_map_and_submit_extent
   → mpage_map_one_extent
   → ext4_map_blocks

``ext4_map_blocks`` 收到的关键flags包括：

.. code-block:: text

   EXT4_GET_BLOCKS_CREATE
   EXT4_GET_BLOCKS_METADATA_NOFAIL
   EXT4_GET_BLOCKS_IO_SUBMIT
   EXT4_EX_NOCACHE
   EXT4_GET_BLOCKS_UNWRIT_EXT

最后一个flag来自固定的 ``dioread_nolock`` mount mode。

reservation怎样变成physical block
---------------------------------

``ext4_map_blocks()`` 先从extent-status tree看到delayed extent，再进入：

.. code-block:: text

   ext4_map_create_blocks
   → ext4_ext_map_blocks
   → ext4 multi-block allocator
   → allocate physical block P

本场景只需要一个block，因此建立：

.. code-block:: text

   logical block 0
   → physical block P
   → length 1
   → state unwritten

同时更新block bitmap、group descriptor与inode extent metadata，并消费delalloc reservation：

.. code-block:: text

   i_reserved_data_blocks: 1 → 0
   s_dirtyclusters_counter:  -1
   quota reservation:        claimed/released as configured
   inode i_blocks:           0 → 8 sectors

为什么先创建unwritten extent
----------------------------

unwritten extent已经占有physical blocks，但read语义仍返回zero。即使metadata先被观察到，也不会暴露磁盘上旧内容。

``dioread_nolock`` writeback选择该状态，使真正data I/O完成前extent不会成为written。与普通ordered-data list相比，这里依赖的是：

.. code-block:: text

   allocate as unwritten
   → submit data
   → only after successful completion convert to written

因此 ``ext4_map_blocks()`` 不把这个新unwritten mapping当作已经可见的initialized data。

buffer怎样取得真实block number
------------------------------

``mpage_map_and_submit_buffers()`` 扫描folio buffer：

.. code-block:: text

   clear BH_Delay
   → bh->b_blocknr = P
   → io_end记录offset=0, size=4096
   → io_end设置EXT4_IO_END_UNWRITTEN

buffer现在知道DMA目标block，但on-disk extent仍是unwritten。unwritten状态由extent tree和 ``ext4_io_end`` 共同保护，不能只看buffer bit判断完成。

数据bio怎样构造
---------------

``mpage_submit_folio()`` 先执行：

.. code-block:: text

   folio_clear_dirty_for_io
   → folio进入writeback保护
   → ext4_bio_write_folio

``ext4_bio_write_folio()`` 为physical block ``P`` 建立：

.. code-block:: text

   bio operation = REQ_OP_WRITE
   length        = 4096
   source        = page-cache folio index 0
   bi_sector     = P换算出的partition-relative sector
   bi_end_io     = ext4_end_bio
   bi_private    = ext4_io_end

``ext4_io_submit()`` 看到 ``WB_SYNC_ALL``，添加 ``REQ_SYNC``，然后调用：

.. code-block:: c

   blk_crypto_submit_bio(bio);

本场景没有fscrypt bio context，因此进入普通block submission。

数据怎样到达AHCI
----------------

已固定的下层路径是：

.. code-block:: text

   submit_bio
   → submit_bio_noacct
   → partition remap (+2048 sectors)
   → blk_mq_submit_bio
   → struct request / tag
   → scsi_queue_rq
   → sd_setup_read_write_cmnd
   → SCSI WRITE(10)或WRITE(16)
   → ata_scsi_queuecmd
   → ata_scsi_rw_xlat
   → ATA DMA WRITE / WRITE DMA EXT / WRITE FPDMA QUEUED
   → ahci_qc_prep
   → DMA map page-cache folio
   → write command header + PRDT
   → write PxCI[tag]

4096 bytes对应8个512-byte sectors。具体ATA opcode由QEMU disk暴露的IDENTIFY与NCQ状态决定，但所有成功分支都提交同一个physical data range。

``i_disksize`` 何时推进
----------------------

数据bio提交后，``mpage_map_and_submit_extent()`` 在 ``i_data_sem`` 下把：

.. code-block:: text

   i_disksize: 0 → 4096

并通过当前JBD2 handle标记inode dirty。此时extent仍是unwritten，因此 ``i_disksize=4096`` 不表示用户数据已经可读或持久化；它表示on-disk mapping已经覆盖该长度且不会暴露未初始化内容。

fsync task现在等待什么
----------------------

``file_write_and_wait_range()`` 的wait阶段等待folio writeback结束。由于io_end带unwritten conversion工作，folio不会在data DMA刚结束时立刻被视为完整结束；conversion必须先成功。

当前精确边界
------------

* current task：parent，位于CPL 0的 ``fsync`` syscall中；
* fd 6 ``f_pos``：仍为4096；
* inode ``i_size``：4096；
* ext4 ``i_disksize``：4096；
* logical block 0：映射到physical block ``P``；
* extent state：unwritten；
* ``i_reserved_data_blocks``：0；
* folio：clean-for-I/O、uptodate、under writeback；
* data bio：已提交，带 ``REQ_SYNC``；
* lower request：正在设备路径中或等待completion；
* metadata：block allocation与unwritten extent变更已加入JBD2 transaction；
* extent conversion：尚未完成；
* ``file_write_and_wait_range``：尚未返回；
* ``ext4_fsync_journal``：尚未执行；
* ``fsync``：尚未返回用户态。

关键边界
--------

#. fsync先写并等待file data，再等待journal metadata commit。
#. delayed reservation在writeback时才转换成block bitmap中的真实allocation。
#. ``dioread_nolock`` 路径先建立unwritten extent，data成功后再转换。
#. ``i_disksize`` 推进不等于extent已经written。
#. ``REQ_SYNC`` 不等于FUA，也不单独保证device cache已flush。
#. fsync等待的不只是DMA completion，还包括影响数据可见性的extent conversion。

资料
----

* `Linux 7.2-rc1 fs/ext4/fsync.c：ext4_sync_file <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/fsync.c>`_
* `Linux 7.2-rc1 fs/ext4/inode.c：ext4_writepages、mpage_map_and_submit_extent与ext4_map_blocks <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/inode.c>`_
* `Linux 7.2-rc1 fs/ext4/page-io.c：ext4_bio_write_folio与ext4_io_submit <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/page-io.c>`_
