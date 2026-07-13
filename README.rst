techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第八十九章：ext4 fsync 怎样选择 fast commit 或完整 JBD2 commit？ <docs/tracks/linux-kernel/89-ext4-fsync-chooses-fast-or-full-jbd2-commit.rst>`_
* `第九十章：ext4 barrier 怎样把 journal 顺序落实到设备 cache？ <docs/tracks/linux-kernel/90-ext4-barrier-flushes-device-cache.rst>`_
* `第九十一章：O_SYNC write 怎样提交 file position 并返回用户态？ <docs/tracks/linux-kernel/91-osync-write-returns-to-userspace.rst>`_

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
   LK-WRITE-083..LK-WRITE-091

运行期实验
----------

``read(fd, buf, 4096)`` cold page-cache miss 已完整闭环：

::

   userspace syscall
   → VFS / ext4 / page cache
   → block / SCSI / libata / AHCI
   → completion interrupt
   → user copy
   → userspace RAX=4096

``O_SYNC write(fd, buf, 4096)`` buffered overwrite 也已完整闭环：

::

   userspace write
   → VFS / ext4 buffered copy
   → dirty folio / WB_SYNC_ALL
   → ext4 WRITE bio
   → block / SCSI / libata / AHCI
   → folio_end_writeback
   → fast commit 或完整 JBD2 commit
   → commit barrier 或 standalone FLUSH CACHE
   → file->f_pos = 4096
   → userspace RAX = 4096

当前状态
--------

第二个运行期场景已经结束。writer task 位于 x86-64 CPL 3，``write()`` 返回 4096，``file->f_pos`` 为 4096，target folio clean、uptodate、unlocked。data request、journal durability 与需要的 barrier/flush 均已完成，相关 locks 与 freeze protection 已释放。

下一条 kernel runtime 主线尚未选择。建议从单线程进程直接执行 native x86-64 ``fork()`` syscall 开始，继续贯通 ``kernel_clone()``、``copy_process()``、PID、task、page-table COW、scheduler 与父子进程分别返回。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `Linux Kernel 入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 已完成章节；
#. ``manifests/tracks/linux-kernel.toml``。
