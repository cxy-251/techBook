第八十八章：WRITE completion 怎样结束 folio writeback，并让 O_SYNC 等待继续？
================================================================================

第八十七章结束时，AHCI command header 已设置 ``AHCI_CMD_WRITE``，PRDT 指向 page-cache folio，CPU 已写入：

.. code-block:: c

   PxCI[tag] = 1;

q35 AHCI engine随后从 folio DMA-read 4096 bytes，并向 SATA disk执行 ATA WRITE。本章固定无错误完成路径，追踪 completion interrupt 怎样回穿 libata、SCSI、blk-mq、bio 和 ext4，最终执行 ``folio_end_writeback()``，并让 ``file_write_and_wait_range()`` 完成 data-range wait。

章节停在 ``ext4_sync_file()`` 已确认 file data writeback成功，下一步即将提交相关 JBD2 transaction。此时仍不能说整个 O_SYNC write已经完成持久化。

hardware completion 与 writer task 是两条控制流
----------------------------------------------

提交之后存在两条并发线：

.. code-block:: text

   writer task
   → 从 ahci_qc_issue() 返回
   → 返回 ext4_writepages()
   → blk_finish_plug()
   → filemap_fdatawrite_range() 返回
   → __filemap_fdatawait_range()
   → 等待 PG_writeback 清除

   AHCI engine / SATA disk
   → fetch command structures
   → DMA-read page-cache folio
   → execute ATA WRITE
   → clear hardware active bit
   → set interrupt status
   → raise completion interrupt

completion IRQ 落在哪个 CPU 上不固定，``current`` 也不保证是 writer task。writer只有在 writeback wait condition满足后才会继续。

AHCI 怎样确认哪个 WRITE tag 已完成
----------------------------------

INTx、MSI 与 MSI-X 入口最终汇合到 libahci port handler。driver读取并清除 ``PxIS``，然后读取当前硬件 active state：

* NCQ command主要查看 ``PxSACT``；
* non-NCQ command主要查看 ``PxCI``；
* 特殊组合状态可能合并二者。

软件提交时保存了 ``ap->qc_active``。libata比较：

.. code-block:: c

   done_mask = ap->qc_active ^ hardware_active_mask;

固定当前 tag从 active 变为 inactive，因此 ``done_mask`` 包含该 ``ata_queued_cmd``。

``ata_qc_complete`` 怎样结束 DMA ownership
-----------------------------------------

``ata_qc_complete_multiple()`` 找到 command后调用：

.. code-block:: c

   ata_qc_complete(qc);

当前 command在提交时执行过：

.. code-block:: c

   dma_map_sg(..., DMA_TO_DEVICE);

completion path中的 ``ata_sg_clean()`` 相应执行 DMA unmap。对 WRITE，这一步结束 controller从 folio读取数据的 DMA ownership，并回收可能的 IOMMU mapping。

顺序是：

.. code-block:: text

   controller finishes reading folio memory
   → command completion becomes visible
   → dma_unmap_sg(DMA_TO_DEVICE)
   → upper layers may finish buffer/writeback state

这不表示 SATA device的 volatile write cache已经 flush。它只结束当前 ATA data command及其 DMA mapping。

libata 怎样把成功结果交回 SCSI
-----------------------------

``__ata_qc_complete()`` 清理：

.. code-block:: text

   NCQ      → link->sactive bit
   non-NCQ  → link->active_tag
   both     → ap->qc_active bit
              ATA_QCFLAG_ACTIVE

随后调用 ``qc->complete_fn``，即：

.. code-block:: c

   ata_scsi_qc_complete(qc);

固定 ``qc->err_mask == 0``，无需构造 sense data或启动 libata error handler。libata释放 queued-command state，并调用 SCSI completion callback：

.. code-block:: c

   scsi_done(scmd);

``scsi_done`` 再调用：

.. code-block:: c

   blk_mq_complete_request(request);

到这里完成的是 ATA/SCSI command，ext4 folio的 ``PG_writeback`` 仍需要 bio completion来清除。

SCSI completion 怎样结束 request bytes
-------------------------------------

blk-mq最终调用 ``scsi_complete(request)``。SCSI mid-layer检查 result disposition：

.. code-block:: text

   command result = success
   residual       = 0
   disposition    = SUCCESS

