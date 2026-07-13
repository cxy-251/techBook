第八十七章：WRITE bio 怎样变成 AHCI command 并写入 PxCI？
================================================================

第八十六章结束时，ext4 已经构造一个：

.. code-block:: text

   operation   = REQ_OP_WRITE | REQ_SYNC
   data source = page-cache folio
   bi_end_io   = ext4_end_bio

并调用：

.. code-block:: c

   blk_crypto_submit_bio(bio);

本章固定成功提交路径：bio没有 crypt context，不被 blk-cgroup throttle，不需要 split，没有可合并 request，queue 与 device 资源可用。章节追踪它怎样成为 blk-mq request、SCSI WRITE、ATA write taskfile 和 AHCI command slot，最后写入 ``PxCI[tag]``。

未加密 WRITE 怎样进入普通 block submission
------------------------------------------

``blk_crypto_submit_bio()`` 检查不到 ``bio_crypt_ctx``，直接调用：

.. code-block:: c

   submit_bio(bio);

``submit_bio()`` 记录 write I/O accounting、设置 I/O priority，然后进入：

.. code-block:: c

   submit_bio_noacct(bio);

accounting 只表示 block I/O 被提交，不表示数据已经离开内存，也不表示设备 write cache 已经持久化。

WRITE 比 READ 多了哪些通用检查
------------------------------

``submit_bio_noacct()`` 取得 ``bio->bi_bdev`` 和 request queue，检查：

* block device 是否只读；
* filesystem freeze/claim 状态是否允许该 I/O；
* sector range 是否越界；
* operation 是否受 queue 支持；
* fault injection 是否制造失败；
* block-cgroup 是否需要 throttle；
* crypt/integrity/zone 属性是否有效。

固定 ``/dev/sda1`` 可写，请求没有越界，也没有 injected error。当前 ``REQ_SYNC`` 不改变 operation 类型，它只是 request priority/同步语义的一部分。

分区地址怎样变成整盘地址
------------------------

ext4 bio 中的 ``bi_sector`` 相对于 ``/dev/sda1``。通用 block layer 执行分区 remap：

.. code-block:: c

   bio->bi_iter.bi_sector += bdev->bd_start_sect;
   bio_set_flag(bio, BIO_REMAPPED);

固定第一分区从整盘 LBA 2048 开始：

.. code-block:: text

   ext4 physical block
   → partition-relative sector S
   → whole-disk sector S + 2048

remap 只改变地址坐标，不复制 folio 数据，也不改变 ext4 logical block mapping。

bio 怎样进入 ``blk_mq_submit_bio``
----------------------------------

普通 SCSI disk 没有 filesystem-facing 自定义 ``submit_bio`` callback，因此合法 bio最终进入：

.. code-block:: c

   blk_mq_submit_bio(bio);

当前 ext4 writeback 已经开启 block plug。``blk_mq_submit_bio()`` 可能先把新 request 放入 plug list；当 ``ext4_do_writepages()`` 执行 ``blk_finish_plug()`` 时，plug 中的 request 会被 merge/dispatch。

固定 bio满足 queue limits：

* 4096-byte size 与 logical-block alignment 合法；
* segment 数不超过 AHCI/SCSI 限制；
* 不需要 ``__bio_split_to_limits()`` 拆分；
* 没有兼容的已有 request 可 merge。

因此 blk-mq 分配新的 ``struct request`` 和 tag。

``struct request`` 怎样继承 WRITE 属性
--------------------------------------

``blk_mq_bio_to_request()`` 建立：

.. code-block:: text

   rq->bio       → ext4 WRITE bio
   rq sector     → whole-disk sector
   rq data len   → 4096 bytes
   rq operation  → REQ_OP_WRITE
   rq flags      → 包含 REQ_SYNC，不包含 REQ_FUA
   rq segments   → 指向 page-cache folio

bio 与 request 仍是两个对象：

* bio保存 folio vectors 与 ext4 completion callback；
* request保存 queue、tag、调度与 driver-private command state。

request 最终通过 plug、I/O scheduler 或 direct issue 汇合到 SCSI queue 的：

.. code-block:: c

   scsi_queue_rq(hctx, &bd);

SCSI data direction 为什么是 ``DMA_TO_DEVICE``
---------------------------------------------

``scsi_prepare_cmd()`` 根据 request direction 初始化 ``struct scsi_cmnd``：

