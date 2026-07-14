techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百一十章：unlinkat() 怎样锁住父目录并进入 ext4_unlink()？ <docs/tracks/linux-kernel/110-unlinkat-locks-parent-and-enters-ext4-unlink.rst>`_
* `第一百一十一章：ext4_unlink() 怎样删除名称，却让 fd 6 继续访问 inode？ <docs/tracks/linux-kernel/111-ext4-unlink-removes-name-and-keeps-open-inode.rst>`_
* `第一百一十二章：close(6) 怎样触发最后一次 __fput() 并回收 ext4 inode？ <docs/tracks/linux-kernel/112-close-evicts-unlinked-ext4-inode.rst>`_

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
   LK-UNLINK-110..LK-UNLINK-112

最新场景
--------

::

   unlinkat(AT_FDCWD, "/work/demo.txt", 0)
   → lock /work and find cached positive dentry
   → ext4_delete_entry
   → nlink 1 -> 0
   → add orphan tracking
   → pathname disappears while fd 6 remains valid
   → close(6)
   → file_close_fd / fput_close_sync / __fput
   → final dput / iput / ext4_evict_inode
   → remove extent P and free inode allocation in JBD2 transaction
   → userspace RAX = 0

当前运行系统中pathname、fd、dentry、extent与inode均已删除。block与inode free metadata已经进入JBD2 transaction；没有显式sync，因此close返回不保证该删除事务已经持久化。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
