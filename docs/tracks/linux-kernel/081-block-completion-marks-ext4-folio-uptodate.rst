第八十一章：blk-mq completion 怎样结束 bio，并让 ext4 folio 变成 uptodate？
============================================================================

第八十章结束时，AHCI 已确认当前 tag 完成，libata 已解除 DMA mapping、清理 ATA active state，并通过 ``scsi_done()`` 调用：

.. code-block:: c

   blk_mq_complete_request(req);

此时数据已经由 q35 AHCI engine DMA 到 page-cache folio 对应的内存，但 folio 仍需要经过 block、SCSI、bio 和 ext4 completion protocol，才能设置 ``PG_uptodate``、清除 ``PG_locked`` 并唤醒等待者。

本章固定成功路径，追到：

.. code-block:: text

   scsi_complete
   → scsi_finish_command
   → scsi_io_completion
   → scsi_end_request
   → blk_update_request
   → bio_endio
   → mpage_end_io
   → folio_end_read(folio, true)

章节停在 folio 已经 uptodate 并 unlock；reader task 何时重新获得 CPU 以及怎样复制到用户 buffer，留到下一章。

blk-mq completion 在什么上下文执行
---------------------------------

``blk_mq_complete_request()`` 可以根据 request 的 completion affinity、CPU 状态和 queue 配置，直接或间接安排完成处理。最终会调用 request 对应的 completion callback。

SCSI queue 将这个 callback 设置为：

.. code-block:: text

   scsi_complete(struct request *rq)

因此 completion 可能仍处在 interrupt-related context，也可能经过 blk-mq 的 completion redirection。正文不把它写死为 reader task 的 process context。

``scsi_complete`` 先决定成功、重试还是错误恢复
---------------------------------------------

``scsi_complete()`` 从 request private data 取回：

.. code-block:: c

   struct scsi_cmnd *cmd = blk_mq_rq_to_pdu(rq);

随后根据 ``cmd->result``、sense data、host byte 与 device state 调用 ``scsi_decide_disposition()``。主要结果包括：

* ``SUCCESS``：正常结束 request；
* ``NEEDS_RETRY``：重新排队；
* ``ADD_TO_MLQUEUE``：设备/target busy；
* 其他结果：交给 SCSI error handler。

固定场景没有 ATA/SCSI error，``cmd->result`` 表示成功，disposition 为 ``SUCCESS``，因此执行：

.. code-block:: c

   scsi_finish_command(cmd);

这一步很重要：AHCI IRQ 只说明低层 command 完成，SCSI mid-layer 仍有权根据 result 选择重试或 error recovery。只有 ``SUCCESS`` 才进入本章主线。

``scsi_finish_command`` 怎样计算成功字节数
------------------------------------------

``scsi_finish_command()`` 先解除 SCSI device/target/host busy accounting，让新的命令有机会进入 queue。

随后它计算：

.. code-block:: c

   good_bytes = scsi_bufflen(cmd);

对于普通 SCSI disk，upper-level driver 的 ``done`` callback 可以根据 residual、sense 或设备特殊语义修正成功长度。当前 READ 完整成功，没有 residual，因此：

.. code-block:: text

   good_bytes = 4096

然后调用：

.. code-block:: c

   scsi_io_completion(cmd, good_bytes);

这里的 4096 是 block request 已成功处理的字节数，还不是系统调用最终返回值。后续 user copy 仍可能失败或只复制部分数据。

``scsi_io_completion`` 为什么支持 partial completion
----------------------------------------------------

一个 ``struct request`` 可能包含多个 bio，也可能被设备分段完成。``scsi_io_completion()`` 因而不能简单释放整个 request，而是调用：

.. code-block:: c

   scsi_end_request(req, BLK_STS_OK, good_bytes);

固定 request 对应当前成功 READ，4096 bytes 覆盖目标 bio 的全部数据。若 request 仍有剩余 bytes，SCSI 可以继续或重新排队；本场景没有剩余。

``blk_update_request`` 怎样推进 bio
----------------------------------

``scsi_end_request()`` 首先执行：

.. code-block:: c

   blk_update_request(req, error, bytes);

``blk_update_request()`` 遍历 ``req->bio`` 链，对当前 bio 计算：

.. code-block:: c

   bio_bytes = min(bio->bi_iter.bi_size, nr_bytes);

固定 bio 的有效读取范围是 4096 bytes，因此函数：

#. 保持 ``bio->bi_status == BLK_STS_OK``；
#. 把 request 的 ``req->bio`` 推进到下一个 bio；
#. 调用 ``bio_advance(bio, 4096)``，令该 bio 的剩余 size 变为 0；
#. 对已经完全处理的 bio 调用 ``bio_endio(bio)``。

这里存在两个不同的“完成”：

.. code-block:: text

   request byte completion
   → blk_update_request() 推进 request/bio iterator

   bio semantic completion
   → bio_endio() 调用 filesystem 注册的 bi_end_io

request 可以包含多个 bio，因此两者不能混为一个动作。

``bio_endio`` 做了哪些通用收尾
-----------------------------

``bio_endio()`` 先处理 bio chaining、integrity、zone、request-QoS、block-cgroup 与 trace completion。只有 chain 的最终成员完成时，才调用真正的：

.. code-block:: c

   bio->bi_end_io(bio);

第七十六章构造 ext4 READ bio 时登记的是：

.. code-block:: text

   bio->bi_end_io = mpage_end_io

因此 block layer 不知道 folio 的 ext4/page-cache 语义。它只负责报告 bio 成功或失败，然后通过 function pointer 把所有权交回 filesystem。

