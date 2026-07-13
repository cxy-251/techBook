techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第七十七章：READ bio 怎样通过校验与分区重映射进入 blk-mq？ <docs/tracks/linux-kernel/77-read-bio-enters-generic-block-submission.rst>`_
* `第七十八章：blk-mq 怎样把 bio 变成 SCSI READ request？ <docs/tracks/linux-kernel/78-blk-mq-builds-scsi-read-request.rst>`_
* `第七十九章：SCSI READ 怎样变成 ATA taskfile 并写入 AHCI command slot？ <docs/tracks/linux-kernel/79-scsi-read-becomes-ahci-command.rst>`_

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d
   → boot handoff complete
   → fixed runtime read(fd, buf, 4096)

固定 commit 的真实版本是 Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 属于历史显示标签错误；源码事实以固定 commit 为准。

已经完成：

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-079

当前运行期路径：

::

   userspace read(fd, buf, 4096)
   → entry_SYSCALL_64 / __x64_sys_read
   → fd / VFS / ext4
   → cold page-cache miss
   → ext4 READ bio
   → submit_bio_noacct
   → /dev/sda1 partition remap
   → blk_mq_submit_bio
   → blk-mq request and tag
   → SCSI READ CDB
   → libata ATA taskfile
   → DMA-map folio scatterlist
   → AHCI H2D Register FIS
   → AHCI PRDT and command header
   → PxCI[tag] = 1

当前 AHCI command 已提交，DMA completion 尚未发生。下一批从 AHCI interrupt path 开始，继续追踪 ``ata_qc_complete``、``scsi_done``、blk-mq/bio completion、``mpage_end_io``、folio unlock、``copy_folio_to_iter`` 与 x86 syscall return。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节；
#. ``manifests/tracks/linux-kernel.toml``。