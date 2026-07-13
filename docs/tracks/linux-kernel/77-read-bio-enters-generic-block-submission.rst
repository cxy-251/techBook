第七十七章：READ bio 怎样通过校验与分区重映射进入 blk-mq？
================================================================

第七十六章结束时，ext4 已经把目标 page-cache folio 放进一个 ``REQ_OP_READ`` bio，并调用：

.. code-block:: c

   blk_crypto_submit_bio(bio);

当前执行者仍是发起 ``read(fd, buf, 4096)`` 的 task，CPU 位于 CPL 0 process context。bio 描述的是“从块设备读取哪些 sector，以及把数据 DMA 到哪些 page”，但尚未生成 blk-mq request。

本章沿固定的未加密、普通分区块设备路径，追踪 bio 怎样经过通用 block submission 校验、把分区内 sector 改成整盘 sector，并进入 ``blk_mq_submit_bio()``。章节停在 blk-mq 开始处理 bio 之前。

未加密 bio 为什么仍经过 ``blk_crypto_submit_bio``
---------------------------------------------------

``blk_crypto_submit_bio()`` 是统一提交入口。它先检查 bio 是否带有 ``bio_crypt_ctx``：

.. code-block:: c

   if (!bio_has_crypt_ctx(bio) || __blk_crypto_submit_bio(bio))
       submit_bio(bio);

固定场景排除了 fscrypt 和 inline encryption，因此 ``bio_has_crypt_ctx(bio)`` 为 false。这里不会分配 keyslot、不会创建 fallback bio，也不会执行软件解密，直接调用普通 ``submit_bio()``。

必须区分：

.. code-block:: text

   文件没有加密
   → 跳过 blk-crypto transformation
   → 继续进入普通 block layer

   文件没有加密
   ≠ 绕过 block layer

``submit_bio`` 先记录 I/O accounting
-------------------------------------

``submit_bio()`` 对 READ 执行：

.. code-block:: c

   task_io_account_read(bio->bi_iter.bi_size);
   count_vm_events(PGPGIN, bio_sectors(bio));
   bio_set_ioprio(bio);
   submit_bio_noacct(bio);

这些动作分别把本次读取计入当前 task、VM page-in 统计，并在上层没有显式设置 I/O priority 时从当前 task 初始化 ``bi_ioprio``。

这里没有等待磁盘，也没有增加 ``read()`` 的返回值。accounting 表示请求已经提交到 block 层，不表示数据已经到达内存。

``submit_bio_noacct`` 校验设备与操作
------------------------------------

``submit_bio_noacct()`` 取得：

.. code-block:: c

   struct block_device *bdev = bio->bi_bdev;
   struct request_queue *q = bdev_get_queue(bdev);

随后依次处理：

* ``REQ_NOWAIT`` 是否被设备支持；
* crypto context 是否可用；
* fault-injection 是否主动制造失败；
* read-only 状态；
* sector 是否越过设备或分区末尾；
* 分区 sector 是否需要转换成整盘 sector；
* operation 是否受该 queue 支持；
* block-cgroup throttling。

固定路径没有 ``REQ_NOWAIT``，没有 crypt context，没有 fault injection，请求也没有越过 ``/dev/sda1`` 的末尾。``bio_check_ro()`` 只对写请求发出只读设备警告，当前 READ 不受影响。

本章进一步固定：当前 bio 没有被 block-cgroup throttle 延迟。若 cgroup I/O policy 决定节流，``blk_throtl_bio()`` 会消费 bio，并在以后重新提交；那是另一个调度时刻，不改变后续 request 构造机制。

分区 sector 为什么必须加 ``bd_start_sect``
------------------------------------------

ext4 在第七十六章产生的 sector 是相对于文件系统所在 block device 的地址。固定文件系统位于第一分区 ``/dev/sda1``，该分区从整盘 LBA 2048 开始。

``blk_partition_remap()`` 执行：

.. code-block:: c

   bio->bi_iter.bi_sector += p->bd_start_sect;
   bio_set_flag(bio, BIO_REMAPPED);

因此地址关系是：

.. code-block:: text

   ext4 physical block
   → partition-relative 512-byte sector
   → + 2048
   → whole-disk sector

例如，若 ext4 映射结果对应分区内 sector ``S``，AHCI 最终看到的是整盘 sector ``S + 2048``。

``BIO_REMAPPED`` 防止同一个 bio 在递归提交或 stacked-device 路径中被重复加上分区偏移。这里的 remap 只改变块地址坐标，不重新执行 ext4 extent lookup，也不进行数据复制。

READ operation 怎样通过类型检查
--------------------------------

``submit_bio_noacct()`` 对 ``bio_op(bio)`` 做 operation-specific 检查。当前命中：

.. code-block:: c

   case REQ_OP_READ:
       break;

discard、secure erase、zone append、write zeroes 等操作需要额外设备能力；普通 READ 只需通过前面的范围和 queue 状态检查。

