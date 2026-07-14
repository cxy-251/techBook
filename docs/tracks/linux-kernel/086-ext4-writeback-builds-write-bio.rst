第八十六章：ext4 writeback 怎样把 dirty folio 变成 WRITE bio？
===================================================================

第八十五章结束时，O_SYNC writer 已经通过 ``file_write_and_wait_range()`` 建立：

.. code-block:: text

   sync_mode  = WB_SYNC_ALL
   range_start= 0
   range_end  = 4095

``do_writepages()`` 根据 ``mapping->a_ops->writepages`` 把控制权交给：

.. code-block:: c

   ext4_writepages(mapping, wbc);

目标 folio 位于 page cache，状态是 dirty、uptodate、unlocked。用户数据已经完成 CPU copy；本章追踪 ext4 怎样锁定 folio、清除 dirty-for-I/O、设置 ``PG_writeback``、构造 ``REQ_OP_WRITE`` bio，并调用 ``blk_crypto_submit_bio()``。

固定写覆盖的是已经 initialized、已经映射的 logical block 0。这个条件决定本次 writeback 不需要为 delayed extent 分配新磁盘块。

``ext4_writepages`` 怎样进入真实 writeback 循环
---------------------------------------------

``ext4_writepages()`` 建立 ``struct mpage_da_data``，然后调用：

.. code-block:: c

   ext4_do_writepages(&mpd);

函数先确认：

* mapping 中仍有 folio；
* ``PAGECACHE_TAG_DIRTY`` 仍然存在；
* filesystem 没有进入 emergency/forced-shutdown 状态；
* inode 不使用 inline data；
* 当前不是 ``data=journal`` 模式。

固定 filesystem 是 ``data=ordered``，所以：

.. code-block:: text

   mpd->can_map = 1

这表示 writeback 必要时允许映射 delayed/unwritten buffers。它不表示当前 folio一定需要新映射。

范围怎样固定在第一个 folio
--------------------------

当前 ``writeback_control`` 不是 cyclic writeback：

.. code-block:: c

   mpd->start_pos = wbc->range_start;  /* 0 */
   mpd->end_pos   = wbc->range_end;    /* 4095 */

``WB_SYNC_ALL`` 还会调用 ``tag_pages_for_writeback()``，把本轮开始时需要同步的 dirty folio标记到 writeback scan 使用的 ``TOWRITE`` 集合。

这样可以区分：

* 本次 O_SYNC 开始前已经存在的 dirty data；
* scan 期间其他执行者后来再次弄脏的 data。

完整同步不能因为并发 dirtying 而漏掉本轮目标范围。

为什么 ext4 启动 block plug
---------------------------

``ext4_do_writepages()`` 调用：

.. code-block:: c

   blk_start_plug(&plug);

writeback 可能连续产生多个相邻 bio。plug 允许 block layer 暂时收集 request，并在 ``blk_finish_plug()`` 时统一 merge/dispatch。

当前只有一个 4 KiB folio，但代码仍走相同机制。plug 影响 request 何时进入 hardware queue，不改变 bio、request 和 AHCI command 的对象边界。

第一遍为什么设置 ``do_map = 0``
-------------------------------

ext4 首先尝试提交“不需要修改 extent metadata”的 folio：

.. code-block:: c

   mpd->do_map = 0;
   mpage_prepare_extent_to_map(mpd);

这样可以避免在已经映射的数据块上无意义地启动 journal transaction，也避免持有 transaction 时阻塞在底层设备拥塞上。

固定 logical block 0 在 write 之前已经是 initialized mapped extent。第八十四章的 ``ext4_da_get_block_prep()`` 已把对应 buffer head 设置为：

.. code-block:: text

   BH_Mapped    = 1
   BH_Delay     = 0
   BH_Unwritten = 0
   b_blocknr    = existing ext4 physical block

因此当前 folio可以在第一遍直接提交，不进入第二遍 ``mpage_map_and_submit_extent()``，也不进行新的 ext4 block allocation。

``mpage_prepare_extent_to_map`` 怎样取得 folio
---------------------------------------------

