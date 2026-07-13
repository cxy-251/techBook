项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-079

最新三章：

#. ``LK-READ-077``：READ bio 怎样通过校验与分区重映射进入 blk-mq？
#. ``LK-READ-078``：blk-mq 怎样把 bio 变成 SCSI READ request？
#. ``LK-READ-079``：SCSI READ 怎样变成 ATA taskfile 并写入 AHCI command slot？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

固定来源
--------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux release     = 7.2-rc1
   Linux repository  = gregkh/linux
   Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d

固定 Linux commit ``7404ce51637231382873d0b55edabc2f3b841a9d`` 的 ``Makefile`` 标识为 ``7.2-rc1``。旧章节中残留的 ``Linux 6.12.95`` 只是历史显示标签错误；技术事实继续以固定 commit 为权威来源。

固定运行期场景
--------------

::

   userspace call       = read(fd, buf, 4096)
   ABI                  = native x86-64 SYSCALL / entry_SYSCALL_64
   file                 = already-open regular ext4 file on /dev/sda1
   f_pos                = 0
   filesystem block     = 4096 bytes
   I/O                  = buffered; not O_DIRECT; not DAX
   file features        = no inline data, fscrypt, fs-verity, integrity metadata
   page cache           = target index 0 absent
   readahead            = synchronous readahead covers target folio
   extent               = logical block 0 mapped to an existing physical block
   user buffer          = mapped and writable
   partition            = /dev/sda1 starts at whole-disk LBA 2048
   block submission     = no injected failure or blk-cgroup throttle delay
   queue limits         = target bio fits and is not split
   merge                = no compatible request
   dispatch             = plug/elevator/direct paths eventually dispatch successfully

磁盘 logical-sector size、``sd`` 的 READ(6/10/16) 选择和 libata 的 DMA/NCQ negotiation 取决于没有完全锁定的 QEMU backend/IDENTIFY 状态。正文保留这些真实分支，并在 ``ata_scsi_rw_xlat``、``ahci_qc_prep`` 和 ``PxCI`` 处重新汇合。

当前控制流位置
--------------

第七十七至七十九章已经完成：

::

   ext4 blk_crypto_submit_bio(bio)
   → no crypt context
   → submit_bio()
   → task/VM I/O accounting
   → submit_bio_noacct()
   → validate operation, range and queue support
   → partition remap: sector += /dev/sda1 bd_start_sect (2048)
   → block-cgroup accounting and bio queue trace
   → request-based device selects blk_mq_submit_bio()

   → queue usage reference
   → alignment and queue-limit checks
   → fixed path: no bio split
   → fixed path: no merge target
   → allocate blk-mq request and tag
   → blk_mq_bio_to_request()
   → plug/elevator/direct issue convergence
   → scsi_queue_rq()
   → SCSI device/target/host resource checks
   → scsi_prepare_cmd()
   → DMA_FROM_DEVICE
   → sd_init_command()
   → applicable READ(6), READ(10), or READ(16) CDB
   → blk_mq_start_request()
   → scsi_dispatch_cmd()

   → ata_scsi_queuecmd()
   → ata_get_xlat_func()
   → ata_scsi_rw_xlat()
   → ata_build_rw_tf()
   → ATA DMA or NCQ read taskfile
   → ata_scsi_qc_issue()
   → ata_qc_issue()
   → mark ata_queued_cmd active
   → dma_map_sg(..., DMA_FROM_DEVICE)
   → ahci_qc_prep()
   → H2D Register FIS
   → AHCI PRDT entries
   → AHCI command header and command table address
   → optional PxSACT[tag] for NCQ
   → PxCI[tag] = 1

当前精确边界
------------

CPU 已经执行：

.. code-block:: c

   writel(1 << qc->hw_tag, port_mmio + PORT_CMD_ISSUE);

该寄存器对应 AHCI ``PxCI``。此写入允许 q35 AHCI engine 读取 RAM 中的 command header、command table、H2D Register FIS 和 PRDT，并向 SATA device 发出 ATA READ。

此刻存在两条并发线：

::

   CPU / reader task
   → 从 ahci_qc_issue 和 submission stack 返回
   → 回到 filemap
   → 在目标 folio 仍 locked 时等待

   q35 AHCI engine / SATA device
   → fetch command structures
   → execute ATA READ
   → DMA data into page-cache folio pages
   → raise completion interrupt

此刻机器状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* 当前 read task：仍处于 syscall 的 kernel process context；
* CPU mode：CPL 0；
* blk-mq request：已 started，拥有 request tag；
* bio：仍挂在 request 上，``bi_end_io`` 链最终指向 ext4 ``mpage_end_io``；
* SCSI command：READ CDB 已生成并提交给 libata；
* ata queued command：已分配、带 tag，并标记 active；
* ATA taskfile：已按 negotiated device capability 选择 DMA 或 NCQ read；
* data direction：device → memory；
* DMA mapping：folio scatterlist 已转换成 controller 可访问地址；
* AHCI H2D FIS：已写入 command table；
* AHCI PRDT：已指向 page-cache folio pages；
* AHCI command header：已填写 PRDT count、FIS length 和 command-table DMA address；
* ``PxSACT``：只在 NCQ 分支设置；
* ``PxCI``：对应 hardware tag bit 已置位；
* AHCI completion：尚未处理；
* target folio：不能视为 uptodate，通常仍 locked；
* user buffer：尚未执行 ``copy_folio_to_iter()``；
* file position：尚未提交新的 ``f_pos``；
* syscall return value：尚未确定；
* ``read()``：尚未返回用户态。

关键边界
--------

必须继续分开：

#. ``submit_bio()`` 表示 I/O 已交给 block layer，不表示 request 已建立；
#. ``blk_mq_bio_to_request()`` 建立 request，不表示 SCSI command 已生成；
#. ``sd_init_command()`` 建立 SCSI CDB，不表示 SATA hardware 使用 SCSI protocol；
#. ``ata_scsi_rw_xlat()`` 把 SCSI block command 翻译为 ATA taskfile；
#. ``dma_map_sg()`` 准备 DMA addresses，不启动 DMA；
#. ``ahci_qc_prep()`` 填写 command structures，不启动 command；
#. ``PxCI[tag] = 1`` 启动 hardware command，不表示 completion；
#. storage DMA 写入 page-cache folio，不直接写用户 buffer；
#. folio 只有在 completion callback 成功执行 ``folio_end_read(..., true)`` 后才是 uptodate；
#. reader task 与 hardware completion 是并发控制流，最终在 folio unlock/wakeup 处汇合。

当前下一步
----------

下一批从 AHCI completion IRQ 开始。interrupt delivery 可能采用 legacy INTx、MSI 或 MSI-X，固定配置没有锁定具体入口；各路径在 libahci port handling 中汇合：

::

   AHCI IRQ entry
   → read HOST_IRQ_STAT / port interrupt status
   → ahci_handle_port_intr()
   → ahci_port_intr()
   → compare PxCI/PxSACT with software active masks
   → determine completed tag
   → ata_qc_complete()
   → ata_scsi_qc_complete()
   → scsi_done()
   → blk_mq_complete_request()
   → scsi_complete()/scsi_finish_command()
   → end blk-mq request
   → bio_endio
   → mpage_end_io
   → folio_end_read(success)
   → folio uptodate and unlocked

随后继续 reader task：

::

   folio waiter wakes
   → filemap_get_pages()
   → filemap_read()
   → copy_folio_to_iter(user buffer)
   → ki_pos update
   → ksys_read commits file->f_pos
   → syscall return value
   → syscall_exit_to_user_mode()
   → SYSRETQ or IRETQ

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。