随后：

.. code-block:: c

   if (blk_throtl_bio(bio))
       return;
   submit_bio_noacct_nocheck(bio, false);

固定场景不被 throttle，因此进入 ``submit_bio_noacct_nocheck()``。

为什么还有一个 ``nocheck`` 层
-----------------------------

``submit_bio_noacct_nocheck()`` 表示 operation、范围和设备状态已经检查完成。它继续执行：

.. code-block:: text

   blk_cgroup_bio_start
   → block bio queue tracepoint
   → 设置 BIO_TRACE_COMPLETION
   → 选择递归 bio-list 或底层提交路径

``BIO_TRACE_COMPLETION`` 让 block trace 在 bio 完成时也能记录对应事件。``blk_cgroup_bio_start()`` 建立 cgroup I/O accounting 生命周期；它不等同于前面的 throttling decision。

``current->bio_list`` 为什么存在
--------------------------------

stacked block driver 的 ``submit_bio`` 回调可能在处理一个 bio 时递归提交新的下层 bio。直接进行 C 递归会让深层 device-mapper、RAID 或 encryption stack 消耗不可控的 kernel stack。

block layer 因此使用 ``current->bio_list``：

.. code-block:: text

   当前 bio 进入 __submit_bio()
   → driver 若递归提交下层 bio
   → 新 bio 放入 current->bio_list
   → 当前回调返回后由循环继续处理

``__submit_bio_noacct()`` 还会把新 bio 按“更低层 queue”和“同一层 queue”排序，优先推进最底层请求。

固定路径是 ext4 直接提交给普通 SCSI disk queue，没有 device-mapper、MD RAID 或自定义 ``gendisk->submit_bio``。当前 ``current->bio_list`` 为空，block device 也没有设置 ``BD_HAS_SUBMIT_BIO``，因此使用简化的 mq 循环：

.. code-block:: c

   __submit_bio_noacct_mq(bio);

``__submit_bio`` 怎样选择 blk-mq
--------------------------------

底层分派函数检查 block device 是否提供自定义 ``submit_bio``：

.. code-block:: c

   if (!bdev_test_flag(bio->bi_bdev, BD_HAS_SUBMIT_BIO))
       blk_mq_submit_bio(bio);
   else
       disk->fops->submit_bio(bio);

普通 SCSI disk 使用 request-based blk-mq queue，不实现 filesystem-facing 自定义 bio submission。因此控制权进入：

.. code-block:: c

   blk_mq_submit_bio(bio);

从这里开始，bio 才会经过 queue limits、split/merge、tag allocation，并成为 ``struct request``。

本章没有发生哪些动作
--------------------

到达 ``blk_mq_submit_bio()`` 时：

* 没有保证 bio 已经分配 request；
* 没有保证请求已进入 I/O scheduler；
* 没有构造 SCSI CDB；
* 没有生成 ATA taskfile；
* 没有填写 AHCI command table；
* 没有执行 DMA；
* 没有完成 folio；
* 没有向用户 buffer 复制数据。

分区 remap 和 block submission validation 只是把 bio 变成一个可以交给具体 request queue 的合法整盘 I/O 描述。

本章结束时的状态
----------------

本章结束时：

* 当前执行者：发起 ``read()`` 的 task；
* CPU mode：x86-64 CPL 0，process context；
* bio operation：``REQ_OP_READ``；
* bio size：至少包含当前 4096-byte 目标读取，readahead 可能包含更多 folio；
* block address：已经从 ``/dev/sda1`` 分区内 sector 重映射到整盘 sector；
* bio flags：已标记 ``BIO_REMAPPED`` 和 completion tracing；
* block cgroup：submission accounting 已开始，固定路径未被 throttle 延迟；
* crypto：没有 crypt context，不需要 transformation 或 keyslot；
* request：尚未建立；
* SCSI/AHCI：尚未接管；
* user buffer：尚未填充；
* ``read()``：尚未返回。

下一入口是 ``block/blk-mq.c:blk_mq_submit_bio()``，继续检查 queue limits、尝试 merge、分配 blk-mq request，并决定 plug、I/O scheduler 或直接 dispatch 路径。

资料
----

* `Linux 7.2-rc1 include/linux/blk-crypto.h：blk_crypto_submit_bio <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/blk-crypto.h>`_
* `Linux 7.2-rc1 block/blk-core.c：submit_bio、submit_bio_noacct 与递归 bio-list <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-core.c>`_
* `Linux 7.2-rc1 include/linux/blkdev.h：block_device、request_queue 与 submission 接口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/blkdev.h>`_
* `Linux 7.2-rc1 block/blk-cgroup.c：bio cgroup accounting <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-cgroup.c>`_
* `Linux 7.2-rc1 block/blk-mq.c：blk_mq_submit_bio <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-mq.c>`_