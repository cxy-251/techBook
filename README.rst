techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百零七章：首次 buffered write 怎样只预留空间而不分配物理块？ <docs/tracks/linux-kernel/107-first-buffered-write-creates-delalloc-state.rst>`_
* `第一百零八章：fsync() 怎样让 writeback 分配第一个 unwritten extent 并提交数据？ <docs/tracks/linux-kernel/108-fsync-writeback-allocates-first-unwritten-extent.rst>`_
* `第一百零九章：data completion 怎样转换 extent，并让 fsync() 真正返回？ <docs/tracks/linux-kernel/109-write-completion-converts-extent-and-fsync-returns.rst>`_

固定来源
--------

::

   x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

已经完成
--------

::

   LK-BOOT-001..LK-BOOT-073
   LK-READ-074..LK-READ-082
   LK-WRITE-083..LK-WRITE-091
   LK-FORK-092..LK-FORK-094
   LK-COW-095..LK-COW-097
   LK-EXEC-098..LK-EXEC-100
   LK-EXIT-101..LK-EXIT-103
   LK-OPEN-104..LK-OPEN-106
   LK-DELALLOC-107..LK-DELALLOC-109

最新场景
--------

::

   write(6, buf, 4096)
   → page-cache folio + delayed-allocation reservation
   → write returns 4096 before physical allocation
   → fsync(6)
   → allocate physical block P as unwritten extent
   → data bio through blk-mq / SCSI / libata / AHCI
   → successful completion
   → deferred unwritten-to-written conversion
   → full JBD2 commit + required device flush
   → userspace fsync result 0

fd 6仍打开，``f_pos=4096``。文件size与 ``i_disksize`` 均为4096，logical block 0已经映射为written extent，page-cache folio clean，create、extent、size和data满足本次fsync durability要求。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
