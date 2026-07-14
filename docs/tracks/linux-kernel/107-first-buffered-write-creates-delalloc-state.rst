第一百零七章：首次 buffered write 怎样只预留空间而不分配物理块？
================================================================================

上一场景结束时，parent持有fd 6：

.. code-block:: text

   path       = /work/demo.txt
   f_pos      = 0
   i_size     = 0
   i_disksize = 0
   data blocks= 0

本章固定用户态调用：

.. code-block:: c

   write(6, buf, 4096);

固定条件：

* ext4 block size与page size均为4 KiB；
* mount options包含 ``data=ordered,delalloc,dioread_nolock,barrier``；
* filesystem没有bigalloc或inline-data feature；
* journal fast commit关闭；
* page-cache index 0尚不存在；
* user buffer已resident且可读；
* cluster ratio为1，quota关闭；
* 本次write返回前没有background writeback；
* 不发生signal、ENOSPC、allocation、copy或I/O错误。

系统调用怎样找到fd 6
--------------------

native x86-64 ``write`` 经过：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_write
   → ksys_write
   → fdget_pos(6)
   → vfs_write
   → new_sync_write
   → call_write_iter
   → ext4_file_write_iter

``fdget_pos()`` 取得fd 6对应的 ``struct file``，并为共享file position取得必要序列化。当前：

.. code-block:: text

   kiocb.ki_pos = file->f_pos = 0
   iov_iter length = 4096

fd 6没有 ``O_DIRECT``、``O_SYNC`` 或 ``O_DSYNC``，所以 ``ext4_file_write_iter()`` 进入：

.. code-block:: c

   ext4_buffered_write_iter(iocb, from);

``ext4_buffered_write_iter`` 先保护什么
--------------------------------------

函数取得inode ``i_rwsem`` write lock，然后执行：

.. code-block:: text

   ext4_write_checks
   → generic_write_checks
   → file_modified

固定write从offset 0扩展size-zero regular file，长度与filesystem限制合法。``file_modified()`` 更新时间与可能的security状态；当前文件没有setuid/setgid位需要清除。

随后进入：

.. code-block:: c

   generic_perform_write(iocb, from);

新folio在哪里分配
-----------------

``generic_perform_write()`` 调用address-space callback：

.. code-block:: c

   mapping->a_ops->write_begin(...);

当前delalloc ext4 inode使用 ``ext4_da_write_begin()``。它确认没有低空间fallback后调用：

.. code-block:: text

   write_begin_get_folio
   → filemap_alloc_folio
   → filemap_add_folio(mapping, index=0)
   → lock folio

由此建立page-cache folio：

.. code-block:: text

   mapping = demo.txt address_space
   index   = 0
   offset  = 0..4095
   locked  = true

分配RAM folio不等于分配ext4 physical block。folio当前只是文件内容的内存容器。

``ext4_da_map_blocks`` 怎样识别hole
-----------------------------------

``ext4_da_write_begin()`` 调用：

.. code-block:: text

   ext4_block_write_begin
   → ext4_da_get_block_prep(inode, logical block 0)
   → ext4_da_map_blocks

lookup顺序是：

.. code-block:: text

   extent-status tree
   → on-disk extent tree
   → 再次在i_data_sem write lock下确认

新文件logical block 0没有written、unwritten或delayed mapping，因此仍是hole。

为什么此时只预留一个cluster
---------------------------

``ext4_da_map_blocks()`` 调用：

.. code-block:: text

   ext4_insert_delayed_blocks(inode, lblk=0, len=1)
   → ext4_da_reserve_space(inode, nr_resv=1)

cluster ratio固定为1，所以reservation是一个4-KiB cluster。它执行：

.. code-block:: text

   reserve quota/accounting capacity
   → ext4_claim_free_clusters(1)
   → i_reserved_data_blocks += 1
   → s_dirtyclusters_counter += 1
   → extent-status tree插入delayed extent [0,1)

reservation只承诺未来writeback应能取得空间。它没有选择physical block number，也没有修改block bitmap。

buffer head怎样表示delalloc
---------------------------

``ext4_da_get_block_prep()`` 把folio中的4-KiB buffer标记为：

.. code-block:: text

   BH_Mapped = 1
   BH_New    = 1
   BH_Delay  = 1
   b_blocknr = invalid sentinel

这里的 ``BH_Mapped`` 表示buffer已经由filesystem callback处理，不表示它拥有有效physical mapping。真正physical block仍未知，决定性标志是 ``BH_Delay``。

用户数据怎样进入folio
---------------------

``generic_perform_write()`` 在folio仍locked时执行：

.. code-block:: text

   copy_folio_from_iter_atomic
   → 把user buf的4096 bytes复制到folio offset 0
   → ext4_da_write_end
   → ext4_da_do_write_end
   → block_write_end

完整4-KiB copy使buffer与folio成为uptodate并dirty。``block_write_end()`` 设置page-dirty状态，使后续writeback能够发现它。

``i_size`` 与 ``i_disksize`` 为什么不同
---------------------------------------

``ext4_da_do_write_end()`` 在folio lock仍持有时更新：

.. code-block:: text

   i_size = 4096

但 ``ext4_da_should_update_i_disksize()`` 看到目标buffer仍带 ``BH_Delay``，返回false。因此：

.. code-block:: text

   i_size     = 4096
   i_disksize = 0

``i_size`` 是当前运行系统对文件长度的可见值。``i_disksize`` 表示ext4已经有安全on-disk mapping可支撑的长度；delalloc数据还不能把它推进到4096。

write为什么可以先返回
---------------------

``ext4_da_write_end()`` 解锁并put folio。``generic_perform_write()`` 更新：

.. code-block:: text

   iocb->ki_pos = 4096
   written       = 4096

``ext4_buffered_write_iter()`` 释放inode ``i_rwsem``，随后调用 ``generic_write_sync()``。fd 6没有sync flags，因此该函数不执行writeback或fsync。

系统调用退出时：

.. code-block:: text

   file->f_pos = 4096
   RAX         = 4096

当前精确状态
------------

* current task：parent；
* CPU mode：x86-64 CPL 3；
* ``write`` result：4096；
* fd 6 ``f_pos``：4096；
* inode ``i_size``：4096；
* ext4 ``i_disksize``：0；
* page-cache folio index 0：uptodate、dirty、unlocked、not under writeback；
* folio data：等于user buffer 4096 bytes；
* extent-status tree：logical ``[0,1)`` 为delayed；
* ``i_reserved_data_blocks``：1；
* physical data block：尚未选择；
* on-disk extent：尚不存在；
* data bio：尚不存在；
* writeback：尚未开始；
* durability：data与新size均未由本次write保证；
* 下一用户动作：固定为 ``fsync(6)``。

关键边界
--------

#. page-cache folio allocation与filesystem block allocation是两件事。
#. delalloc reservation改变空间accounting，不写block bitmap。
#. ``BH_Delay`` 表示尚无physical block，即使 ``BH_Mapped`` 已设置。
#. ``i_size`` 可以领先于 ``i_disksize``。
#. 普通buffered write成功只说明数据进入kernel cache，不说明设备已收到数据。
#. fd没有sync flags时，``generic_write_sync()`` 不强制I/O。

资料
----

* `Linux 7.2-rc1 fs/ext4/file.c：ext4_buffered_write_iter <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/file.c>`_
* `Linux 7.2-rc1 mm/filemap.c：generic_perform_write <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/filemap.c>`_
* `Linux 7.2-rc1 fs/ext4/inode.c：ext4_da_write_begin、ext4_da_map_blocks与ext4_da_write_end <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/ext4/inode.c>`_
