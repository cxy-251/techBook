techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百四十章：signalfd4() 怎样把阻塞信号变成可poll的fd并挂进epoll？ <docs/tracks/linux-kernel/140-signalfd4-creates-pollable-signal-fd-and-epoll-registration.rst>`_
* `第一百四十一章：tgkill() 怎样让blocked SIGUSR1经signalfd callback唤醒epoll_wait？ <docs/tracks/linux-kernel/141-tgkill-wakes-signalfd-epoll-waiter.rst>`_
* `第一百四十二章：parent怎样从epoll event进入signalfd read并取出128字节siginfo？ <docs/tracks/linux-kernel/142-epoll-returns-signalfd-event-and-read-dequeues-siginfo.rst>`_

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

最新场景
--------

::

   block SIGUSR1 in parent/helper
   → signalfd4(-1, mask(SIGUSR1), SFD_CLOEXEC) publishes fd 6
   → epoll_create1(EPOLL_CLOEXEC) publishes fd 7
   → EPOLL_CTL_ADD attaches callback to shared sighand signalfd wait queue
   → parent blocks exclusively on eventpoll wait queue
   → helper tgkill targets parent with blocked SIGUSR1
   → signalfd_notify queues an epoll ready candidate and wakes parent
   → parent re-polls signalfd and receives {EPOLLIN, data=0x51FD6}
   → epoll_wait returns 1
   → read(6) dequeues parent private pending signal
   → one 128-byte signalfd_siginfo is copied and read returns 128

最终fd 6/7与registration仍active。parent private pending中的SIGUSR1已消费；level-triggered epitem暂留在ready list，等待下一次epoll scan重新验证并清理。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
