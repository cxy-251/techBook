第七十八章：blk-mq 怎样把 bio 变成 SCSI READ request？
============================================================

第七十七章结束时，READ bio 已经通过 block 层通用校验，分区内 sector 也已加上 ``/dev/sda1`` 的起始偏移，控制权进入：

.. code-block:: c

   blk_mq_submit_bio(bio);

当前仍是发起 ``read(fd, buf, 4096)`` 的 task，在 CPL 0 process context 中执行。bio 只有“操作、磁盘范围、内存 folio”这些描述；blk-mq 现在要把它变成可占用 hardware queue tag、可调度、可交给驱动的 ``struct request``。

本章固定以下成功路径条件：

* 承载目标 folio 的 bio 符合当前 request queue limits，不需要拆分；
* queue alignment 检查通过；
* 没有可与它合并的现有 request；
* queue、SCSI device、target 和 host 都有可用资源；
* 即使 request 暂存于 plug 或 I/O scheduler，也最终被正常 dispatch；
* 不使用 integrity metadata、inline crypto、polling 或 zoned-write 特殊路径。

章节追踪到 SCSI disk 层建立 READ CDB，并停在 ``scsi_dispatch_cmd()`` 准备调用 libata low-level driver 之前。

``blk_mq_submit_bio`` 先取得什么
--------------------------------

函数首先取得：

.. code-block:: c

   struct request_queue *q = bdev_get_queue(bio->bi_bdev);
   struct blk_plug *plug = current->plug;

``request_queue`` 描述这块 SCSI disk 的 queue limits、blk-mq tag set、hardware context、I/O scheduler、request QoS 和底层 ``queue_rq`` callback。

``current->plug`` 是可选的批处理环境。上层在一段代码中预计连续提交多个相邻 I/O 时，可以先把 request 暂存在当前 task 的 plug list，退出 plug 时再统一 merge 和 dispatch。

是否存在 plug 不改变 request 的最终设备路径：

.. code-block:: text

   no plug
   → 直接进入 scheduler/direct issue

   active plug
   → blk_add_rq_to_plug
   → blk_flush_plug
   → scheduler/direct issue

二者最后都必须到达 queue 的 ``queue_rq``。

queue usage reference 为什么先取得
----------------------------------

如果没有可复用的 cached request，``blk_mq_submit_bio()`` 调用 ``bio_queue_enter()``，取得 ``q_usage_counter`` reference。

这个 reference 防止 request 构造和 dispatch 过程中 queue 被 freeze、删除或重配置完成。它不是 request tag，也不表示设备已有空闲 command slot。

alignment 与 queue limits 是两层检查
------------------------------------

函数先检查 bio 的 byte size 与起始地址是否满足 queue 的 logical block size：

.. code-block:: c

   if (bio_unaligned(bio, q))
       bio_io_error(bio);

随后调用：

.. code-block:: c

   bio = __bio_split_to_limits(bio, &q->limits, &nr_segs);

queue limits 可能约束：

* 最大 sectors；
* 最大 segment 数；
* 单个 segment 最大长度；
* DMA boundary；
* virtual boundary；
* physical block alignment；
* discard、zone 或 atomic-write 特殊限制。

若 bio 超限，block layer 会创建一个满足限制的前半 bio，并把剩余部分作为后续 bio 提交。固定场景明确选择“不需要 split”的分支，因此当前 bio 本身继续前进，``nr_segs`` 保存它经过 DMA segment 规则计算后的 segment 数。

这项固定条件约束的是当前 ext4 生成的 bio，不表示所有 readahead bio 永远只有 4096 bytes。readahead 可以聚合多个 folio，只要最终结果仍未超过 q35 AHCI/SCSI queue limits即可。

为什么先尝试 merge
------------------

``blk_mq_attempt_bio_merge()`` 依次尝试：

.. code-block:: text

   plug request merge
   → I/O scheduler request merge

merge 的目标是把相邻、方向相同、属性兼容的 bio 挂入已有 request，减少 request/tag/command 数量。

允许合并至少要求：

* sector 连续或满足前后合并关系；
* operation 与 flags 兼容；
* 总 sectors 和 segments 不超过 queue limits；
* cgroup、integrity、crypto 和 write hint 等属性兼容。

