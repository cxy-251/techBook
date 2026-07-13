第七十六章：page cache miss 怎样让 ext4 构造并提交 READ bio？
=============================================================

第七十五章停在：

.. code-block:: text

   ext4_file_read_iter()
   → generic_file_read_iter(iocb, iter)

此时 ``kiocb`` 已保存 ext4 ``struct file`` 与当前 file position，``iov_iter`` 指向 4096 字节用户 buffer。尚未查 page cache，也没有向 block layer 提交请求。

为得到一条确定的 cold-read 路径，本章追加固定条件：

* ``kiocb.ki_pos = 0``，文件长度至少 4096 字节；
* ext4 block size 为 4096 字节；
* 文件使用普通 extent mapping，logical block 0 已映射到一个 physical block；
* inode 没有 inline data、fscrypt、fs-verity、DAX；
* page cache 中没有 index 0 的 folio；
* file readahead window 非零，同步 readahead 覆盖目标 folio；
* 用户 buffer 对应页可以在复制阶段正常写入。

本章追踪到 ``blk_crypto_submit_bio(bio)``。bio 进入 block layer 后的 request、scheduler、AHCI 与 completion interrupt 留给下一批。

``generic_file_read_iter()`` 为什么直接进入 page cache
----------------------------------------------------

该函数先取得请求长度：

.. code-block:: c

   count = iov_iter_count(iter);

当前为 4096。``IOCB_DIRECT`` 未设置，因此跳过 direct-I/O 分支，直接调用：

.. code-block:: c

   filemap_read(iocb, iter, 0);

第三个参数 ``already_read = 0``，表示当前没有 direct-I/O 前半段已经完成的数据。

``filemap_read()`` 操作的核心对象不是 inode block
-----------------------------------------------

``filemap_read()`` 取得：

.. code-block:: text

   filp    = iocb->ki_filp
   mapping = filp->f_mapping
   inode   = mapping->host
   ra      = filp->f_ra

其中 ``address_space mapping`` 是文件 page cache 的中心对象：

* ``mapping->i_pages`` 保存以 file page index 为 key 的 folio；
* ``mapping->host`` 指回 ext4 inode；
* ``mapping->a_ops`` 提供 ``readahead``、``read_folio`` 等 filesystem 回调；
* ``file->f_ra`` 保存这个 open file description 的顺序读取状态。

因此 buffered read 的第一目标是“获得包含文件 offset 0 的 uptodate folio”，不是立即生成磁盘 sector request。

进入循环前，``filemap_read()`` 检查：

.. code-block:: text

   ki_pos >= 0
   ki_pos < superblock s_maxbytes
   iterator count > 0
   ki_pos < inode i_size

固定文件至少 4096 字节，所有检查通过。

第一次 ``filemap_get_read_batch()`` 为什么得到空结果
---------------------------------------------------

``filemap_get_pages()`` 根据 offset 计算：

.. code-block:: text

   index      = ki_pos >> PAGE_SHIFT = 0
   last_index = first folio index beyond requested range

随后调用：

.. code-block:: c

   filemap_get_read_batch(mapping, index, last_index - 1, fbatch);

该函数在 ``mapping->i_pages`` 的 XArray 中查找已有 folio。固定条件声明 index 0 cold miss，因此 ``fbatch`` 为空。

这里的“page cache miss”只说明文件数据不在 RAM 中的 file cache。它不说明进程 user buffer 缺页，也不说明 ext4 metadata 一定不在缓存中；这三类缓存状态必须分开。

同步 readahead 怎样接管 cold miss
--------------------------------

空 batch 触发：

.. code-block:: c

   DEFINE_READAHEAD(ractl, filp, &filp->f_ra, mapping, index);
   page_cache_sync_ra(&ractl, last_index - index);

readahead 层根据 ``file->f_ra``、backing-device readahead limits 和当前访问模式决定实际窗口。固定场景只保证窗口非零并覆盖 index 0，不固定它究竟创建一个还是多个 folio。

readahead 会先把新 folio 插入 ``mapping->i_pages``，再调用 filesystem 的 ``mapping->a_ops->readahead``。对当前 ext4 regular inode，该回调是：

