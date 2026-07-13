techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第八十章：AHCI 中断怎样确认完成的 tag，并把结果交回 SCSI？ <docs/tracks/linux-kernel/80-ahci-interrupt-completes-ata-and-scsi-command.rst>`_
* `第八十一章：blk-mq completion 怎样结束 bio，并让 ext4 folio 变成 uptodate？ <docs/tracks/linux-kernel/81-block-completion-marks-ext4-folio-uptodate.rst>`_
* `第八十二章：reader task 怎样复制 folio，并让 read() 返回用户态？ <docs/tracks/linux-kernel/82-reader-copies-folio-and-returns-from-read.rst>`_

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

``read()`` 运行期主线
--------------------

固定场景：native x86-64 ``read(fd, buf, 4096)``，已打开的普通 ext4 文件，offset 0，buffered I/O，目标 folio cold miss，文件数据位于 q35 ICH9 AHCI SATA port 0 的启动盘。

::

   userspace read(fd, buf, 4096)
   → entry_SYSCALL_64 / __x64_sys_read
   → fd / VFS / ext4 buffered read
   → cold page-cache miss
   → ext4 READ bio
   → submit_bio_noacct / partition remap
   → blk-mq request and tag
   → SCSI READ CDB
   → libata ATA taskfile
   → AHCI H2D FIS / PRDT / PxCI[tag]
   → AHCI completion interrupt
   → ata_qc_complete / scsi_done
   → blk-mq / bio / ext4 completion
   → folio_end_read(folio, true)
   → folio uptodate + unlock
   → copy_folio_to_iter(user buffer)
   → file->f_pos = 4096
   → SYSRETQ or IRETQ
   → userspace receives RAX = 4096

当前状态
--------

第一个运行期场景已经完整闭环：用户 buffer 含有文件 offset 0..4095 的数据，``file->f_pos`` 已推进到 4096，目标 folio 保留在 page cache 中且处于 uptodate、unlocked 状态，相关 AHCI/SCSI/blk-mq request 与 tag 已完成并释放。

下一条运行期故事尚未选定。开始新主线前必须重新固定 syscall、对象、缓存状态、文件系统状态和目标子系统，不能假装它在时间线上自动接续本次 ``read()``。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节；
#. ``manifests/tracks/linux-kernel.toml``。