techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百四十三章：零超时epoll_wait() 怎样清理signalfd的stale-ready item？ <docs/tracks/linux-kernel/143-zero-time-epoll-wait-removes-signalfd-stale-ready-item.rst>`_
* `第一百四十四章：EPOLL_CTL_DEL 怎样拆除signalfd callback与epitem？ <docs/tracks/linux-kernel/144-epoll-del-detaches-signalfd-callback.rst>`_
* `第一百四十五章：close() 怎样释放signalfd与eventpoll，却保留共享sighand wait queue？ <docs/tracks/linux-kernel/145-final-close-frees-signalfd-and-eventpoll.rst>`_

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

最新场景
--------

::

   epoll_wait(7, events, 1, 0)
   → re-poll signalfd after SIGUSR1 was consumed
   → remove stale-ready epitem and return 0
   → epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → detach callback from shared sighand signalfd wait queue
   → erase epitem and drop eventpoll refcount 2 → 1
   → close(6) frees signalfd ctx/file
   → close(7) ends eventpoll lifetime through kfree_rcu

最终fd 6/7均已关闭。signalfd ctx与callback同步释放；epitem与eventpoll退出活动对象图。共享 ``sighand_struct`` 及其 ``signalfd_wqh`` 继续存在，parent/helper的blocked mask仍包含 ``SIGUSR1``。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
