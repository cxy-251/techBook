techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百一十九章：pipe2() 怎样建立匿名管道并发布 fd 6/7？ <docs/tracks/linux-kernel/119-pipe2-builds-anonymous-pipe-and-publishes-fds.rst>`_
* `第一百二十章：空管道 read() 怎样进入 exclusive wait queue 并阻塞？ <docs/tracks/linux-kernel/120-empty-pipe-read-enters-exclusive-wait.rst>`_
* `第一百二十一章：pipe write() 怎样唤醒reader并让 read() 返回5？ <docs/tracks/linux-kernel/121-pipe-write-wakes-reader-and-read-returns.rst>`_

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

最新场景
--------

::

   pipe2(pipefd, O_CLOEXEC)
   → allocate pipefs inode, pipe_inode_info and 16-slot ring
   → publish read fd 6 and write fd 7
   → parent read(6, buf, 5) on empty pipe
   → exclusive TASK_INTERRUPTIBLE wait on rd_wait
   → helper write(7, "hello", 5)
   → allocate anonymous page and insert one pipe_buffer
   → sync wake reader
   → parent consumes 5 bytes and returns RAX=5

最终pipe仍保持open，``head=tail=1``、occupancy为0；首次data page没有立即归还buddy，而是缓存到 ``pipe->tmp_page[0]`` 供后续write复用。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
