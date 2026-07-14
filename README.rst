techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百一十三章：clock_nanosleep() 怎样建立 hrtimer 并让 parent 阻塞？ <docs/tracks/linux-kernel/113-clock-nanosleep-arms-hrtimer-and-blocks-parent.rst>`_
* `第一百一十四章：local APIC timer interrupt 怎样运行 hrtimer callback 并唤醒 parent？ <docs/tracks/linux-kernel/114-lapic-timer-interrupt-wakes-sleeping-parent.rst>`_
* `第一百一十五章：scheduler 怎样恢复 parent，并让 clock_nanosleep() 返回 0？ <docs/tracks/linux-kernel/115-scheduler-resumes-parent-and-nanosleep-returns.rst>`_

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

最新场景
--------

::

   clock_nanosleep(CLOCK_MONOTONIC, 0, {0, 10ms}, NULL)
   → create on-stack hrtimer_sleeper
   → enqueue CPU0 monotonic hrtimer
   → program local APIC TSC deadline
   → parent TASK_INTERRUPTIBLE and schedule to idle/0
   → LOCAL_TIMER_VECTOR
   → hrtimer_interrupt / hrtimer_wakeup
   → try_to_wake_up(parent)
   → scheduler restores parent kernel stack
   → clock_nanosleep returns userspace RAX=0

固定timer slack为0、只有CPU0 online、没有signal或其他runnable task。monotonic elapsed不早于10 ms；sleep completion不进入restart或remaining-time copyout。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
