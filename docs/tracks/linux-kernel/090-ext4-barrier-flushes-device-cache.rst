第九十章：ext4 barrier 怎样把 journal 顺序落实到设备 cache？
================================================================

第八十九章结束时，``ext4_fsync_journal()`` 已经成功返回。相关 metadata durability 已由以下任一分支满足：

.. code-block:: text

   target transaction already committed
   successful fast commit
   successful full JBD2 commit

``ext4_sync_file()`` 现在检查 ``needs_barrier``。如果 journal commit 本身已经携带正确的 preflush/FUA 顺序，不需要额外命令；如果目标 transaction 无法再替本次 fsync 提供 barrier，则调用：

.. code-block:: c

   blkdev_issue_flush(inode->i_sb->s_bdev);

本章追踪这个 standalone flush 怎样从零长度 bio 变成 SCSI SYNCHRONIZE CACHE、ATA FLUSH CACHE 与 AHCI no-data command，并在完成后让 ``ext4_sync_file()`` 返回 0。

为什么不一定需要额外 flush
--------------------------

``needs_barrier == false`` 可能来自不同原因：

* full JBD2 commit 的 commit record 已携带 ``REQ_PREFLUSH | REQ_FUA``；
* fast-commit tail 已携带 ``REQ_PREFLUSH | REQ_FUA``；
*正在进行的 transaction 已被标记为会发送 data barrier；
* filesystem mount policy禁用了 barrier。

前三种情况下，commit path已经承担 cache ordering。最后一种情况下，内核按 ``nobarrier`` 策略不发送 flush，物理断电保证取决于设备与平台；不能把“没有额外 flush”统一解释成“设备 cache 一定已清空”。

什么时候 ``needs_barrier`` 为 true
----------------------------------

典型情况是目标 ``commit_tid`` 在检查时已经 committed，或 commit state已越过可以附加 data flush 的阶段：

.. code-block:: text

   file data write completed
   → related transaction already committed independently
   → that old commit cannot order this later data write
   → ext4 sets needs_barrier
   → issue standalone device flush

这样避免出现“metadata transaction 已提交，但后来的 data write仍停留在 volatile cache”的窗口。

``blkdev_issue_flush`` 为什么使用零 vector bio
-------------------------------------------

block layer构造一个栈上 bio：

.. code-block:: c

   bio_init(&bio, bdev, NULL, 0,
            REQ_OP_WRITE | REQ_PREFLUSH);
   submit_bio_wait(&bio);

这个 bio：

* 没有 payload pages；
* 没有 sector range；
* operation语义是 preflush；
* 调用者同步等待 completion。

flush不是“再写一次那 4096 bytes”。它要求 block device把之前完成但可能仍在 volatile cache中的 writes推进到设备承诺的持久介质。

block flush state machine 做什么
-------------------------------

``submit_bio_wait()`` 让 bio进入普通 block submission。blk-mq把它变成 ``REQ_OP_FLUSH`` request并交给 flush state machine。

对于可能同时包含 PREFLUSH、data、FUA的普通 write request，block layer会把动作拆成：

.. code-block:: text

   preflush
   → data request
   → optional postflush

当前 bio只有 ``REQ_PREFLUSH``，没有 data payload，所以 state machine只需执行 flush action。request仍需要 blk-mq tag、driver dispatch与 completion，但没有 DMA scatterlist。

``sd`` 怎样表达 flush
---------------------

SCSI disk层看到 ``REQ_OP_FLUSH`` 后调用：

.. code-block:: c

   sd_setup_flush_cmnd(cmd);

它把 ``cmd->sdb`` 清零，因为 flush没有 data transfer，然后根据 device配置选择：

.. code-block:: text

   SYNCHRONIZE CACHE(10)
   或
   SYNCHRONIZE CACHE(16)

同时设置更长的 flush timeout。固定 QEMU disk没有锁定 ``use_16_for_sync``，因此正文保留真实分支。

SCSI command的核心语义是：在 command成功完成前，使先前的 write cache内容达到设备对 SYNCHRONIZE CACHE承诺的状态。

libata 怎样把它翻译成 ATA flush
-------------------------------

q35 AHCI disk仍通过 ``ata_scsi_queuecmd()`` 进入 libata。SYNCHRONIZE CACHE opcode映射到：

.. code-block:: c

   ata_scsi_flush_xlat(qc);

translation建立 no-data ATA taskfile：

.. code-block:: c

   tf->protocol = ATA_PROT_NODATA;
   tf->flags   |= ATA_TFLAG_DEVICE;

随后根据 ATA device capability选择：

.. code-block:: text

   ATA_CMD_FLUSH
   或
   ATA_CMD_FLUSH_EXT

并设置 ``ATA_QCFLAG_IO``，因为 flush对 I/O integrity至关重要。

这里没有 LBA、sector count或 data direction。flush command针对的是 device cache状态，而不是某个特定 file block。

AHCI no-data command怎样提交
---------------------------

libata分配 ``ata_queued_cmd``，但不会建立 data scatterlist，也不会调用 ``dma_map_sg()``。

``ahci_qc_prep()`` 仍会填写：