``mpage_end_io`` 为什么还保留 post-read 分支
------------------------------------------

ext4 的 ``mpage_end_io()`` 先检查该 bio 是否需要 post-read processing：

.. code-block:: text

   fscrypt decrypt
   fs-verity verify

固定场景明确排除 fscrypt 和 fs-verity，因此 ``bio_post_read_required(bio)`` 为 false，直接进入：

.. code-block:: c

   __read_end_io(bio);

若启用了 encryption 或 verity，I/O completion 不会立刻把 folio 标记为 uptodate；必须先在相应 workqueue 完成 decrypt/verify。固定主线跳过这些分支并不代表它们不存在。

``__read_end_io`` 怎样找到 folio
-------------------------------

函数遍历 bio 描述的所有 folio：

.. code-block:: c

   bio_for_each_folio_all(fi, bio)
       folio_end_read(fi.folio, bio->bi_status == 0);

当前 ``bio->bi_status == BLK_STS_OK``，因此传入：

.. code-block:: c

   folio_end_read(folio, true);

随后释放可能存在的 post-read context，并调用 ``bio_put()`` 释放 bio reference。

``folio_end_read`` 怎样同时设置 uptodate 和 unlock
-------------------------------------------------

``folio_end_read()`` 是 page cache 对 filesystem read completion 的统一入口。成功时，它构造 bit mask：

.. code-block:: text

   clear PG_locked
   set   PG_uptodate

并通过原子 flag 更新完成状态转换。若 folio 上存在 waiters，还调用 ``folio_wake_bit(folio, PG_locked)``。

因此 successful completion 的可见顺序是：

.. code-block:: text

   DMA data visible to CPU
   → bio success propagated to ext4
   → PG_uptodate set
   → PG_locked cleared
   → waiters woken

waiter 被唤醒意味着它可以重新进入 runqueue，不表示它会在 interrupt handler 尚未返回前立即执行。scheduler 决定 reader task 何时重新获得 CPU。

为什么不能只调用 ``folio_unlock``
---------------------------------

``folio_unlock()`` 只清除 lock 并唤醒等待者。read completion 还必须说明数据是否有效：

* 成功：设置 ``PG_uptodate`` 后 unlock；
* 失败：不设置 ``PG_uptodate``，仅 unlock，让读取路径发现错误或重新读取。

``folio_end_read(folio, success)`` 把这两个动作绑定，避免 waiter 看到“已经 unlock，但成功状态尚未发布”的中间状态。

request 什么时候真正释放
------------------------

``blk_update_request()`` 完成最后一个 bio 后返回 false，表示 request 已没有剩余数据。``scsi_end_request()`` 随后执行：

.. code-block:: text

   scsi_mq_uninit_cmd()
   → release SCSI scatterlist/driver command state
   → __blk_mq_end_request()
   → finish accounting
   → release blk-mq tag
   → return request to allocator

注意，``bio_endio()`` 与 folio wakeup 发生在 ``blk_update_request()`` 中，而 request/tag 的最终释放在后面的 ``__blk_mq_end_request()``。上层 waiter 可以被标记 runnable，同时底层 completion stack 仍在进行资源收尾。

此刻 reader task 看到了什么
--------------------------

reader 在 ``filemap_get_pages()`` 中可能曾遇到目标 folio：

.. code-block:: text

   folio exists in mapping->i_pages
   PG_locked = 1
   PG_uptodate = 0

它通过 folio lock wait path 睡眠。现在 completion 已经把状态变为：

.. code-block:: text

   folio exists in mapping->i_pages
   PG_locked = 0
   PG_uptodate = 1
   data bytes = storage content read by AHCI DMA

reader 被唤醒后通常重新查找/验证 folio，而不是从 interrupt handler 直接跳到 ``copy_folio_to_iter()``。

本章结束时的状态
----------------

本章结束时：

* 执行环境：blk-mq/SCSI/bio completion，可能处在 interrupt-related completion context；
* SCSI result：成功，成功字节数为 4096；
* blk-mq request：所有 bytes 已完成，request/tag 正在或已经释放；
* bio：已经执行 ``bio_endio()`` 与 ext4 ``mpage_end_io()``；
* ext4 post-read：固定场景无需 decrypt/verity；
* target folio：``PG_uptodate = 1``；
* target folio：``PG_locked = 0``；
* folio waiters：已经被 wake；
* page-cache 数据：已经可以由 CPU 读取；
* user buffer：仍未执行 ``copy_folio_to_iter()``；
* reader task：runnable 或即将重新运行，但不保证已经获得 CPU；
* file position：仍未提交最终 ``file->f_pos``；
* ``read()``：尚未返回用户态。

下一入口回到发起 read 的 task，继续 ``filemap_get_pages()`` 与 ``filemap_read()``，把 page-cache folio 复制到用户 buffer。

资料
----

* `Linux 7.2-rc1 drivers/scsi/scsi_lib.c：scsi_complete、scsi_end_request 与 scsi_io_completion <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/scsi_lib.c>`_
* `Linux 7.2-rc1 drivers/scsi/scsi.c：scsi_finish_command <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/scsi/scsi.c>`_
* `Linux 7.2-rc1 block/blk-mq.c：blk_update_request 与 request completion <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-mq.c>`_
* `Linux 7.2-rc1 block/bio.c：bio_endio <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/bio.c>`_
* `Linux 7.2-rc1 fs/ext4/readpage.c：mpage_end_io 与 __read_end_io <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/readpage.c>`_
* `Linux 7.2-rc1 mm/filemap.c：folio_end_read、folio unlock 与 waiter wakeup <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_