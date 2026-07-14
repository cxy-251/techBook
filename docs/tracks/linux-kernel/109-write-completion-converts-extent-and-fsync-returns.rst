第一百零九章：data completion 怎样转换 extent，并让 fsync() 真正返回？
================================================================================

第一百零八章结束时，physical block ``P`` 已分配，data bio已提交，但extent仍是unwritten，parent仍阻塞在 ``file_write_and_wait_range()``。

本章固定所有data、metadata、journal与flush操作成功。journal fast commit关闭；固定JBD2 full commit本身没有覆盖最后所需的device-cache flush，因此 ``ext4_sync_file()`` 最终执行一次standalone ``blkdev_issue_flush()``。

AHCI completion怎样回到ext4
---------------------------

设备完成4-KiB write后，控制链沿已固定路径返回：

.. code-block:: text

   AHCI interrupt
   → ahci_port_intr
   → ata_qc_complete
   → ata_scsi_qc_complete
   → scsi_done
   → blk_mq_complete_request
   → bio_endio
   → ext4_end_bio

completion status为success，``bio->bi_status=0``。这只证明data command成功完成，不等于unwritten extent已经转换，也不等于journal commit durable。

为什么 ``ext4_end_bio`` 不立刻结束folio writeback
-------------------------------------------------

``bio->bi_private`` 指向 ``ext4_io_end``。它带：

.. code-block:: text

   EXT4_IO_END_UNWRITTEN
   io_end_vec: offset=0, size=4096

``ext4_end_bio()`` 判断conversion必须在可睡眠context执行，于是：

.. code-block:: text

   bio挂到io_end
   → ext4_put_io_end_defer
   → ext4_add_complete_io
   → 加入inode i_rsv_conversion_list
   → queue_work(rsv_conversion_wq)

此时data DMA已经结束，但 ``ext4_finish_bio()`` 尚未运行，因此folio仍保持writeback状态。这样fsync不会在extent仍unwritten时误认为file data阶段完成。

workqueue怎样把unwritten变成written
-----------------------------------

workqueue worker执行：

.. code-block:: text

   ext4_end_io_rsv_work
   → ext4_do_flush_completed_IO
   → ext4_end_io_end
   → ext4_convert_unwritten_io_end_vec

conversion为logical range ``[0,4096)`` 启动或使用reserved JBD2 handle，进入：

.. code-block:: text

   ext4_convert_unwritten_extents
   → ext4_map_blocks(... EXT4_GET_BLOCKS_CONVERT ...)
   → ext4_ext_handle_unwritten_extents
   → ext4_convert_unwritten_extents_endio
   → ext4_split_convert_extents
   → ext4_ext_mark_initialized
   → ext4_ext_dirty

当前extent正好是一个block，不需要拆成head/middle/tail。最终extent tree变为：

.. code-block:: text

   logical block 0
   → physical block P
   → length 1
   → written/initialized

extent-status tree也从UNWRITTEN更新为WRITTEN。conversion transaction更新inode fsync transaction id，确保后续 ``fsync`` 等待包含这次可见性变更的commit。

为什么conversion必须发生在成功I/O后
----------------------------------

如果data I/O失败，ext4不会执行written conversion。unwritten mapping继续对read返回zeros，从而避免把physical block中的旧数据暴露给用户。

成功顺序是：

.. code-block:: text

   physical allocation as unwritten
   → write new bytes to P
   → successful completion
   → journaled metadata conversion to written

written状态是“这些blocks现在可以按文件数据读取”的发布边界。

folio writeback在哪里结束
-------------------------

conversion成功后：

.. code-block:: text

   ext4_clear_io_unwritten_flag
   → ext4_release_io_end
   → ext4_finish_bio
   → clear buffer async-write state
   → folio_end_writeback

folio现在：

.. code-block:: text

   dirty     = false
   writeback = false
   uptodate  = true

等待该folio的parent被唤醒，``file_write_and_wait_range()`` 完成data与conversion阶段，并检查mapping writeback error；固定结果为0。

``ext4_fsync_journal`` 等待哪个transaction
-----------------------------------------

回到 ``ext4_sync_file()`` 后执行：

.. code-block:: c

   ext4_fsync_journal(inode, datasync=false, &needs_barrier);

普通 ``fsync`` 使用：

