第八十章：AHCI 中断怎样确认完成的 tag，并把结果交回 SCSI？
==============================================================

第七十九章结束时，CPU 已经把当前 ATA command 的 hardware tag 写入 q35 ICH9 AHCI port 0 的 ``PxCI``：

.. code-block:: c

   writel(1 << qc->hw_tag, port_mmio + PORT_CMD_ISSUE);

此后 AHCI engine 读取 command header、H2D Register FIS 与 PRDT，SATA device 执行 READ，controller 按 PRDT 把数据 DMA 到 page-cache folio 对应的内存。

本章固定成功完成路径：没有 ATA device error、host bus error、timeout、hotplug 或 error-handler 接管。章节从 completion interrupt 开始，追到 libata 调用 ``scsi_done()``，并让 blk-mq 开始处理 request completion。

硬件完成与 reader task 是两条控制流
------------------------------------

提交之后，发起 ``read()`` 的 task 会沿 submission call stack 返回；设备则独立执行命令：

.. code-block:: text

   reader task / CPU
   → 从 ahci_qc_issue() 返回
   → 回到 filemap 路径
   → 发现目标 folio 尚未解锁时等待

   q35 AHCI engine / SATA disk
   → fetch command structures
   → execute ATA READ
   → DMA data into page-cache folio
   → clear completed command state
   → set interrupt status
   → raise interrupt

所以 completion handler 执行时，``current`` 不一定是发起读取的 task。中断可能落在任意接收该 IRQ 的 CPU 上；真正的 reader 只会在 folio 解锁以后重新进入 runnable 状态。

为什么不固定 INTx、MSI 或 MSI-X 入口
------------------------------------

AHCI controller 可以按运行配置使用 legacy INTx、MSI 或 MSI-X。固定平台只规定 q35 ICH9 AHCI，没有锁定最终 interrupt mode，因此不能虚构唯一的最外层 IRQ symbol。

不同入口最终会汇合到 libahci 的 port handling：

.. code-block:: text

   legacy/shared IRQ ─┐
   MSI                ├→ read host/port interrupt status
   MSI-X per-port     ┘→ ahci_handle_port_interrupt()

共享中断路径先读取 host-wide ``HOST_IRQ_STAT``，找出发生事件的 port，再调用 ``ahci_handle_port_intr()``。per-port 路径可以直接读取对应 port 的 ``PORT_IRQ_STAT``。两者都会清除已观察到的 interrupt status，并进入：

.. code-block:: c

   ahci_handle_port_interrupt(ap, port_mmio, status);

``PxIS`` 为什么要先读取再清除
----------------------------

``ahci_port_intr()`` 的核心动作是：

.. code-block:: c

   status = readl(port_mmio + PORT_IRQ_STAT);
   writel(status, port_mmio + PORT_IRQ_STAT);
   ahci_handle_port_interrupt(ap, port_mmio, status);

AHCI ``PxIS`` 使用 write-one-to-clear 语义。driver 先保存 status，再把相同 bit 写回清除 latch，随后根据保存值判断是正常完成、SDB FIS、taskfile error、host-bus error 还是 link change。

固定路径没有 ``PORT_IRQ_ERROR``，因此不会进入 ``ahci_error_intr()``、port freeze 或 libata error handling。handler 直接处理已完成 command。

硬件不会直接传回“完成 tag 列表”
--------------------------------

软件在提交时保存了：

.. code-block:: text

   ap->qc_active
   → 所有软件认为仍在 flight 的 ata_queued_cmd tag

   link->sactive
   → NCQ active tags

   link->active_tag
   → non-NCQ active tag

硬件侧则通过 ``PxSACT`` 和 ``PxCI`` 暴露仍然 active 的 command。成功完成后，对应 bit 不再出现在硬件 active mask 中。

``ahci_qc_complete()`` 根据协议读取当前硬件状态：

* NCQ 路径主要读取 ``PxSACT``；
* non-NCQ 路径读取 ``PxCI``；
* FBS 等组合状态下会合并 ``PxSACT`` 与 ``PxCI``。

得到的 ``qc_active`` 表示“硬件此刻仍认为 active 的 tag”，不是“已经完成的 tag”。

``done_mask`` 怎样计算
----------------------

libahci 调用：

.. code-block:: c

   ata_qc_complete_multiple(ap, qc_active);

libata 读取旧的软件 active mask：

.. code-block:: c

   ap_qc_active = ap->qc_active;
   done_mask = ap_qc_active ^ qc_active;

在合法状态转换中，硬件 active mask 只能从 1 变成 0。于是：

.. code-block:: text

   software old active = 1
   hardware new active = 0
   XOR                 = 1  → completed tag

若 ``done_mask`` 中还包含硬件 active bit，说明状态出现非法的 0→1 转换，driver 会把它视为 host-state-machine 错误，而不是盲目完成 request。

固定场景只有当前 READ tag 完成，因此 ``done_mask`` 至少包含该 ``qc->tag``。

``ata_qc_complete_multiple`` 怎样逐个完成 command
--------------------------------------------------

函数遍历 ``done_mask``：

.. code-block:: c

   tag = __ffs64(done_mask);
   qc = ata_qc_from_tag(ap, tag);
   ata_qc_complete(qc);