.. code-block:: text

   REQ_OP_WRITE
   → rq_dma_dir(request)
   → DMA_TO_DEVICE

这表示 DMA ownership 方向是：

.. code-block:: text

   system memory
   → storage controller
   → SATA device

system memory 中的源数据是 page-cache folio，不再是用户 buffer。

``sd`` 怎样构造 SCSI WRITE CDB
-----------------------------

``sd_init_command()`` 看到 ``REQ_OP_WRITE``，调用：

.. code-block:: c

   sd_setup_read_write_cmnd(cmd);

函数计算：

.. code-block:: c

   lba = sectors_to_logical(sdev, blk_rq_pos(rq));
   nr_blocks = sectors_to_logical(sdev, blk_rq_sectors(rq));

libata 初始化 SCSI device 时设置 ``use_10_for_rw``，所以普通小范围 ATA disk write通常使用 WRITE(10)。如果 disk capacity/configuration 要求 16-byte addressing，``sd`` 使用 WRITE(16)。固定 disk size 没有锁定，因此保留这两个真实分支：

.. code-block:: text

   WRITE(10) ─┐
              ├→ libata ata_scsi_rw_xlat()
   WRITE(16) ─┘

当前 request 没有 ``REQ_FUA``，所以 CDB 的 FUA bit 不由本次 data bio设置。``O_SYNC`` 的最终 durability 依赖后续 journal commit 与必要的 device flush，而不是在这里偷偷变成 FUA write。

``scsi_dispatch_cmd`` 怎样进入 libata
------------------------------------

SCSI command 准备完成后：

.. code-block:: c

   blk_mq_start_request(rq);
   scsi_dispatch_cmd(cmd);

q35 AHCI host 的 ``queuecommand`` 是：

.. code-block:: c

   ata_scsi_queuecmd

libata从 ``Scsi_Host`` 找到 port 0 的 ``ata_port``、``ata_link`` 和 ``ata_device``，随后为 command 分配 ``struct ata_queued_cmd``。

``ata_queued_cmd`` 连接：

.. code-block:: text

   ata_queued_cmd
   ├── scsicmd → SCSI WRITE command
   ├── sg      → request scatterlist
   ├── tf      → ATA taskfile
   ├── tag     → libata software tag
   ├── hw_tag  → AHCI command slot
   └── complete_fn → ata_scsi_qc_complete

``ata_scsi_rw_xlat`` 怎样生成 ATA WRITE
---------------------------------------

WRITE(10/16) 都由 ``ata_scsi_rw_xlat()`` 解析为：

* ATA LBA；
* sector count；
* write direction；
* FUA 与其他 command flags；
* transfer byte count。

它设置 I/O command state并调用：

.. code-block:: c

   ata_build_rw_tf(qc, block, n_block,
                   ATA_TFLAG_WRITE | other_flags,
                   dld, class);

``ata_build_rw_tf()`` 根据 IDENTIFY、LBA width、NCQ negotiation 与 runtime state选择：

* ATA DMA WRITE；
* ATA DMA WRITE EXT；
* NCQ ``WRITE FPDMA QUEUED``；
* 必要时的 PIO WRITE。

固定 q35 controller支持 NCQ，实际 command仍取决于 QEMU disk 暴露的 IDENTIFY 数据。所有成功分支都在 AHCI command preparation 重新汇合。

scatterlist 怎样变成设备可读的 DMA 地址
---------------------------------------

``ata_qc_issue()`` 对 data command 调用 DMA API：

.. code-block:: c

   dma_map_sg(ap->dev, qc->sg, qc->n_elem,
              DMA_TO_DEVICE);

成功后 scatterlist 中的 ``sg_dma_address`` 与 ``sg_dma_len`` 可供 AHCI controller 使用。

对 WRITE，DMA mapping 表示 controller将从这些地址读取数据。``dma_map_sg()`` 只建立 DMA address/ownership，还没有启动 SATA transaction。

AHCI H2D FIS 和 PRDT 各自描述什么
---------------------------------

``ahci_qc_prep()`` 把 ATA taskfile编码成 Register Host-to-Device FIS。FIS 告诉 SATA device：

* 执行哪个 ATA WRITE command；
* 写哪个 LBA；
* 写多少 sectors；
* 是否使用 NCQ/tag；
* command flags。