* H2D Register FIS，包含 ATA FLUSH CACHE/EXT opcode；
* command header与 command table address；
* PRDT length为 0；
* ``AHCI_CMD_WRITE`` 不用于表示 payload write，因为 command没有 data phase。

``ahci_qc_issue()`` 最终写：

.. code-block:: c

   writel(1 << qc->hw_tag,
          port_mmio + PORT_CMD_ISSUE);

q35 AHCI engine读取 H2D FIS并让 SATA device执行 flush。``PxCI`` 写入仍只是 submission point。

flush completion怎样返回等待者
------------------------------

设备完成后产生 AHCI interrupt。成功路径与普通 command一样识别 completed tag：

.. code-block:: text

   AHCI IRQ
   → ata_qc_complete
   → ata_scsi_qc_complete
   → scsi_done
   → blk_mq_complete_request
   → flush request completion
   → submit_bio_wait waiter 被唤醒

因为没有 data payload：

* 不存在 folio DMA；
* 不调用 ``ext4_end_bio``；
* 不改变 target folio flags；
* completion只报告 flush command成功或失败。

固定无错误路径中：

.. code-block:: text

   blkdev_issue_flush(...) = 0

``ext4_sync_file`` 怎样合并 commit 与 flush 错误
----------------------------------------------

代码保留 journal commit 的返回值 ``ret``，再执行：

.. code-block:: c

   err = blkdev_issue_flush(...);
   if (!ret)
       ret = err;

这意味着 journal commit错误优先保留；只有 commit成功时，flush错误才成为 fsync返回值。

无论是否执行 standalone flush，函数随后进入 ``out``：

.. code-block:: c

   err = file_check_and_advance_wb_err(file);
   if (ret == 0)
       ret = err;

``file_check_and_advance_wb_err()`` 比较 ``mapping->wb_err`` 与该 open file description保存的 ``f_wb_err`` cursor：

* 没有新 writeback error：返回 0；
* 出现新的 ``EIO`` 或 ``ENOSPC``：只向尚未观察该 error的 file description报告一次，并推进 cursor。

固定场景没有 writeback、journal或 flush error，因此 ``ret`` 保持 0。

此刻 O_SYNC durability 到达什么边界
----------------------------------

在 barrier-enabled成功路径中：

.. code-block:: text

   file data WRITE completed
   → required journal recovery record durable
   → commit path barrier 或 standalone FLUSH CACHE completed
   → ext4_sync_file returns success

这正是 ext4在当前 mount/device能力下为本次 O_SYNC提供的完成边界。

如果 mount显式使用 ``nobarrier``，代码仍可返回成功，但内核没有请求设备执行 cache flush。该配置主动降低了 power-loss ordering保证，正文必须保留这个差异。

当前精确边界
------------

``ext4_sync_file()`` 已返回 0，控制权回到：

.. code-block:: c

   generic_write_sync(iocb, 4096);

当前状态：

* file data WRITE：完成；
* target folio：clean、uptodate、unlocked、``PG_writeback=0``；
* journal requirement：成功满足；
* barrier-enabled路径：commit内 barrier或 standalone device flush已成功完成；
* standalone flush是否实际发出：取决于 ``needs_barrier``；
* writeback error cursor：已检查并推进，无错误；
* ``ext4_sync_file()`` result：0；
* ``kiocb->ki_pos``：4096；
* local ``pos``：0；
* ``file->f_pos``：0；
* superblock freeze protection：仍由 ``vfs_write()`` 持有；
* writer task：仍在 CPL 0 syscall process context；
* syscall return value：尚未写入 ``pt_regs->ax``。

下一入口是 ``generic_write_sync()`` 的成功返回路径，随后依次回到 ``ext4_buffered_write_iter()``、``new_sync_write()``、``vfs_write()`` 与 ``ksys_write()``。

关键边界
--------

#. standalone flush bio没有 payload、sector或 folio。
#. SCSI SYNCHRONIZE CACHE会翻译成 ATA FLUSH CACHE或 FLUSH CACHE EXT。
#. flush command没有 DMA data phase，AHCI PRDT entry count为 0。
#. ``PxCI`` submission与 flush completion仍是两个时刻。
#. commit内 barrier与 standalone flush是替代关系，不应重复描述成必然都发生。
#. ``nobarrier`` 下没有 device flush，返回成功不等于最强断电保证。
#. ``file_check_and_advance_wb_err`` 负责向当前 file description报告尚未观察的 writeback error。
#. ``ext4_sync_file()`` 返回后，文件位置仍未提交。

资料
----

* `Linux 7.2-rc1 fs/ext4/fsync.c：needs_barrier、blkdev_issue_flush 与 error merge <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/fsync.c>`_
* `Linux 7.2-rc1 block/blk-flush.c：blkdev_issue_flush 与 flush state machine <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-flush.c>`_
* `Linux 7.2-rc1 drivers/scsi/sd.c：SYNCHRONIZE CACHE command construction <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/sd.c>`_
* `Linux 7.2-rc1 drivers/ata/libata-scsi.c：ata_scsi_flush_xlat <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-scsi.c>`_
* `Linux 7.2-rc1 drivers/ata/libahci.c：AHCI no-data command submission 与 completion <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libahci.c>`_
* `Linux 7.2-rc1 mm/filemap.c：file_check_and_advance_wb_err <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
