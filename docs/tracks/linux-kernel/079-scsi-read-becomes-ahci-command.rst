第七十九章：SCSI READ 怎样变成 ATA taskfile 并写入 AHCI command slot？
=====================================================================

第七十八章结束时，blk-mq request 已经进入 SCSI mid-layer，``sd`` 根据 request 建立了适用的 READ CDB，``scsi_dispatch_cmd()`` 即将调用 host template 的：

.. code-block:: c

   host->hostt->queuecommand(host, cmd);

q35 ICH9 AHCI 磁盘由 libata 以 SCSI device 形式暴露。libata 的基础 host template 明确设置：

.. code-block:: c

   .queuecommand = ata_scsi_queuecmd

本章追踪 SCSI READ 怎样经过 libata 翻译成 ATA taskfile，怎样把 folio 的 scatter-gather pages DMA-map，怎样填写 AHCI command table、PRDT 与 command header，最后通过写 ``PxCI`` 的 tag bit 让 q35 AHCI engine 开始执行命令。

章节停在命令提交给硬件之后，completion interrupt 尚未到来。

为什么 SATA disk 出现在 SCSI 层
------------------------------

Linux 的 ``sd`` driver 处理通用块磁盘语义，libata 则在它和 ATA/AHCI hardware 之间实现 SCSI-to-ATA translation layer（SATL）：

.. code-block:: text

   block request
   → SCSI disk command
   → libata translation
   → ATA taskfile
   → AHCI command structures
   → SATA device

因此 ``struct scsi_cmnd`` 不是说物理设备使用并行 SCSI 总线。它只是内核上层采用的统一磁盘命令模型。

``scsi_dispatch_cmd`` 怎样进入 libata
------------------------------------

``scsi_dispatch_cmd()`` 检查 device、host state 和 CDB 长度，然后执行：

.. code-block:: c

   host->hostt->queuecommand(host, cmd);

对固定 q35 AHCI host，该 function pointer 是 ``ata_scsi_queuecmd()``。

``ata_scsi_queuecmd()`` 从 ``Scsi_Host`` 找到对应 ``ata_port``，取得 port lock，再根据 ``scsi_device`` 找到 port 0 上的 ``ata_device``：

.. code-block:: text

   Scsi_Host
   → ata_port
   → ata_link
   → ata_device

固定磁盘在线、没有 error handler 正在运行，device lookup 成功。

READ CDB 怎样找到翻译函数
-------------------------

``__ata_scsi_queuecmd()`` 读取：

.. code-block:: c

   u8 scsi_op = scmd->cmnd[0];

对 ATA disk class，它调用 ``ata_get_xlat_func(dev, scsi_op)``。READ(6)、READ(10) 和 READ(16) 全部返回：

.. code-block:: c

   ata_scsi_rw_xlat

因此上一章保留的 CDB-size 分支在此处重新汇合：

.. code-block:: text

   READ(6) ─┐
   READ(10) ├→ ata_scsi_rw_xlat()
   READ(16) ┘

READ(32)/protection 等特殊命令需要额外 translation 路径；固定场景没有 data-integrity protection，主线使用普通 READ(6/10/16) 集合。

``ata_scsi_translate`` 建立 ``ata_queued_cmd``
--------------------------------------------

libata 调用：

.. code-block:: c

   ata_scsi_translate(dev, scmd, ata_scsi_rw_xlat, ap);

首先由 ``ata_scsi_qc_new()`` 为该 SCSI command 取得一个 ``ata_queued_cmd``，通常简称 ``qc``。它连接：

.. code-block:: text

   ata_queued_cmd
   ├── scsicmd → struct scsi_cmnd
   ├── dev     → ata_device
   ├── ap      → ata_port
   ├── tag / hw_tag
   ├── tf      → ATA taskfile
   ├── sg      → SCSI scatterlist
   └── complete_fn → ata_scsi_qc_complete

因为 ``cmd->sc_data_direction == DMA_FROM_DEVICE``，函数把 SCSI scatterlist 交给 ``ata_sg_init()``，并把 ``qc->dma_dir`` 设置为从设备到内存。

这张 scatterlist 的叶子最终指向第七十六章加入 bio 的 page-cache folio pages。到这里依然没有 user-buffer page，DMA 目标仍是 page cache。

``ata_scsi_rw_xlat`` 怎样提取读范围
----------------------------------

translation function 根据 CDB 类型解析：

.. code-block:: text

   SCSI LBA
   transfer block count
   FUA flag
   duration-limit bits

随后设置：

.. code-block:: c

   qc->flags |= ATA_QCFLAG_IO;
   qc->nbytes = n_block * scmd->device->sector_size;
   ata_build_rw_tf(qc, block, n_block, tf_flags, dld, class);