NCQ 分支还可以先从 SDB FIS 填写完成 command 的 result taskfile。普通成功 READ 没有 error mask，不需要进入 ATA error handler。

这里完成的是 ``struct ata_queued_cmd``，尚未直接完成 bio。数据结构仍按以下关系连接：

.. code-block:: text

   ata_queued_cmd
   → scsi_cmnd
   → blk-mq request
   → bio
   → page-cache folio

``ata_qc_complete`` 为什么先解除 DMA mapping
--------------------------------------------

``ata_qc_complete()`` 最终进入 ``__ata_qc_complete()``。对已经 DMA-map 的 data command，它首先调用：

.. code-block:: c

   ata_sg_clean(qc);

底层执行 ``dma_unmap_sg()``，完成 DMA API 对该 mapping 的收尾。根据架构和平台，这一步负责 IOMMU mapping 回收以及必要的 DMA/CPU coherency 同步。

因此顺序是：

.. code-block:: text

   device DMA finished
   → driver detects completed tag
   → dma_unmap_sg()
   → upper layers may consume memory data

不能把 ``dma_map_sg()`` 和 ``dma_unmap_sg()`` 仅理解成地址转换函数；它们还是 DMA ownership/coherency 协议的一部分。

libata 怎样清除 active 状态
---------------------------

``__ata_qc_complete()`` 根据协议清理 software state：

.. code-block:: text

   NCQ
   → link->sactive &= ~(1 << hw_tag)

   non-NCQ
   → link->active_tag = ATA_TAG_POISON

   both
   → ap->qc_active &= ~(1ULL << qc->tag)
   → qc->flags 清除 ATA_QCFLAG_ACTIVE

完成后，这个 tag 可以在后续 request 中重新使用；当前 command 不再属于 controller 的 active set。

``complete_fn`` 怎样回到 SCSI
-----------------------------

第七十九章建立 ``ata_queued_cmd`` 时已经登记：

.. code-block:: text

   qc->complete_fn = ata_scsi_qc_complete

所以 ``__ata_qc_complete()`` 最后调用：

.. code-block:: c

   qc->complete_fn(qc);

固定成功路径进入 ``ata_scsi_qc_complete()``。它检查 ATA error state；当前 ``qc->err_mask == 0``，无需生成 sense data，随后执行 ``ata_scsi_qc_done()``：

.. code-block:: text

   release ata_queued_cmd tag/state
   → preserve successful SCSI result
   → call qc->scsidone(scsi_cmnd)

``qc->scsidone`` 对普通 SCSI block command 指向 ``scsi_done()``。

``scsi_done`` 为什么还不等于 bio completion
------------------------------------------

``scsi_done()`` 防止同一个 command 被重复完成，记录 SCSI dispatch completion，然后调用：

.. code-block:: c

   blk_mq_complete_request(req);

这只是把已完成的 device command 交给 blk-mq completion machinery。后面仍要执行：

.. code-block:: text

   SCSI result disposition
   → successful byte count
   → blk_update_request()
   → bio_endio()
   → ext4 mpage_end_io()
   → folio_end_read()

因此在本章结束点：

* SATA device 已成功完成 READ；
* DMA data 已写入 page-cache folio pages；
* AHCI/libata active tag 已清除；
* SCSI command 已报告完成；
* blk-mq completion 已被触发；
* bio 的 ``bi_end_io`` 尚未在本章展开；
* folio 尚未在叙事上完成 ``PG_uptodate`` 与 unlock；
* reader task 尚未复制数据到用户 buffer。

本章结束时的状态
----------------

本章结束时：

* 执行环境：AHCI completion IRQ 及其 blk-mq completion 调度上下文；
* 当前 task：不保证是发起 ``read()`` 的 reader；
* AHCI ``PxCI/PxSACT``：当前 tag 已从硬件 active mask 消失；
* ``ap->qc_active``：对应 software bit 已清除；
* DMA mapping：已经 ``dma_unmap_sg()``；
* ATA command：成功完成，没有进入 error handler；
* SCSI command：已经调用 ``scsi_done()``；
* blk-mq request：completion processing 已开始；
* bio：仍需由 block/SCSI completion 结束；
* target folio：数据已由 DMA 写入，但必须等待 ``folio_end_read(..., true)`` 才能正式视为 uptodate 并唤醒 waiters；
* user buffer：尚未复制；
* ``read()``：尚未返回。

下一入口从 blk-mq 的 SCSI completion callback 继续，追踪 ``scsi_complete()``、``scsi_finish_command()``、``blk_update_request()``、``bio_endio()`` 和 ext4 ``mpage_end_io()``。

资料
----

* `Linux 7.2-rc1 drivers/ata/libahci.c：AHCI IRQ、port status 与 command completion <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libahci.c>`_
* `Linux 7.2-rc1 drivers/ata/libata-sata.c：ata_qc_complete_multiple <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-sata.c>`_
* `Linux 7.2-rc1 drivers/ata/libata-core.c：ata_qc_complete 与 DMA unmap <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-core.c>`_
* `Linux 7.2-rc1 drivers/ata/libata-scsi.c：ata_scsi_qc_complete 与 scsi_done handoff <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/ata/libata-scsi.c>`_
* `Linux 7.2-rc1 drivers/scsi/scsi_lib.c：scsi_done 与 blk-mq completion <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/scsi_lib.c>`_