固定路径没有合适的 merge target，因此需要新建 request。不能把“没有 merge”理解为 block layer 没检查 merge。

request 从哪里分配
------------------

``blk_mq_get_new_requests()`` 先执行 request QoS throttle，然后通过：

.. code-block:: c

   __blk_mq_alloc_requests(&data);

从 blk-mq tag set 中取得一个 request。分配过程决定：

* software submission context ``blk_mq_ctx``；
* hardware queue context ``blk_mq_hw_ctx``；
* request tag；
* driver-private command area；
* request 所属 queue；
* operation flags。

对 SCSI queue，request 后面的 driver-private area 包含 ``struct scsi_cmnd`` 以及 inline scatter-gather storage。此时它们只是获得了内存和 tag，SCSI CDB 尚未生成。

``blk_mq_bio_to_request`` 建立所有权关系
---------------------------------------

request 分配成功后：

.. code-block:: c

   blk_mq_bio_to_request(rq, bio, nr_segs);

它把 bio 挂到 request，并建立：

.. code-block:: text

   rq->bio / rq->biotail
   rq starting sector
   rq byte and sector length
   rq physical segment count
   rq operation flags

从这里开始，同一份 I/O 同时存在两个层次的对象：

``struct bio``
   保存 completion chain、folio vectors 和上层 block address。

``struct request``
   保存 queue/tag/scheduling 状态，并作为底层驱动提交单位。

request 完成时仍要沿 ``rq → bio → bi_end_io`` 返回文件系统，不能在生成 request 后丢掉 bio。

未加密 request 为什么不申请 keyslot
----------------------------------

随后执行：

.. code-block:: c

   blk_crypto_rq_get_keyslot(rq);

固定 bio 没有 crypt context，这个 helper 直接成功，不分配 inline-encryption keyslot。调用仍然存在，是为了让加密与未加密 request 使用同一条 blk-mq submission pipeline。

plug、scheduler 与 direct issue 在哪里汇合
-----------------------------------------

request 完成构造后可能进入三类路径：

.. code-block:: text

   active plug
   → blk_add_rq_to_plug()
   → later blk_mq_flush_plug_list()

   I/O scheduler / busy hctx
   → blk_mq_insert_request()
   → blk_mq_run_hw_queue()

   direct issue
   → blk_mq_try_issue_directly()

plug 与 scheduler 影响“什么时候、按什么顺序”调用驱动。它们不改变 SCSI disk 的 queue callback。

固定路径要求 request 最终被成功 dispatch。blk-mq 取得 hardware context 后，通过 queue ops 调用：

.. code-block:: c

   scsi_queue_rq(hctx, &bd);

从这个入口起，request 的设备语义由 SCSI mid-layer 接管。

``scsi_queue_rq`` 先检查资源状态
--------------------------------

``scsi_queue_rq()`` 从 request 找到：

.. code-block:: text

   request_queue
   → scsi_device
   → Scsi_Host
   → request-private scsi_cmnd

它检查：

* ``sdev_state == SDEV_RUNNING``；
* target queue 是否可接收命令；
* host 是否处于 error recovery；
* host queue depth 与 device budget 是否允许继续。

资源不足时返回 ``BLK_STS_RESOURCE`` 或 ``BLK_STS_DEV_RESOURCE``，blk-mq 稍后重新运行 queue。固定路径所有检查通过。

``scsi_prepare_cmd`` 把 request 变成 ``scsi_cmnd``
-------------------------------------------------

首次准备该 request 时：

.. code-block:: c

   scsi_prepare_cmd(req);

它清理并初始化 ``struct scsi_cmnd``，然后根据 request 数据方向设置：

.. code-block:: text

   REQ_OP_READ
   → rq_dma_dir(req)
   → DMA_FROM_DEVICE

SCSI scatterlist storage 已经附在 command-private area 中。最终调用 upper-level disk driver 的：

.. code-block:: c

   sd_init_command(cmd);

这里的 upper-level driver 是 ``sd``，不是 AHCI。``sd`` 负责把 block READ request 表达成标准 SCSI block command；libata 稍后再把 SCSI command 翻译成 ATA taskfile。

``sd_setup_read_write_cmnd`` 怎样计算 LBA
----------------------------------------

``sd_init_command()`` 看到 ``REQ_OP_READ`` 后调用：

.. code-block:: c

   sd_setup_read_write_cmnd(cmd);

