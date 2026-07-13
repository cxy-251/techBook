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
   LK-WRITE-083..LK-WRITE-088

最新三章：

#. ``LK-WRITE-086``：ext4 writeback 怎样把 dirty folio 变成 WRITE bio？
#. ``LK-WRITE-087``：WRITE bio 怎样变成 AHCI command 并写入 PxCI？
#. ``LK-WRITE-088``：WRITE completion 怎样结束 folio writeback，并让 O_SYNC 等待继续？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

旧章节中的 ``Linux 6.12.95`` 是历史显示标签错误，技术事实继续以固定 Linux commit 为准。

已完成的 read 场景
------------------

``read(fd, buf, 4096)`` cold page-cache miss 已完整闭环：VFS、ext4、page cache、block、SCSI、libata、AHCI、DMA completion、folio unlock、user copy 和 syscall return 均已写完。

当前 write 固定场景
-------------------

::

   userspace call       = write(fd, buf, 4096)
   ABI                  = native x86-64 SYSCALL
   open flags           = O_WRONLY | O_SYNC
   file                 = independent already-open regular ext4 file
   filesystem           = /dev/sda1, journal enabled, data=ordered, delalloc enabled
   initial f_pos        = 0
   file size            = at least 4096 bytes
   filesystem block     = 4096 bytes
   write type           = full-block overwrite, not extending
   extent               = logical block 0 already initialized and mapped
   initial page cache   = index 0 absent
   user buffer          = mapped, readable, stable
   excluded             = O_DIRECT, DAX, inline data, fscrypt, fs-verity, atomic write
   failure policy       = no ENOSPC, copy fault, forced shutdown or injected I/O error

当前控制流
----------

::

   userspace write(fd, buf, 4096)
   → entry_SYSCALL_64 / __x64_sys_write
   → ksys_write / vfs_write / new_sync_write
   → ext4_file_write_iter / ext4_buffered_write_iter
   → generic_perform_write
   → ext4_da_write_begin
   → copy_folio_from_iter_atomic
   → ext4_da_write_end
   → dirty page-cache folio
   → generic_write_sync
   → vfs_fsync_range(file, 0, 4095, datasync=0)
   → ext4_sync_file
   → file_write_and_wait_range
   → WB_SYNC_ALL
   → ext4_writepages
   → scan and lock dirty folio
   → folio_clear_dirty_for_io
   → ext4_bio_write_folio
   → PG_writeback = 1
   → REQ_OP_WRITE | REQ_SYNC bio
   → blk_crypto_submit_bio
   → partition remap
   → blk-mq request/tag
   → SCSI WRITE(10 or 16)
   → libata ATA DMA/NCQ WRITE
   → dma_map_sg(DMA_TO_DEVICE)
   → AHCI H2D FIS / PRDT / AHCI_CMD_WRITE
   → PxCI[tag] = 1
   → AHCI completion interrupt
   → ata_qc_complete / dma_unmap_sg
   → ata_scsi_qc_complete / scsi_done
   → blk_mq_complete_request
   → scsi_complete / blk_update_request
   → bio_endio / ext4_end_bio
   → ext4_finish_bio
   → folio_end_writeback
   → file_write_and_wait_range returns 0
   → ext4_fsync_journal next

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* 当前执行者：发起 O_SYNC ``write()`` 的 task；
* CPU mode：x86-64 CPL 0，仍在 syscall process context；
* target folio：page cache 中，clean、uptodate、unlocked；
* ``PG_writeback``：0；
* data WRITE bio：已完成并释放；
* blk-mq request/tag：已完成并释放；
* SCSI/ATA/AHCI command：已完成；
* DMA mapping：已解除；
* data-range wait：成功返回；
* data writeback error：无；
* device cache durability：尚未最终确认；
* JBD2 transaction commit：尚未执行下一入口；
* optional block-device flush：尚未执行；
* ``kiocb->ki_pos``：4096；
* local ``pos``：0；
* ``file->f_pos``：0；
* ``write()``：尚未返回。

关键边界
--------

#. 新 write 场景独立于前一条 read，不共享其 page-cache 结果。
#. 已有 initialized extent 的覆盖写在 ``ext4_writepages`` 第一遍直接提交，不分配新 extent。
#. ``folio_clear_dirty_for_io``、``PG_writeback`` 与 folio lock 是不同状态。
#. WRITE DMA 从 page-cache folio读取数据，不直接读取用户 buffer。
#. ``REQ_SYNC`` 不等于 ``REQ_FUA``。
#. AHCI command completion必须经过 SCSI、blk-mq、bio和 ``ext4_end_bio`` 才能结束 folio writeback。
#. ``folio_end_writeback`` 不提交 JBD2 transaction，也不保证 volatile device cache已经 flush。
#. data-range wait成功发生在 journal commit之前。
#. ``kiocb->ki_pos``、local ``pos`` 与共享 ``file->f_pos`` 尚未全部提交。

下一任务
--------

下一批从：

.. code-block:: c

   ext4_fsync_journal(inode, false, &needs_barrier);

开始：

::

   choose i_sync_tid
   → ext4_fc_commit
   → fast commit or full JBD2 commit
   → determine needs_barrier
   → optional blkdev_issue_flush
   → file_check_and_advance_wb_err
   → ext4_sync_file returns
   → generic_write_sync returns 4096
   → new_sync_write copies kiocb->ki_pos to local pos
   → vfs_write accounting / file_end_write
   → ksys_write commits file->f_pos = 4096
   → syscall exit
   → userspace RAX = 4096

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。
