techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百二十五章：FUTEX_WAIT_PRIVATE 怎样建立private key并把parent排入hash bucket？ <docs/tracks/linux-kernel/125-futex-wait-private-enqueues-parent.rst>`_
* `第一百二十六章：FUTEX_WAKE_PRIVATE 怎样移除waiter并把parent放回runqueue？ <docs/tracks/linux-kernel/126-futex-wake-private-dequeues-and-wakes-parent.rst>`_
* `第一百二十七章：parent 被唤醒后，futex_wait 为什么返回0却不自动重读用户字？ <docs/tracks/linux-kernel/127-futex-wait-returns-without-rechecking-user-word.rst>`_

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

最新场景
--------

::

   private atomic user word U = 0
   → parent FUTEX_WAIT_PRIVATE expected=0
   → build key from shared mm + virtual page base + page offset
   → enqueue stack futex_q in per-mm hash bucket H
   → parent TASK_INTERRUPTIBLE and schedules out
   → helper release-store U=1
   → helper FUTEX_WAKE_PRIVATE nr=1
   → remove q, set q.lock_ptr=NULL and wake parent
   → helper returns 1
   → parent resumes original futex stack and returns 0

最终U仍为1，bucket H已没有本次waiter。kernel不会在wake成功后自动重读U；用户代码仍必须在condition loop中执行acquire load并重新判断。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