函数按 ``TOWRITE`` tag 扫描 ``mapping->i_pages``，找到 index 0 的 folio后执行：

.. code-block:: c

   folio_lock(folio);
   folio_wait_writeback(folio);

固定 folio 当前没有旧 writeback，所以 wait 立即结束。随后再次确认：

* folio仍然 dirty；
* ``folio->mapping`` 仍指向当前 inode mapping；
* folio带有 ext4 buffer heads；
* 没有 truncate/invalidate 把它移走。

这些检查发生在 folio lock 之下，避免对已经被替换或截断的 page-cache 对象提交 I/O。

已有 mapped buffer 为什么可以直接提交
-------------------------------------

``mpage_process_page_bufs()`` 遍历 folio 的 buffer heads。当前唯一 4 KiB buffer：

.. code-block:: text

   dirty = 1
   mapped = 1
   delay = 0
   unwritten = 0

``mpage_add_bh_to_extent()`` 判断该 buffer 不需要 mapping；因为当前没有正在积累的 delayed extent，函数允许直接调用：

.. code-block:: c

   mpage_submit_folio(mpd, folio);

这里没有生成新的 ``ext4_map_blocks`` allocation transaction。``data=ordered`` 的最终顺序将在 O_SYNC 路径中通过“先等待 file data I/O，再提交相关 journal transaction”实现。

``folio_clear_dirty_for_io`` 建立什么状态转换
---------------------------------------------

``mpage_submit_folio()`` 首先执行：

.. code-block:: c

   folio_clear_dirty_for_io(folio);

这个动作不是简单清除一个 flag。它还负责：

* 清除本轮要写出的 dirty state；
* 更新 page-cache dirty tags/accounting；
* 对可写 mmap 映射执行必要的 write-protect 协议；
* 建立 writeback 可以安全采样 ``i_size`` 的顺序保证。

如果另一个 CPU 在稍后再次修改 folio，它会重新设置 dirty；``PG_writeback`` 与新的 dirty state可以同时存在，表示“旧版本正在写出，内存中又出现了更新版本”。

``ext4_bio_write_folio`` 怎样准备 buffer I/O
-------------------------------------------

固定文件大小至少 4096 bytes，所以本次 ``len`` 是完整 folio size，不需要 zero beyond EOF。

``ext4_bio_write_folio()`` 检查每个 buffer，当前 buffer满足：

.. code-block:: text

   buffer_dirty       = 1
   buffer_mapped      = 1
   buffer_delay       = 0
   buffer_unwritten   = 0

函数随后：

.. code-block:: c

   set_buffer_async_write(bh);
   clear_buffer_dirty(bh);

``BH_Async_Write`` 让 completion path 知道哪些 buffers 属于当前 bio。只有所有相关 async-write buffers 都完成后，folio 才能执行 ``folio_end_writeback()``。

``PG_writeback`` 在哪里设置
--------------------------

在任何 buffer 真正加入 bio 前，ext4执行：

.. code-block:: c

   __folio_start_writeback(folio, keep_towrite);

当前 ``keep_towrite`` 为 false，所以状态变为：

.. code-block:: text

   PG_dirty     = 0   /* 本轮版本已经交给 I/O */
   PG_writeback = 1

设置 ``PG_writeback`` 必须早于提交第一个 buffer。否则极快的 completion 可能在 ext4仍在组装同一 folio 的其他 buffer 时提前调用 ``folio_end_writeback()``。

WRITE bio 怎样建立
------------------

``io_submit_add_bh()`` 发现当前尚无 bio，于是调用 ``io_submit_init_bio()``：

.. code-block:: c

   bio_alloc(bh->b_bdev, BIO_MAX_VECS,
             REQ_OP_WRITE, GFP_NOIO);

随后填写：

.. code-block:: text

   bio operation       = REQ_OP_WRITE
   bi_bdev             = ext4 所在的 /dev/sda1
   bi_sector           = b_blocknr 转换出的分区内 sector
   bi_end_io           = ext4_end_bio
   bi_private          = ext4_io_end
   bi_write_hint       = inode write hint