.. code-block:: c

   ext4_readahead(rac);

这意味着 page cache 负责“需要哪些 file offsets”，ext4 负责“这些 offsets 对应哪些磁盘 blocks，以及怎样组装 bio”。

为什么还保留 ``read_folio`` 备用路径
----------------------------------

``filemap_get_pages()`` 在同步 readahead 后会再次 lookup。如果 readahead 没有留下目标 folio，它还能调用 ``filemap_create_folio()``：

.. code-block:: text

   allocate folio
   → insert into mapping->i_pages
   → mapping->a_ops->read_folio
   → ext4_read_folio

``ext4_read_folio()`` 与 ``ext4_readahead()`` 最终都进入 ``ext4_mpage_readpages()``。本章固定同步 readahead 已覆盖目标，所以主线使用 ``ext4_readahead()``；备用路径说明 cold miss 不依赖 readahead 必须成功才能读取。

``ext4_readahead()`` 先排除 inline data 与 verity 特例
--------------------------------------------------

ext4 回调取得 ``rac->mapping->host`` 对应 inode，然后检查：

* inline data：数据直接保存在 inode body，当前固定为 false；
* fs-verity：需要额外 metadata readahead 与校验，当前固定为 false。

因此直接调用：

.. code-block:: c

   ext4_mpage_readpages(inode, NULL, rac, NULL);

``rac`` 提供 page-cache 层已经准备好的 folio 序列。ext4 逐个取出 locked folio，并准备 logical-to-physical mapping。

4 KiB folio 怎样变成 ext4 logical block 0
----------------------------------------

固定 x86-64 page size 与 ext4 block size 都是 4096 字节，因此：

.. code-block:: text

   folio index       = 0
   folio position    = 0
   inode i_blkbits   = 12
   blocks per folio  = 1
   block_in_file     = 0

``ext4_mpage_readpages()`` 构造 ``struct ext4_map_blocks``，并调用：

.. code-block:: c

   ext4_map_blocks(NULL, inode, &map, 0);

flags 为 0 表示查询已有 mapping，不为 read 分配新 data block。extent tree 将 logical block 0 映射为 ``map.m_pblk``，并设置 ``EXT4_MAP_MAPPED``。

若这里得到 hole，ext4 会把对应 folio 范围清零并直接完成读取，不需要磁盘 I/O。当前场景固定为已有 mapped block，所以继续构造 bio。

为什么 ext4 要检查物理 block 是否连续
-------------------------------------

一个 readahead window 可能包含多个 folio。ext4 尝试把连续 logical blocks 映射出的连续 physical blocks 合并到一个 bio，以减少 block-layer request 数量。

它会在以下情况结束当前 bio 并重新分配：

* 新 physical block 不紧邻前一个 block；
* fscrypt context 不可合并；
* extent boundary 要求提交；
* folio 中出现 hole 或复杂 buffer-head layout。

固定第一个 4 KiB folio只有一个 mapped block，不存在 hole、加密或不连续问题。

``bio_alloc()`` 建立了什么
-------------------------

ext4 为 block device 分配：

.. code-block:: c

   bio_alloc(bdev, bio_max_segs(nr_pages),
             REQ_OP_READ, GFP_KERNEL);

此时 bio 的关键字段是：

.. code-block:: text

   target device = inode->i_sb->s_bdev
   operation     = REQ_OP_READ
   end_io        = mpage_end_io
   private       = optional post-read context

当前文件不使用 fscrypt/fs-verity，所以不需要 decrypt/verity post-processing context。``mpage_end_io`` 仍是统一 completion callback；I/O 成功后它最终调用 ``folio_end_read(folio, true)``，设置 uptodate 并唤醒等待者。

physical block 怎样换成 sector
-----------------------------

bio 使用 512-byte sector 编号，而 ext4 mapping 返回 filesystem block。源码写入：

.. code-block:: c

   bio->bi_iter.bi_sector = first_block << (blkbits - 9);

当前 ``blkbits = 12``，因此：

.. code-block:: text

   starting sector = physical ext4 block << 3

