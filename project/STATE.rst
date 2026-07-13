项目状态
========

最后更新
--------

2026-07-14

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-085

最新三章：

#. ``LK-WRITE-083``：x86-64 的 write() 怎样进入 ext4 buffered write？
#. ``LK-WRITE-084``：ext4 怎样把用户数据复制进 page-cache folio 并标脏？
#. ``LK-WRITE-085``：O_SYNC write 怎样进入 ext4 writeback？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

旧章节中的 ``Linux 6.12.95`` 是历史显示标签错误，技术事实继续以固定 Linux commit 为准。

已完成的 read 场景
------------------

``read(fd, buf, 4096)`` cold page-cache miss 已完整闭环：VFS、ext4、page cache、block、SCSI、libata、AHCI、DMA completion、folio unlock、user copy 和 syscall return 均已写完。

当前 write 固定场景
-------------------

::

   userspace call       = write(fd, buf, 4096)
   ABI                  = native x86-64 SYSCALL
   open flags           = O_WRONLY | O_SYNC
   file                 = independent already-open regular ext4 file
   filesystem           = /dev/sda1, journal enabled, data=ordered, delalloc enabled
   initial f_pos        = 0
   file size            = at least 4096 bytes
   filesystem block     = 4096 bytes
   write type           = full-block overwrite, not extending
   extent               = logical block 0 already initialized and mapped
   initial page cache   = index 0 absent
   user buffer          = mapped, readable, stable
   excluded             = O_DIRECT, DAX, inline data, fscrypt, fs-verity, atomic write
   failure policy       = no ENOSPC, copy fault, forced shutdown or injected I/O error

当前控制流
----------

::

   userspace write(fd, buf, 4096)
   → entry_SYSCALL_64
   → do_syscall_64 / __x64_sys_write
   → ksys_write / fd position guard
   → vfs_write / new_sync_write
   → IOCB_SYNC + IOCB_DSYNC
   → ext4_file_write_iter
   → ext4_buffered_write_iter
   → inode_lock
   → ext4_write_checks
   → generic_perform_write
   → ext4_da_write_begin
   → allocate and lock page-cache folio
   → prepare existing block mapping
   → copy_folio_from_iter_atomic
   → ext4_da_write_end / block_write_end
   → folio dirty, uptodate, unlocked
   → iocb->ki_pos = 4096
   → inode_unlock
   → generic_write_sync
   → vfs_fsync_range(file, 0, 4095, datasync=0)
   → ext4_sync_file
   → file_write_and_wait_range
   → filemap_fdatawrite_range
   → writeback_control: WB_SYNC_ALL, range 0..4095
   → do_writepages
   → ext4_writepages

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* 当前执行者：发起 O_SYNC ``write()`` 的 task；
* CPU mode：x86-64 CPL 0，syscall process context；
* target folio：page cache 中，dirty、uptodate、unlocked；
* user data：已经复制进 folio；
* stable storage：尚未更新；
* inode ``i_rwsem``：已释放；
* superblock write/freeze protection：仍 held；
* writeback mode：``WB_SYNC_ALL``；
* writeback range：file offset 0..4095；
* ``kiocb->ki_pos``：4096；
* local ``pos``：0；
* ``file->f_pos``：0；
* ``PG_writeback``：尚未由本次 ``ext4_writepages`` 建立；
* WRITE bio：尚未建立；
* blk-mq/SCSI/ATA/AHCI objects：尚未建立；
* journal commit：尚未等待；
* ``write()``：尚未返回。

关键边界
--------

#. 新 write 场景独立于前一条 read，不共享其 page-cache 结果。
#. ``O_SYNC`` buffered write 仍先复制到 page cache，再进入同步 writeback。
#. dirty/uptodate folio 不表示数据已经进入 stable storage。
#. delayed-allocation aops 被选中，不表示覆盖已有 extent 时会重新分配磁盘块。
#. ``generic_write_sync`` 对 ``O_SYNC`` 使用 ``datasync=0``。
#. ``file_write_and_wait_range`` 先启动 writeback，再等待 completion。
#. ``WB_SYNC_ALL`` 表示必须完成 data-integrity writeback，不表示 bio 已建立。
#. ``kiocb->ki_pos``、local ``pos`` 与共享 ``file->f_pos`` 尚未全部提交。

下一任务
--------

下一批从 ``ext4_writepages(mapping, wbc)`` 开始：

::

   ext4_writepages
   → scan/lock dirty folio
   → clear dirty for I/O and set PG_writeback
   → prepare writeback extent
   → ordered-data journal dependency
   → ext4_io_submit / WRITE bio
   → block layer / SCSI / libata / AHCI
   → write completion
   → folio end writeback
   → file_write_and_wait_range returns
   → ext4 journal commit / optional flush
   → generic_write_sync returns
   → local pos and file->f_pos commit
   → write() returns userspace

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。