固定文件没有 fscrypt，因此 ``fscrypt_set_bio_crypt_ctx()`` 不会建立实际 crypt context。

``bio_add_folio()`` 把 folio 的 4096-byte range 加入 bio vector。对 WRITE，vector 表示：

.. code-block:: text

   page-cache folio memory
   → 作为设备 DMA 的数据源
   → 写入 bio 指定的 disk sectors

用户 buffer 已经退出数据路径。AHCI 后续不会直接读取 userspace ``buf``；它读取的是 page-cache folio 对应的 DMA addresses。

folio 为什么在 bio completion 前就解锁
-------------------------------------

``mpage_submit_folio()`` 返回后，``mpage_folio_done()``：

.. code-block:: c

   wbc->nr_to_write -= folio_nr_pages(folio);
   folio_unlock(folio);

此时：

.. code-block:: text

   PG_locked    = 0
   PG_writeback = 1

folio lock保护内容准备阶段；writeback flag保护异步设备 I/O 生命周期。二者不能混为同一个状态。

``ext4_io_submit`` 怎样真正交给 block layer
------------------------------------------

scan 返回后，``ext4_do_writepages()`` 调用：

.. code-block:: c

   ext4_io_submit(&mpd->io_submit);

因为当前是 ``WB_SYNC_ALL``，ext4给 bio增加：

.. code-block:: c

   bio->bi_opf |= REQ_SYNC;

``REQ_SYNC`` 表示同步/高优先级语义提示，不等于 ``REQ_FUA``。当前 bio没有设置 FUA；stable-storage 保证还需要后续 data completion、journal commit 和必要的 cache flush。

最后调用：

.. code-block:: c

   blk_crypto_submit_bio(bio);

固定 bio没有 crypt context，因此下一步会进入普通 ``submit_bio()`` 和通用 block submission。

当前精确边界
------------

CPU 已调用：

.. code-block:: c

   blk_crypto_submit_bio(write_bio);

当前状态：

* 当前执行者：发起 O_SYNC ``write()`` 的 task；
* CPU mode：CPL 0，process context；
* bio operation：``REQ_OP_WRITE | REQ_SYNC``；
* bio data source：page-cache folio；
* bio block address：仍是 ``/dev/sda1`` 分区内 sector；
* bio completion：``ext4_end_bio``；
* folio：uptodate、unlocked、``PG_writeback=1``；
* 本轮 dirty state：已清除；
* 新 block allocation：没有发生；
* blk plug：active，稍后由 ``blk_finish_plug()`` flush；
* blk-mq request：尚未建立；
* SCSI/ATA/AHCI command：尚未建立；
* data I/O：尚未完成；
* journal commit：尚未开始等待；
* ``file->f_pos``：仍为 0；
* ``write()``：尚未返回。

关键边界
--------

#. 已有 initialized extent 的覆盖写可以在 ``do_map=0`` 第一遍直接提交。
#. delayed-allocation aops 不代表本次一定分配 delayed blocks。
#. ``folio_clear_dirty_for_io()`` 与 ``__folio_start_writeback()`` 是两个状态转换。
#. folio unlock 不表示 writeback 已完成；``PG_writeback`` 仍保持为 1。
#. WRITE DMA 的源是 page-cache folio，不是用户 buffer。
#. ``REQ_SYNC`` 不等于 ``REQ_FUA``，也不等于 stable storage 已更新。
#. data writeback 与后续 JBD2 transaction commit 是两个独立阶段。

资料
----

* `Linux 7.2-rc1 fs/ext4/inode.c：ext4_writepages、mpage_prepare_extent_to_map 与 mpage_submit_folio <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/inode.c>`_
* `Linux 7.2-rc1 fs/ext4/page-io.c：ext4_bio_write_folio、ext4_io_submit 与 ext4_end_bio <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/page-io.c>`_
* `Linux 7.2-rc1 mm/page-writeback.c：dirty/writeback accounting <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/page-writeback.c>`_
* `Linux 7.2-rc1 include/linux/writeback.h：writeback_control 与 WB_SYNC_ALL <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/writeback.h>`_
