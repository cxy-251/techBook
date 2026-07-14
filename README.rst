techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百零四章：openat() 怎样保留 fd 并把 /work/demo.txt 解析成 negative dentry？ <docs/tracks/linux-kernel/104-openat-resolves-negative-dentry.rst>`_
* `第一百零五章：ext4_create() 怎样分配 inode 并把 demo.txt 写进目录？ <docs/tracks/linux-kernel/105-ext4-create-allocates-inode-and-dirent.rst>`_
* `第一百零六章：VFS 怎样打开新 inode、发布 fd 6 并让 openat() 返回？ <docs/tracks/linux-kernel/106-vfs-opens-and-publishes-new-fd.rst>`_

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

最新场景
--------

::

   openat(AT_FDCWD, "/work/demo.txt", O_CREAT|O_EXCL|O_WRONLY, 0644)
   → reserve fd 6
   → RCU pathname walk to /work
   → exclusive final lookup / negative dentry
   → ext4 inode and directory entry metadata transaction
   → vfs_open / ext4_file_open
   → fd_install(6, file)
   → userspace RAX = 6

最终文件mode为0644、nlink为1、size为0，尚未分配data block。create metadata已进入JBD2 transaction，但 ``openat`` 返回不保证transaction已经持久化。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