``ahci_fill_sg()`` 把 DMA-mapped scatterlist写入 PRDT：

.. code-block:: text

   PRDT entry
   → page-cache folio DMA address
   → 4096-byte transfer length

对 WRITE，PRDT 描述的是 controller需要从内存读取的数据源。

command header 为什么设置 ``AHCI_CMD_WRITE``
-------------------------------------------

``ahci_qc_prep()`` 为 slot计算 options。与 READ 不同，当前 data direction 是 host-to-device，所以 command header包含：

.. code-block:: text

   AHCI_CMD_WRITE = 1

这告诉 controller PRDT 描述的是内存到设备的数据传输。header 同时记录：

* command FIS length；
* PRDT entry count；
* command table DMA address；
* port multiplier 与 ATAPI flags。

``PxCI`` 怎样启动命令
--------------------

``ata_qc_issue()`` 先登记 software active state，并调用 ``ahci_qc_issue()``。

NCQ 分支先写：

.. code-block:: c

   writel(1 << qc->hw_tag,
          port_mmio + PORT_SCR_ACT);  /* PxSACT */

所有分支最终执行：

.. code-block:: c

   writel(1 << qc->hw_tag,
          port_mmio + PORT_CMD_ISSUE); /* PxCI */

从这一刻开始：

.. code-block:: text

   AHCI engine
   → 读取 command header/table
   → 读取 H2D FIS 与 PRDT
   → 按 PRDT 从 page-cache folio DMA-read 数据
   → 向 SATA disk 执行 ATA WRITE

``ahci_qc_issue()`` 返回只证明 command issue bit 已设置，不证明 device已经完成写入，更不证明 write cache已经持久化。

当前精确边界
------------

CPU 已执行：

.. code-block:: c

   PxCI[tag] = 1;

当前状态：

* blk-mq request：已 started，持有 tag；
* request direction：WRITE；
* SCSI command：WRITE(10) 或必要时 WRITE(16)；
* SCSI DMA direction：``DMA_TO_DEVICE``；
* ATA taskfile：DMA/NCQ/PIO WRITE 的 negotiated 形式；
* ATA queued command：active；
* DMA mapping：page-cache folio → controller，已建立；
* AHCI command header：``AHCI_CMD_WRITE`` 已设置；
* AHCI PRDT：指向 page-cache folio DMA address；
* ``PxSACT``：NCQ 分支已登记 tag；
* ``PxCI``：当前 tag bit 已置 1；
* folio：unlocked、``PG_writeback=1``；
* data completion：尚未发生；
* journal commit/device flush：尚未发生；
* writer task：将从 submission stack 返回并在 data-range wait 中等待；
* ``file->f_pos``：仍为 0；
* ``write()``：尚未返回。

关键边界
--------

#. ``REQ_SYNC`` 不会自动设置 SCSI FUA。
#. bio、request、SCSI command、ATA queued command 和 AHCI slot 是不同对象。
#. WRITE 的 DMA direction 是 ``DMA_TO_DEVICE``。
#. AHCI WRITE PRDT 指向 page-cache folio，不指向 userspace buffer。
#. ``AHCI_CMD_WRITE`` 描述传输方向，不表示 command 已完成。
#. ``PxCI[tag]=1`` 是提交点，不是 completion point。
#. data command completion、journal commit 与 device cache flush 仍是三个不同阶段。

资料
----

* `Linux 7.2-rc1 block/blk-core.c：WRITE bio validation 与 partition remap <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-core.c>`_
* `Linux 7.2-rc1 block/blk-mq.c：bio-to-request、plug 与 dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-mq.c>`_
* `Linux 7.2-rc1 drivers/scsi/scsi_lib.c：scsi_queue_rq 与 dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/scsi_lib.c>`_
* `Linux 7.2-rc1 drivers/scsi/sd.c：SCSI WRITE CDB construction <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/sd.c>`_
* `Linux 7.2-rc1 drivers/ata/libata-scsi.c：SCSI-to-ATA WRITE translation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-scsi.c>`_
* `Linux 7.2-rc1 drivers/ata/libata-core.c：ATA qc 与 DMA mapping <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-core.c>`_
* `Linux 7.2-rc1 drivers/ata/libahci.c：AHCI WRITE command preparation 与 PxCI <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libahci.c>`_
