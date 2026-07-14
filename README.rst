techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百四十六章：timerfd怎样建立一次性hrtimer并让parent阻塞在epoll_wait？ <docs/tracks/linux-kernel/146-timerfd-creates-arms-and-registers-with-epoll.rst>`_
* `第一百四十七章：local APIC定时器中断怎样让timerfd callback唤醒epoll_wait？ <docs/tracks/linux-kernel/147-lapic-hrtimer-callback-wakes-timerfd-epoll.rst>`_
* `第一百四十八章：parent怎样从epoll event进入timerfd read并取出expiration count？ <docs/tracks/linux-kernel/148-epoll-returns-timerfd-event-and-read-consumes-expiration.rst>`_

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
   LK-EPOLL-134..LK-EPOLL-136
   LK-EPOLLCLOSE-137..LK-EPOLLCLOSE-139
   LK-SIGNALFD-140..LK-SIGNALFD-142
   LK-SIGNALFDCLOSE-143..LK-SIGNALFDCLOSE-145
   LK-TIMERFD-146..LK-TIMERFD-148

最新场景
--------

::

   timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC) -> fd 6
   → timerfd_settime arms one-shot relative 20ms hrtimer on CPU0
   → epoll_create1(EPOLL_CLOEXEC) -> fd 7
   → EPOLL_CTL_ADD attaches callback to timerfd wait queue
   → parent blocks exclusively on eventpoll wait queue
   → local APIC timer interrupt enters hrtimer_interrupt
   → timerfd_tmrproc changes ticks 0 → 1 and wakes epoll
   → parent receives {EPOLLIN, data=0x71FD6}
   → epoll_wait returns 1
   → read(6) consumes u64 expiration count 1 and returns 8

最终fd 6/7与registration仍active。timerfd hrtimer已经inactive，``ticks=0``、``expired=0``；level-triggered epitem暂留ready list，等待下一次epoll scan重新验证。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
