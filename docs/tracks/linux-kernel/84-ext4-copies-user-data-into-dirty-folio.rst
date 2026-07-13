第八十四章：ext4 怎样把用户数据复制进 page-cache folio 并标脏？
====================================================================

第八十三章结束时，``ext4_buffered_write_iter()`` 已完成写检查并持有 inode ``i_rwsem``，即将进入：

.. code-block:: c

   generic_perform_write(&kiocb, &iter);

当前 iterator 是 ``ITER_SOURCE``，包含用户 buffer 中的 4096 bytes；目标 page-cache index 0 尚不存在。本章追踪 ext4 怎样取得并准备 folio、完成 user-to-kernel copy、标记 dirty，并把 ``kiocb->ki_pos`` 推进到 4096。

本章仍不进入磁盘 I/O。``O_SYNC`` 只保证函数稍后必须执行同步阶段，不会让这一段跳过 page cache。

``generic_perform_write`` 怎样切分本次写入
-----------------------------------------

函数首先取得：

.. code-block:: c

   file    = iocb->ki_filp;
   mapping = file->f_mapping;
   a_ops   = mapping->a_ops;
   pos     = iocb->ki_pos;

固定场景中：

.. code-block:: text

   pos                    = 0
   iov_iter_count(iter)   = 4096
   mapping folio size     = 4096
   offset in folio        = 0
   bytes in this iteration= 4096

因此整个 write 只需要一次 folio iteration。

函数在调用 filesystem ``write_begin`` 前执行 ``balance_dirty_pages_ratelimited(mapping)``。它根据当前 task 与 backing device 的 dirty pressure 决定是否需要节流。本场景没有设置高 dirty pressure，因此不会在此处长时间阻塞。

为什么进入 ``ext4_da_write_begin``
---------------------------------

固定 ext4 使用 journal、``data=ordered`` 和 delayed allocation。普通非 DAX inode 的 address-space operations 选择 delayed-allocation aops：

.. code-block:: text

   mapping->a_ops->write_begin = ext4_da_write_begin
   mapping->a_ops->write_end   = ext4_da_write_end
   mapping->a_ops->writepages  = ext4_writepages

``generic_perform_write()`` 因而调用：

.. code-block:: c

   a_ops->write_begin(iocb, mapping, pos, bytes,
                      &folio, &fsdata);

``ext4_da_write_begin()`` 先检查 filesystem emergency state、inline-data state 和 free-space pressure。固定条件排除 inline data、ENOSPC 与 non-delalloc fallback，所以继续使用 delayed-allocation write-begin 路径。

``write_begin_get_folio`` 怎样创建目标 folio
-------------------------------------------

index 0 不在 ``mapping->i_pages`` 中。``write_begin_get_folio()`` 分配一个 folio，将其插入 address-space XArray，并以 locked 状态返回：

.. code-block:: text

   folio->mapping = file->f_mapping
   folio->index   = 0
   PG_locked      = 1

插入 page cache 与复制用户数据是两个不同动作。folio 此时只是一个受锁保护的内核缓存对象，内容尚不能代表新的文件数据。

完整覆盖为什么不需要先读旧磁盘数据
----------------------------------

``ext4_da_write_begin()`` 调用：

.. code-block:: c

   ext4_block_write_begin(NULL, folio, pos, len,
                          ext4_da_get_block_prep);

该函数为 folio 建立或检查 buffer-head/block 状态。固定写入满足：

.. code-block:: text

   offset = 0
   length = PAGE_SIZE = filesystem block size

整个 4 KiB filesystem block 都会被用户数据覆盖，因此无需为了保留未覆盖字节而先读取旧 block 内容。

逻辑块 0 已经是 initialized mapped extent。delalloc aops 仍负责该 buffered write，但这次 overwrite 不需要创建新的 extent，也不应被描述成“此刻已经重新分配磁盘块”。write-begin 的主要结果是：

* folio 保持 locked；
* buffer state 与现有 logical-to-physical mapping 对应；
* write-end 可以安全发布完整覆盖后的数据状态。

用户数据在哪里真正被读取
------------------------

``generic_perform_write()`` 在 folio 准备完成后执行：

.. code-block:: c

   copied = copy_folio_from_iter_atomic(folio, offset, bytes, iter);

这是真正的数据移动：

.. code-block:: text

   userspace buf
   → x86 uaccess/copy implementation
   → page-cache folio memory

函数使用 atomic copy，是因为此时 filesystem 与 folio locks 已持有；若在普通 user fault path 中递归进入任意 filesystem code，可能造成锁反转或死锁。

固定用户 buffer 在复制期间保持 mapped、readable，并且相关 user pages 可正常访问，因此：

.. code-block:: text

   copied = 4096
   iterator remaining = 0

