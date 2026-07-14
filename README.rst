techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百三十一章：close(6) 怎样撤销eventfd fd并同步进入最后一次__fput()？ <docs/tracks/linux-kernel/131-close-eventfd-fd-enters-final-fput.rst>`_
* `第一百三十二章：eventfd_release() 怎样发送EPOLLHUP并释放eventfd_ctx？ <docs/tracks/linux-kernel/132-eventfd-release-sends-hup-and-frees-ctx.rst>`_
* `第一百三十三章：__fput() 怎样释放anon-inode path并让close()返回0？ <docs/tracks/linux-kernel/133-final-eventfd-file-teardown-returns-close.rst>`_

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
   LK-FUTEX-125..LK-FUTEX-127
   LK-EVENTFD-128..LK-EVENTFD-130
   LK-EVENTFDCLOSE-131..LK-EVENTFDCLOSE-133

最新场景
--------

::

   parent close(6)
   → remove fd 6 from shared files_struct
   → clear open and close-on-exec bookkeeping
   → filp_flush returns 0
   → fput_close_sync enters final __fput
   → eventpoll_release finds no registration
   → eventfd_release sends EPOLLHUP to an empty wait queue
   → eventfd_ctx_put changes kref 1 → 0
   → return internal id to eventfd_ida and free ctx
   → dput per-file [eventfd] pseudo dentry
   → mntput per-file anon_inodefs mount reference
   → file_free and close returns 0

最终fd 6已关闭；eventfd file、ctx、internal id和per-file pseudo path均已结束生命周期。全局 ``anon_inode_mnt`` 与singleton ``anon_inode_inode`` 继续存在。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