.. code-block:: text

   commit_tid = EXT4_I(inode)->i_sync_tid

这个tid至少覆盖：

* 文件创建时的inode与directory-entry metadata；
* data block bitmap与group descriptor；
* logical block 0的extent insertion；
* ``i_size/i_disksize/i_blocks`` 的on-disk inode更新；
* unwritten→written conversion。

fast commit固定关闭，因此 ``ext4_fc_commit()`` 收敛到full JBD2 transaction commit并等待完成。JBD2按transaction顺序提交，较早的create transaction若尚未完成，也会在目标tid完成前先完成。

``data=ordered`` 在这里保证什么
-------------------------------

本场景的数据安全主要由unwritten extent publication顺序实现：conversion metadata只在data I/O成功后生成。full journal commit随后持久化written extent与inode metadata。

因此crash不会产生“extent已经written、block仍含旧数据”的窗口。可能观察到的恢复结果只能位于已建立的安全边界：旧状态、unwritten zero-readable状态，或完整written data状态。

为什么还要device flush
----------------------

journal commit completion只证明block layer命令完成；带volatile write cache的device仍可能缓存data或commit record。

``ext4_fsync_journal()`` 固定判断：

.. code-block:: text

   JBD2 barrier enabled
   transaction did not itself send the final required data barrier
   → needs_barrier = true

于是 ``ext4_sync_file()`` 调用：

.. code-block:: text

   blkdev_issue_flush
   → submit_bio_wait(REQ_OP_FLUSH)
   → blk-mq flush sequence
   → SCSI SYNCHRONIZE CACHE
   → libata ATA FLUSH CACHE / FLUSH CACHE EXT
   → AHCI non-data command
   → device confirms volatile cache committed

flush完成后，data block、journal commit record以及它排序覆盖的metadata满足本次fsync durability要求。home-location metadata checkpoint可以稍后发生；journal commit durable与checkpoint complete不是同一概念。

错误检查与系统调用返回
----------------------

``ext4_sync_file()`` 最后执行：

.. code-block:: c

   file_check_and_advance_wb_err(file);

本场景没有writeback error，因此返回0。控制流退出：

.. code-block:: text

   ext4_sync_file
   → vfs_fsync_range
   → do_fsync
   → __x64_sys_fsync
   → syscall_exit_to_user_mode
   → SYSRETQ或IRETQ

parent回到CPL 3：

.. code-block:: text

   RAX = 0

``fsync`` 不改变file position，所以 ``file->f_pos`` 仍为4096。

当前精确状态
------------

* current task：parent；
* CPU mode：x86-64 CPL 3；
* ``fsync(6)`` result/RAX：0；
* fd 6：仍打开、write-only；
* ``file->f_pos``：4096；
* pathname：``/work/demo.txt``；
* inode ``i_size``：4096；
* ext4 ``i_disksize``：4096；
* inode ``i_blocks``：8个512-byte sectors；
* extent：logical block 0 → physical block ``P``，written；
* delalloc reservation：0；
* page-cache folio：uptodate、clean、not under writeback；
* data bio/request/SCSI/ATA/AHCI command：complete并released；
* unwritten conversion work：complete；
* target JBD2 transaction：committed；
* requireddevice flush：complete；
* create dirent、inode size、extent与data durability：满足本次fsync；
* metadata home-block checkpoint：不要求已经完成；
* next runtime scenario：unselected。

关键边界
--------

#. data DMA completion与extent written conversion是两个阶段。
#. ext4延迟 ``folio_end_writeback``，直到unwritten conversion完成。
#. unwritten extent防止I/O失败时暴露stale disk contents。
#. ``i_sync_tid`` 让fsync等待覆盖最新extent conversion的transaction。
#. journal commit durable不等于metadata已经checkpoint到home blocks。
#. standalone FLUSH把block-layer completion提升为volatile device cache durability。
#. fsync返回0后fd仍打开，file position也不会重置。

资料
----

* `Linux 7.2-rc1 fs/ext4/page-io.c：ext4_end_bio、conversion work与folio_end_writeback <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/page-io.c>`_
* `Linux 7.2-rc1 fs/ext4/extents.c：unwritten extent end-I/O conversion <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/extents.c>`_
* `Linux 7.2-rc1 fs/ext4/fsync.c：journal commit、barrier与fsync return <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/fsync.c>`_