一个 4096-byte filesystem block 对应 8 个 512-byte sectors。这里只完成地址单位转换，还没有决定 AHCI command slot 或 SATA LBA command。

``bio_add_folio()`` 为什么不复制文件数据
--------------------------------------

调用：

.. code-block:: c

   bio_add_folio(bio, folio, 4096, 0);

只是把目标 folio 的 memory pages 描述为 bio vector：磁盘读取完成后，block device DMA/driver 路径会把数据放入这些 pages。

它没有把数据复制到用户 ``buf``。真正的 user copy 要等 folio uptodate 后，由 ``filemap_read()`` 调用 ``copy_folio_to_iter()`` 完成。

因此存在两次不同的数据移动概念：

.. code-block:: text

   storage → page-cache folio
   page-cache folio → user buffer

第一段由 block I/O 与设备完成，第二段由 filemap/uaccess 完成。

``blk_crypto_submit_bio()`` 是本章的交接点
----------------------------------------

folio 加入 bio 后，ext4 在窗口结束或 boundary 条件满足时调用：

.. code-block:: c

   blk_crypto_submit_bio(bio);

即使文件未加密，ext4 仍通过该统一入口。inline-encryption 层检查 bio crypt context；没有加密要求时继续把 bio 交给普通 block submission path。

从这一刻开始，文件系统已经完成：

.. code-block:: text

   file offset
   → page-cache folio
   → ext4 logical block
   → physical block
   → block-device sector
   → READ bio

后续职责属于 block layer：bio 合并/拆分、request queue、I/O scheduler、blk-mq hardware queue、SCSI/AHCI driver 与 completion interrupt。

当前 task 为什么还没有得到数据
-----------------------------

bio submission 通常是异步的。``ext4_readahead()`` 可以在设备完成前返回到 ``filemap_get_pages()``。目标 folio 已存在，但可能仍 locked 且未 uptodate。

随后 filemap 会：

.. code-block:: text

   find target folio
   → detect not uptodate / locked
   → wait for read completion when required
   → verify folio uptodate
   → copy_folio_to_iter(user buffer)

当前章节停在首次 READ bio 提交，因此还不能声称 ``read()`` 已返回 4096，也不能声称用户 buffer 已包含文件数据。

本章结束时的状态
----------------

本章结束时：

* 当前执行者：发起 read 的 task，在 ext4 readahead/read context 中；
* CPU mode：CPL 0，process context；
* page cache：目标 folio 已分配并插入 ``mapping->i_pages``；
* folio：参与 READ bio，尚不能假设 uptodate；
* ext4 mapping：logical block 0 已解析为 physical block；
* bio：``REQ_OP_READ``，sector 与 folio vector 已填写；
* completion：``mpage_end_io`` 已登记；
* block layer：即将接管 ``blk_crypto_submit_bio(bio)``；
* AHCI request：尚未创建；
* disk command：尚未发出；
* user buffer：尚未由 ``copy_folio_to_iter()`` 填充；
* syscall return value：尚未确定。

下一入口从 ``blk_crypto_submit_bio()`` 继续，追踪 bio 怎样进入 ``submit_bio_noacct()``、blk-mq request queue，并最终到达 q35 ICH9 AHCI driver。

资料
----

* `Linux 7.2-rc1 mm/filemap.c：generic_file_read_iter、filemap_read 与 filemap_get_pages <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
* `Linux 7.2-rc1 mm/readahead.c：page_cache_sync_ra 与 ondemand readahead <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/readahead.c>`_
* `Linux 7.2-rc1 fs/ext4/readpage.c：ext4_readahead、ext4_read_folio、block mapping 与 bio construction <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/readpage.c>`_
* `Linux 7.2-rc1 fs/ext4/inode.c：ext4 address_space operations 与 ext4_map_blocks <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/inode.c>`_
* `Linux 7.2-rc1 block/blk-crypto.c：blk_crypto_submit_bio <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/block/blk-crypto.c>`_
* `Linux 7.2-rc1 include/linux/bio.h：struct bio 与 bio_add_folio <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/bio.h>`_