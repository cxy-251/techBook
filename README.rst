techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百一十六章：tgkill() 怎样排入 SIGUSR1 并唤醒 nanosleep 中的 parent？ <docs/tracks/linux-kernel/116-tgkill-wakes-interruptible-nanosleep.rst>`_
* `第一百一十七章：parent 怎样取消 hrtimer、写回 remaining 并进入 SIGUSR1 handler？ <docs/tracks/linux-kernel/117-nanosleep-cancels-timer-and-builds-signal-frame.rst>`_
* `第一百一十八章：rt_sigreturn() 怎样恢复被 SIGUSR1 中断的 clock_nanosleep 上下文？ <docs/tracks/linux-kernel/118-rt-sigreturn-restores-interrupted-nanosleep.rst>`_

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

最新场景
--------

::

   parent clock_nanosleep(CLOCK_MONOTONIC, 0, {0,10ms}, &remaining)
   → helper tgkill(P, P, SIGUSR1) at T0+4ms
   → signal_wake_up / try_to_wake_up(parent)
   → parent resumes original do_nanosleep stack
   → cancel still-active hrtimer
   → copy positive remaining time
   → -ERESTART_RESTARTBLOCK becomes -EINTR
   → x64 rt signal frame and SIGUSR1 handler
   → __restore_rt / rt_sigreturn
   → restore original mask, registers and FPU state
   → raw userspace RAX = -EINTR

固定只有CPU0 online，handler使用 ``SA_SIGINFO | SA_RESTORER``，没有 ``SA_RESTART``、``SA_NODEFER`` 或alternate stack。原sleep timer没有到期，remaining满足 ``0 < remaining < 6 ms``。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