因此进入：

.. code-block:: text

   scsi_finish_command
   → scsi_io_completion
   → scsi_end_request
   → blk_update_request

成功字节数覆盖当前 4096-byte WRITE request。``blk_update_request()`` 推进 request中的 bio iterator，并对已完成 bio调用：

.. code-block:: c

   bio_endio(bio);

request completion与 bio completion仍是不同层：request tag在后续 ``__blk_mq_end_request()`` 中释放；bio先通过 ``bi_end_io`` 把语义交还 ext4。

``bio_endio`` 怎样进入 ``ext4_end_bio``
--------------------------------------

通用 ``bio_endio()`` 完成 tracing、cgroup、request-QoS 与 bio chaining收尾后调用：

.. code-block:: c

   bio->bi_end_io(bio);

第八十六章登记的是：

.. code-block:: c

   bio->bi_end_io = ext4_end_bio;

固定 ``bio->bi_status == BLK_STS_OK``，所以 ext4不设置 mapping writeback error，也不标记 ``EXT4_IO_END_FAILED``。

为什么当前 io_end 不需要延迟 extent conversion
---------------------------------------------

本次覆盖的是已有 initialized extent：

.. code-block:: text

   BH_Unwritten = 0
   EXT4_IO_END_UNWRITTEN = 0

因此 completion不需要把 unwritten extent转换为 written extent，也不需要把 ``io_end`` 排入 reserved-conversion workqueue。

``ext4_end_bio()`` 直接进入普通 finish path：

.. code-block:: text

   ext4_put_io_end_defer(io_end)
   → ext4_finish_bio(bio)
   → bio_put(bio)

若本次写的是新 unwritten extent，completion还会涉及 deferred extent conversion；固定 overwrite路径明确排除该分支。

``ext4_finish_bio`` 怎样找到完成的 folio
---------------------------------------

函数遍历 bio中的 folio range，并取得其 buffer heads。它在 ``b_uptodate_lock`` 下清除当前 bio覆盖 buffers的：

.. code-block:: c

   BH_Async_Write

如果同一 folio还有其他 bio负责的 async-write buffer，``under_io`` 仍非零，不能结束 folio writeback。

固定 filesystem block与 folio都是 4096 bytes，当前 bio覆盖唯一 buffer，所以清除后：

.. code-block:: text

   under_io = 0

于是调用：

.. code-block:: c

   folio_end_writeback(folio);

``folio_end_writeback`` 发布什么状态
-----------------------------------

该函数完成：

* 清除 ``PG_writeback``；
* 更新 writeback accounting；
* 清理 page-cache writeback tag；
* 唤醒等待该 folio writeback的 tasks；
* 允许 reclaim或后续 writeback继续处理 folio。

当前状态变为：

.. code-block:: text

   PG_locked    = 0
   PG_writeback = 0
   PG_dirty     = 0   /* 固定场景没有并发再次 dirty */
   PG_uptodate  = 1

如果另一个 task在 I/O 期间再次修改 folio，``PG_dirty`` 可以重新变为 1；本场景排除并发 writer，所以本轮结束后 folio保持 clean。

为什么 folio clean 仍不等于 O_SYNC 完成
--------------------------------------

``folio_end_writeback()`` 证明本次 data bio已经完成，并不证明：

* 相关 ext4 metadata transaction已经 commit；
* journal commit record已经到达要求的存储层；
* SATA device volatile write cache已经执行 flush；
* ``generic_write_sync()`` 已经返回；
* ``file->f_pos`` 已经更新。

尤其当前 data request没有 ``REQ_FUA``。ATA WRITE command完成时，数据可能已经进入 device write cache；最终 durability仍需要后续 barrier/flush策略。

writer task 怎样结束 data-range wait
-----------------------------------

``file_write_and_wait_range()`` 在提交阶段后执行：

.. code-block:: c

   __filemap_fdatawait_range(mapping, 0, 4095);

它扫描目标 range中的 writeback folio并等待 ``PG_writeback`` 清除。

存在两种调度时序：

.. code-block:: text

   completion较早
   → writer开始扫描时 PG_writeback 已清除
   → 无需睡眠

   completion较晚
   → writer在 folio_wait_writeback() 睡眠
   → folio_end_writeback() 唤醒 waiter
   → writer重新运行

