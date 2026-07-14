techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百三十四章：epoll_ctl(ADD) 怎样把eventfd callback挂进wait queue？ <docs/tracks/linux-kernel/134-epoll-add-attaches-eventfd-callback.rst>`_
* `第一百三十五章：epoll_wait() 怎样把parent挂到eventpoll自己的wait queue？ <docs/tracks/linux-kernel/135-epoll-wait-blocks-on-eventpoll-wq.rst>`_
* `第一百三十六章：eventfd write怎样触发epoll callback并让epoll_wait返回1？ <docs/tracks/linux-kernel/136-eventfd-write-wakes-epoll-and-delivers-level-event.rst>`_

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

最新场景
--------

::

   eventfd2(0, EFD_CLOEXEC) -> fd 6
   epoll_create1(EPOLL_CLOEXEC) -> fd 7
   epoll_ctl(7, EPOLL_CTL_ADD, 6, EPOLLIN)
   → ep_poll_callback entry attaches to eventfd wait queue
   → parent epoll_wait(7, events, 1, -1)
   → parent blocks exclusively on eventpoll wait queue
   → helper writes u64 5 to eventfd
   → callback adds epitem to ready list and wakes parent
   → parent receives { EPOLLIN, data=0xEFD6 }
   → epoll_wait returns 1

最终fd 6/7仍打开；eventfd counter为5。level-triggered epitem仍在ready list，因为epoll只报告readiness，没有消费counter。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