``ata_build_rw_tf()`` 根据 ATA device IDENTIFY 和运行配置选择真正的 ATA command/protocol，例如：

* 普通 DMA READ；
* 48-bit LBA DMA READ EXT；
* Native Command Queuing 的 READ FPDMA QUEUED；
* 必要时的较旧 PIO 路径。

固定 q35 controller 支持 AHCI/NCQ，但最终是否使用 NCQ 还取决于 QEMU disk 暴露的 queue depth、libata negotiation、request flags 和运行时 device state。固定信息没有锁定这些 IDENTIFY 结果，因此正文保留真实分支。

所有成功分支都会生成完整 ``ata_taskfile``：

.. code-block:: text

   command
   protocol
   LBA low/mid/high
   optional high-order LBA bytes
   sector count
   device flags
   read direction

NCQ 与非 NCQ 在 AHCI 提交点继续汇合；差别是 NCQ 还会登记 ``PxSACT``。

``ata_scsi_qc_issue`` 为什么可能 defer
--------------------------------------

translation 成功后：

.. code-block:: c

   ata_scsi_qc_issue(ap, qc);

libata 先通过 ``qc_defer`` 检查同一 link 上的活动命令是否允许当前协议并行运行：

* NCQ command 可以按 tag 并行；
* non-NCQ command 通常要求 link 上没有其他活动命令；
* error handling、exclusive link 或资源冲突会让命令 defer/requeue。

固定路径选择资源可用且不需要 defer，进入 ``ata_qc_issue()``。

``ata_qc_issue`` 建立 active command 状态
---------------------------------------

函数先验证 tag，并根据协议记录 active 状态：

.. code-block:: text

   NCQ
   → link->sactive |= 1 << hw_tag

   non-NCQ
   → link->active_tag = qc->tag

   both
   → qc->flags |= ATA_QCFLAG_ACTIVE
   → ap->qc_active |= 1ULL << qc->tag

这些 software bitmask 是后续 interrupt handler 判断哪个 command 完成的依据。它们不是 AHCI MMIO ``PxCI`` 或 ``PxSACT`` 本身。

scatterlist 什么时候变成 DMA address
-----------------------------------

当前 task 仍在 CPU 上执行。``ata_qc_issue()`` 看到 data protocol 后调用：

.. code-block:: c

   ata_sg_setup(qc);

底层执行：

.. code-block:: c

   dma_map_sg(ap->dev, qc->sg, qc->n_elem, DMA_FROM_DEVICE);

DMA API 把 CPU page/scatterlist 转换成 AHCI controller 可使用的 DMA addresses，并处理 IOMMU、cache coherency 和 segment 合并。

成功后：

.. code-block:: text

   qc->sg entries
   → sg_dma_address / sg_dma_len valid
   → ATA_QCFLAG_DMAMAP

这里的 DMA mapping 仍然没有启动传输。它只是准备设备可以访问的地址。

AHCI command table 包含什么
---------------------------

``ata_qc_issue()`` 先调用 port operation：

.. code-block:: c

   ap->ops->qc_prep(qc);

q35 AHCI 使用 ``ahci_qc_prep()``。每个 hardware tag 对应 command table 中的一个区域：

.. code-block:: c

   cmd_tbl = pp->cmd_tbl + qc->hw_tag * AHCI_CMD_TBL_SZ;

command table 的第一部分是 Register – Host to Device FIS。``ata_tf_to_fis()`` 把 ATA taskfile 编码成 SATA H2D Register FIS：

.. code-block:: text

   ATA command/protocol fields
   → H2D Register FIS bytes
   → command table header area

若是 ATAPI command，还会填写 32-byte CDB 区域；当前是普通 ATA disk，不走 ATAPI 分支。

PRDT 怎样描述目标 folio
----------------------

``ahci_fill_sg()`` 遍历 DMA-mapped scatterlist，为每个 segment 填写 AHCI Physical Region Descriptor Table（PRDT）entry：

.. code-block:: c

   ahci_sg[si].addr       = lower_32_bits(dma_addr);
   ahci_sg[si].addr_hi    = upper_32_bits(dma_addr);
   ahci_sg[si].flags_size = dma_length - 1;

PRDT 告诉 controller：

.. code-block:: text

   从 SATA device 读取的数据
   → 写入哪些 DMA physical/IOMMU addresses
   → 每段写入多少 bytes

对当前 READ，command header 不设置 ``AHCI_CMD_WRITE``，因为数据方向是 device → memory。

command header/slot 怎样指向 command table
-----------------------------------------

``ahci_qc_prep()`` 计算 command header options：

.. code-block:: text

   command FIS length = 5 dwords
   PRDT entry count
   port-multiplier number
   direction / ATAPI flags

然后调用：

.. code-block:: c

   ahci_fill_cmd_slot(pp, qc->hw_tag, opts);

