techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百二十八章：eventfd2() 怎样建立counter并发布fd 6？ <docs/tracks/linux-kernel/128-eventfd2-creates-counter-and-publishes-fd.rst>`_
* `第一百二十九章：eventfd read() 怎样在counter为0时进入locked wait queue？ <docs/tracks/linux-kernel/129-empty-eventfd-read-enters-locked-wait-queue.rst>`_
* `第一百三十章：eventfd write() 怎样唤醒reader并让read()返回counter？ <docs/tracks/linux-kernel/130-eventfd-write-wakes-reader-and-read-returns-counter.rst>`_

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

最新场景
--------

::

   eventfd2(0, EFD_CLOEXEC)
   → allocate eventfd_ctx and anon-inode file
   → publish shared fd 6 with count=0
   → parent read(6, &value, 8)
   → non-exclusive TASK_INTERRUPTIBLE wait on ctx->wqh
   → helper write(6, value=3, 8)
   → count 0 → 3 and wake parent
   → parent consumes full counter 3
   → count 3 → 0
   → read returns 8 with value=3

最终fd 6仍打开；parent位于CPU0、CPL 3，read返回8，用户buffer为3。eventfd counter已清零，wait queue不再包含本次waiter。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