若 copy 只完成部分数据，write-end 可以接受 partial copy，或者函数回退后 fault-in user pages 并重试。固定主线不走该分支。

``ext4_da_write_end`` 怎样发布新数据
-----------------------------------

copy 完成后，通用层调用：

.. code-block:: c

   a_ops->write_end(iocb, mapping, pos, bytes,
                    copied, folio, fsdata);

固定路径进入 ``ext4_da_write_end()``，再调用 ``ext4_da_do_write_end()``。核心动作由 ``block_write_end()`` 完成：

* 将成功覆盖的 buffer 范围标记 uptodate；
* 把 folio 标记为 dirty；
* 把 inode 放入带 ``I_DIRTY_PAGES`` 语义的 dirty tracking；
* 保留后续 writeback 所需的 buffer/mapping 状态。

这里的 ``uptodate`` 与 read completion 中的语义不同：它表示 page cache 已包含当前文件数据，不表示数据已经写入 stable storage。

固定写没有扩展文件：

.. code-block:: text

   old i_size = at least 4096
   write end  = 4096

所以 ``ext4_da_do_write_end()`` 不需要提高 ``i_size``，也不需要为 size extension 更新 ``i_disksize`` 或 orphan list。

folio 为什么在 write-end 结束时解锁
----------------------------------

数据与 dirty state 发布后，ext4 执行：

.. code-block:: c

   folio_unlock(folio);
   folio_put(folio);

此刻其他 reader 或 writeback worker 可以取得该 folio。解锁不表示 writeback 已经启动；它只结束当前 buffered-write 对 folio 内容的独占修改阶段。

``generic_perform_write`` 怎样推进 ``ki_pos``
--------------------------------------------

write-end 返回 4096 后，通用层更新 local state：

.. code-block:: c

   pos     += status;
   written += status;

iterator 已无剩余数据，循环结束。函数最终执行：

.. code-block:: c

   iocb->ki_pos += written;
   return written;

当前：

.. code-block:: text

   written       = 4096
   iocb->ki_pos  = 4096
   iterator bytes= 0

注意此时只是 ``kiocb`` 的位置已推进。``new_sync_write()`` 尚未把它复制回 local ``pos``，``ksys_write()`` 也尚未提交共享 ``file->f_pos``。

为什么 write 还不能返回用户态
-----------------------------

``ext4_buffered_write_iter()`` 在 ``generic_perform_write()`` 返回后释放 inode lock：

.. code-block:: c

   inode_unlock(inode);

然后执行：

.. code-block:: c

   return generic_write_sync(iocb, ret);

这一步发生在 inode ``i_rwsem`` 之外，避免同步 writeback、journal commit 与 inode data lock 形成不必要的长临界区。

文件以 ``O_SYNC`` 打开，``iocb_is_dsync(iocb)`` 为真，因此 ``generic_write_sync()`` 不会直接返回 4096。它必须同步本次写入范围。

当前精确边界
------------

CPU 即将进入：

.. code-block:: c

   generic_write_sync(iocb, 4096);

此刻机器状态：

* 当前执行者：调用 ``write()`` 的 task；
* CPU mode：CPL 0，syscall process context；
* target folio：位于 page cache，unlocked；
* folio data：已经是用户 buffer 的 4096 bytes；
* folio state：dirty，当前内容可供 page-cache reader 使用；
* stable storage：尚未更新；
* ext4 block allocation：固定 block 已存在，没有新 extent allocation；
* ``kiocb->ki_pos``：4096；
* local ``pos``：仍未由 ``new_sync_write()`` 更新；
* ``file->f_pos``：仍为 0；
* inode ``i_rwsem``：已释放；
* superblock freeze protection：仍由 ``vfs_write()`` 持有；
* writeback bio/request：尚未建立；
* ``write()``：尚未返回。

关键边界
--------

#. page-cache folio 创建不等于用户数据已经复制。
#. full-folio overwrite 可以避免 read-before-write，但仍需要 write-begin/write-end 协议。
#. dirty folio 表示内存数据比 stable storage 新，不表示磁盘写已经发生。
#. delayed-allocation aops 被选中，不表示每次 overwrite 都会创建 delayed extent。
#. ``folio_unlock()`` 允许其他执行者访问，不启动硬件 I/O。
#. ``kiocb->ki_pos``、local ``pos`` 与 ``file->f_pos`` 仍必须分层描述。
#. ``O_SYNC`` 的同步发生在 inode lock 释放之后。

资料
----

* `Linux 7.2-rc1 mm/filemap.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
* `Linux 7.2-rc1 fs/ext4/inode.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/inode.c>`_
* `Linux 7.2-rc1 fs/ext4/file.c <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/file.c>`_
* `Linux 7.2-rc1 include/linux/fs.h <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/fs.h>`_
