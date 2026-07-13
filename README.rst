techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第八十六章：ext4 writeback 怎样把 dirty folio 变成 WRITE bio？ <docs/tracks/linux-kernel/86-ext4-writeback-builds-write-bio.rst>`_
* `第八十七章：WRITE bio 怎样变成 AHCI command 并写入 PxCI？ <docs/tracks/linux-kernel/87-write-bio-becomes-ahci-command.rst>`_
* `第八十八章：WRITE completion 怎样结束 folio writeback，并让 O_SYNC 等待继续？ <docs/tracks/linux-kernel/88-write-completion-ends-folio-writeback.rst>`_

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
   LK-WRITE-083..LK-WRITE-088

当前 O_SYNC write 主线
----------------------

固定场景：native x86-64 ``write(fd, buf, 4096)``，文件以 ``O_SYNC`` 打开，普通 ext4 ``data=ordered`` buffered full-block overwrite，offset 0，已有 initialized extent。

::

   userspace write(fd, buf, 4096)
   → syscall / VFS / ext4 buffered copy
   → dirty page-cache folio
   → generic_write_sync
   → WB_SYNC_ALL
   → ext4_writepages
   → clear dirty-for-I/O / PG_writeback
   → ext4 WRITE bio
   → block submission / partition remap
   → blk-mq request
   → SCSI WRITE
   → libata ATA WRITE
   → AHCI H2D FIS / PRDT / PxCI
   → AHCI completion interrupt
   → SCSI / blk-mq / bio completion
   → ext4_end_bio
   → folio_end_writeback
   → file_write_and_wait_range returns 0

当前状态
--------

file data WRITE 已完成，target folio 当前 clean、uptodate、unlocked，``PG_writeback=0``。``kiocb->ki_pos=4096``，local ``pos`` 与共享 ``file->f_pos`` 仍为 0。

当前尚未完成 JBD2 transaction commit，也尚未确认是否需要 block-device cache flush，因此 O_SYNC syscall 仍不能返回。下一入口是 ``ext4_fsync_journal(inode, false, &needs_barrier)``。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节；
#. ``manifests/tracks/linux-kernel.toml``。
