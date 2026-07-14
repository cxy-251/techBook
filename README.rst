techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百二十二章：close(7) 怎样撤销 write end 并把 writers 降为 0？ <docs/tracks/linux-kernel/122-close-write-end-drops-pipe-writers.rst>`_
* `第一百二十三章：空管道在 writers=0 时，read() 为什么直接返回 EOF？ <docs/tracks/linux-kernel/123-empty-pipe-without-writers-returns-eof.rst>`_
* `第一百二十四章：最后一次 close(6) 怎样释放pipe page、ring与pseudo inode？ <docs/tracks/linux-kernel/124-final-read-end-close-frees-pipe.rst>`_

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
   LK-SLEEP-113..LK-SLEEP-115
   LK-SIGNAL-116..LK-SIGNAL-118
   LK-PIPE-119..LK-PIPE-121
   LK-PIPECLOSE-122..LK-PIPECLOSE-124

最新场景
--------

::

   helper close(7)
   → remove write fd from shared files_struct
   → fput_close_sync / pipe_release
   → writers 1 → 0, files 2 → 1
   → parent read(6, eofbuf, 5)
   → empty ring + writers=0
   → return EOF, RAX=0, no wait and no copy
   → parent close(6)
   → readers 1 → 0, files 1 → 0
   → free cached page Q, 16-slot ring and pipe_inode_info
   → release final pseudo dentry/inode references

最终fd 6/7均已关闭，anonymous pipe不再可访问；page Q已归还page allocator。pseudo dentry/inode已退出活动对象图，底层slab memory可按VFS/RCU规则延后回收。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