command slot/header 中写入：

* options；
* transferred-byte status 初值；
* command table DMA address low；
* command table DMA address high。

此时 RAM 中的 AHCI structures 已经完整：

.. code-block:: text

   command list slot[tag]
   → command table DMA address

   command table
   ├── H2D Register FIS
   └── PRDT entries → page-cache folio DMA addresses

这些结构由 Linux 分配在 coherent DMA memory 中，q35 AHCI engine 可以直接读取。

``ahci_qc_issue`` 怎样真正敲响门铃
----------------------------------

准备完成后，``ata_qc_issue()`` 调用：

.. code-block:: c

   ap->ops->qc_issue(qc);

固定 driver 进入 ``ahci_qc_issue()``。

若 taskfile 使用 NCQ，driver 先写：

.. code-block:: c

   writel(1 << qc->hw_tag, port_mmio + PORT_SCR_ACT);

``PxSACT`` 表示哪些 NCQ tag 处于 active 状态。非 NCQ command 不写这一寄存器。

所有路径最终都执行：

.. code-block:: c

   writel(1 << qc->hw_tag, port_mmio + PORT_CMD_ISSUE);

``PORT_CMD_ISSUE`` 对应 AHCI ``PxCI``。将 tag bit 从 0 写成 1 是 CPU 对 controller 的提交动作：

.. code-block:: text

   PxCI[tag] = 1
   → AHCI engine 读取 command header
   → 读取 command table/H2D FIS
   → 读取 PRDT
   → 向 SATA device 发出 ATA READ
   → 将返回数据 DMA 到 folio pages

从这一写开始，hardware 与 CPU 并发运行。``ahci_qc_issue()`` 返回 0 只表示 controller 已接受 command issue bit，不表示磁盘读取已经成功完成。

为什么不能在这里说 folio 已经有数据
----------------------------------

``PxCI`` 写入后可能发生：

* device 正常执行并完成 DMA；
* command 仍在 device queue 中；
* controller 等待 SATA link；
* error interrupt；
* timeout 后进入 libata error handling。

只有 completion path 确认成功，并最终调用 ``folio_end_read(folio, true)``，folio 才会标记 uptodate 并解锁。

因此当前仍然成立：

.. code-block:: text

   AHCI command issued
   ≠ DMA completed
   ≠ folio uptodate
   ≠ user buffer filled
   ≠ read() returned

本章结束时的状态
----------------

本章结束时：

* 当前 task：仍在 ``read()`` 的 kernel process context 中，submission call stack 正在返回；
* blk-mq request：已 started，拥有 tag；
* SCSI command：READ CDB 已交给 libata；
* ata queued command：已分配并标记 active；
* ATA taskfile：已按 negotiated device capability 建立 DMA 或 NCQ READ；
* scatterlist：已执行 ``dma_map_sg(..., DMA_FROM_DEVICE)``；
* AHCI command table：H2D Register FIS 已填写；
* AHCI PRDT：已指向 page-cache folio DMA addresses；
* AHCI command header：已指向对应 command table；
* ``PxSACT``：NCQ 分支已设置对应 tag，non-NCQ 分支不设置；
* ``PxCI``：已写入 ``1 << hw_tag``；
* q35 AHCI engine：可以开始读取 command structures 并访问 SATA disk；
* completion：尚未发生；
* folio：仍可能 locked 且 not uptodate；
* user buffer：尚未执行 ``copy_folio_to_iter()``；
* ``read()``：尚未返回。

下一阶段由 CPU submission 与硬件执行分成两条并发线：当前 reader task 会从 submission stack 返回并在 filemap 中等待 locked folio；AHCI engine/device 完成 DMA 后产生中断。下一批将从 AHCI interrupt handler 汇合这两条线，追踪 ``ata_qc_complete → scsi_done → blk-mq/bio completion → mpage_end_io``。

资料
----

* `Linux 7.2-rc1 drivers/scsi/scsi_lib.c：scsi_dispatch_cmd <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/scsi_lib.c>`_
* `Linux 7.2-rc1 include/linux/libata.h：ata_scsi_queuecmd host template <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/libata.h>`_
* `Linux 7.2-rc1 drivers/ata/libata-scsi.c：SCSI READ translation 与 ata_scsi_queuecmd <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-scsi.c>`_
* `Linux 7.2-rc1 drivers/ata/libata-core.c：ata_sg_setup 与 ata_qc_issue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-core.c>`_
* `Linux 7.2-rc1 drivers/ata/libahci.c：ahci_qc_prep、PRDT、command slot 与 PxCI submission <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libahci.c>`_
* `Linux 7.2-rc1 Documentation/driver-api/libata.rst：libata command lifecycle <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/driver-api/libata.rst>`_