它从 request 取得整盘 512-byte sector 坐标，并根据 SCSI device 报告的 logical sector size转换：

.. code-block:: c

   lba = sectors_to_logical(sdp, blk_rq_pos(rq));
   nr_blocks = sectors_to_logical(sdp, blk_rq_sectors(rq));

若 QEMU disk 暴露 512-byte logical sector，则 4096 bytes 对应 8 个 SCSI logical blocks；若设备暴露更大的 logical sector，转换结果相应变化。固定平台尚未锁定 QEMU block backend 的 IDENTIFY logical-sector 参数，正文不能凭 ext4 的 4096-byte block size反推磁盘 logical-sector size。

READ(6)、READ(10) 与 READ(16) 为什么不能随意写死
-----------------------------------------------

``sd`` 根据 LBA、block count、device flags、protection information 与 duration-limit 配置选择：

.. code-block:: text

   READ(6)
   READ(10)
   READ(16)
   或带保护信息的 READ(32)

普通 SATA disk 的小请求通常使用 READ(10)，但固定场景没有锁定磁盘容量、``use_10_for_rw``、``use_16_for_rw`` 和 protection flags，因此本章保留真实选择条件。

无论选择 READ(6)、READ(10) 还是 READ(16)，command 都包含同一核心信息：

* READ opcode；
* 整盘 logical LBA；
* transfer block count；
* FUA/protection 等 flags；
* scatter-gather data length；
* timeout 与 retry policy。

这些 READ CDB 在 libata 中都会汇合到 ``ata_scsi_rw_xlat()``。

SCSI command 什么时候正式开始 dispatch
--------------------------------------

command 准备完成后，``scsi_queue_rq()``：

.. code-block:: c

   blk_mq_start_request(req);
   scsi_dispatch_cmd(cmd);

``blk_mq_start_request()`` 启动 timeout/accounting 状态。它不表示硬件已经接收到命令。

``scsi_dispatch_cmd()`` 再次检查 device/host 状态与 CDB 长度，随后准备调用：

.. code-block:: c

   host->hostt->queuecommand(host, cmd);

q35 AHCI 使用 libata 创建的 SCSI host template，其中 ``queuecommand`` 明确指向 ``ata_scsi_queuecmd``。

本章停在这个 SCSI mid-layer 与 libata low-level driver 的交接点。

本章结束时的状态
----------------

本章结束时：

* 当前 I/O：已经拥有 blk-mq ``struct request`` 与 tag；
* bio：挂在 request 上，保留 ``mpage_end_io`` completion chain；
* split：固定 bio 符合 queue limits，没有被拆分；
* merge：没有合适的已有 request；
* plug/scheduler：若曾暂存，当前 request 已被释放并进入 dispatch；
* blk-mq：request 已开始计时；
* SCSI：``struct scsi_cmnd`` 已初始化；
* data direction：``DMA_FROM_DEVICE``；
* CDB：已由 ``sd`` 建立 READ(6/10/16 等适用形式)；
* libata：``ata_scsi_queuecmd`` 尚未执行；
* AHCI command slot：尚未填写；
* DMA：尚未开始；
* folio：仍未假设 uptodate；
* user buffer：仍未填充；
* ``read()``：仍未返回。

下一入口是 ``drivers/scsi/scsi_lib.c:scsi_dispatch_cmd()`` 对 ``host->hostt->queuecommand`` 的调用；在固定 AHCI host 上，它进入 ``drivers/ata/libata-scsi.c:ata_scsi_queuecmd()``。

资料
----

* `Linux 7.2-rc1 block/blk-mq.c：blk_mq_submit_bio、merge、request allocation 与 dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-mq.c>`_
* `Linux 7.2-rc1 block/blk-merge.c：bio/request limits 与 split/merge <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-merge.c>`_
* `Linux 7.2-rc1 drivers/scsi/scsi_lib.c：scsi_queue_rq、scsi_prepare_cmd 与 scsi_dispatch_cmd <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/scsi_lib.c>`_
* `Linux 7.2-rc1 drivers/scsi/sd.c：sd_init_command 与 SCSI READ CDB 构造 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/sd.c>`_
* `Linux 7.2-rc1 include/linux/libata.h：libata SCSI host template 的 queuecommand <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/libata.h>`_