两种时序最终汇合到相同状态。随后 ``file_check_and_advance_wb_err()`` 检查 mapping的 errseq cursor。固定成功路径没有 ``EIO`` 或 ``ENOSPC``，所以：

.. code-block:: text

   file_write_and_wait_range(...) = 0

这表示 file offset 0..4095 的 data writeback成功完成。

``data=ordered`` 的顺序在这里怎样体现
------------------------------------

``ext4_sync_file()`` 的固定 journal-enabled路径明确按以下顺序执行：

.. code-block:: text

   file_write_and_wait_range(file, 0, 4095)
   → data WRITE completion
   → ext4_fsync_journal(inode, datasync=0, ...)

所以相关 metadata transaction不会在 O_SYNC path中越过尚未完成的 file data range。当前已有 mapping overwrite没有在 ``ext4_writepages()`` 中创建新 extent transaction；ordering由 fsync sequencing与 ext4/JBD2 inode transaction state共同完成。

下一步为什么是 journal commit
-----------------------------

``file_write_and_wait_range()`` 返回 0 后，``ext4_sync_file()`` 继续：

.. code-block:: c

   ext4_fsync_journal(inode, false, &needs_barrier);

``datasync=false`` 来自 ``O_SYNC``，所以目标 transaction id是普通 sync所需的 ``i_sync_tid``，而不是仅 data-dependent metadata的 ``i_datasync_tid``。

``ext4_fsync_journal()`` 可能使用 fast commit或完整 JBD2 commit，并根据 barrier状态决定后续是否还需要 ``blkdev_issue_flush()``。这些属于下一批。

当前精确边界
------------

CPU 即将进入：

.. code-block:: c

   ext4_fsync_journal(inode, false, &needs_barrier);

当前状态：

* ATA WRITE command：成功完成；
* AHCI active tag：已清除；
* DMA mapping：已解除；
* SCSI command：成功完成；
* blk-mq request/tag：已完成并释放或正在完成最终释放；
* WRITE bio：已执行 ``bio_endio()`` 与 ``ext4_end_bio()``；
* target folio：uptodate、clean、unlocked、``PG_writeback=0``；
* data-range wait：成功返回；
* mapping writeback error：无；
* file data command：已完成，但 device cache durability尚未最终确认；
* JBD2 transaction commit：尚未执行本章后续调用；
* optional block-device flush：尚未执行；
* ``kiocb->ki_pos``：4096；
* local ``pos``：0；
* ``file->f_pos``：0；
* writer task：仍在 CPL 0 syscall process context；
* ``write()``：尚未返回。

关键边界
--------

#. AHCI command completion不直接清除 ``PG_writeback``；必须穿过 SCSI、blk-mq、bio和 ext4。
#. WRITE completion使用 ``ext4_end_bio``，不是 read路径的 ``mpage_end_io``。
#. initialized extent不需要 deferred unwritten-extent conversion。
#. ``folio_end_writeback()`` 清除 writeback并唤醒 waiters，不提交 JBD2 transaction。
#. clean folio表示本轮 page-cache data已写出，不等于 storage durability已经全部满足。
#. data-range wait成功发生在 journal commit之前。
#. ``file->f_pos`` 仍需等待整个 O_SYNC同步链成功返回后提交。

资料
----

* `Linux 7.2-rc1 drivers/ata/libahci.c：AHCI completion interrupt 与 active tag detection <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libahci.c>`_
* `Linux 7.2-rc1 drivers/ata/libata-core.c：ATA qc completion 与 DMA unmap <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-core.c>`_
* `Linux 7.2-rc1 drivers/ata/libata-scsi.c：ata_scsi_qc_complete <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-scsi.c>`_
* `Linux 7.2-rc1 drivers/scsi/scsi_lib.c：SCSI request completion <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/scsi_lib.c>`_
* `Linux 7.2-rc1 fs/ext4/page-io.c：ext4_end_bio、ext4_finish_bio 与 folio_end_writeback <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/page-io.c>`_
* `Linux 7.2-rc1 mm/filemap.c：file_write_and_wait_range 与 writeback wait <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
* `Linux 7.2-rc1 fs/ext4/fsync.c：data wait之后的 journal commit与 barrier <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/fsync.c>`_
