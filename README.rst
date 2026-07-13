techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第八十三章：x86-64 的 write() 怎样进入 ext4 buffered write？ <docs/tracks/linux-kernel/83-x86-write-enters-ext4-buffered-path.rst>`_
* `第八十四章：ext4 怎样把用户数据复制进 page-cache folio 并标脏？ <docs/tracks/linux-kernel/84-ext4-copies-user-data-into-dirty-folio.rst>`_
* `第八十五章：O_SYNC write 怎样进入 ext4 writeback？ <docs/tracks/linux-kernel/85-osync-write-enters-ext4-writeback.rst>`_

固定来源
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

固定 commit 的真实版本是 Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 属于历史显示标签错误；源码事实以固定 commit 为准。

已经完成
--------

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-085

``read()`` cold-miss 运行期主线已经完整闭环。当前是独立的 ext4 synchronous buffered write 场景：

::

   write(fd, buf, 4096)
   → native x86-64 syscall entry
   → ksys_write / vfs_write
   → ext4_file_write_iter
   → ext4_buffered_write_iter
   → generic_perform_write
   → ext4_da_write_begin
   → copy_folio_from_iter_atomic
   → ext4_da_write_end
   → dirty page-cache folio
   → generic_write_sync
   → vfs_fsync_range
   → ext4_sync_file
   → file_write_and_wait_range
   → WB_SYNC_ALL
   → do_writepages
   → ext4_writepages

固定 write 条件：文件以 ``O_SYNC`` 打开，普通 ext4 ``data=ordered``、journal enabled、delalloc enabled，offset 0，完整覆盖已有 4 KiB initialized block，目标 folio 初始不在 page cache，用户 buffer mapped and readable。

当前状态
--------

用户数据已经复制到 dirty、uptodate、unlocked 的 page-cache folio。``kiocb->ki_pos`` 已是 4096，local ``pos`` 和共享 ``file->f_pos`` 尚未提交。O_SYNC task 已进入 ``ext4_writepages()``，WRITE bio、blk-mq request、SCSI/ATA/AHCI command 尚未建立。

下一步从 ``ext4_writepages()`` 开始，追踪 dirty folio、writeback extent、ordered-data journal、WRITE bio、block/SCSI/libata/AHCI submission 与完成，再返回 journal commit 和同步 write syscall。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节；
#. ``manifests/tracks/linux-kernel.toml``。
