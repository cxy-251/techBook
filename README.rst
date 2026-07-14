techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百三十七章：eventfd read() 怎样清零counter却暂时留下ready epitem？ <docs/tracks/linux-kernel/137-eventfd-read-clears-count-but-leaves-ready-item.rst>`_
* `第一百三十八章：零超时epoll_wait() 怎样重新poll并清理stale-ready item？ <docs/tracks/linux-kernel/138-zero-time-epoll-wait-removes-stale-ready-item.rst>`_
* `第一百三十九章：EPOLL_CTL_DEL与close()怎样拆除callback并释放eventfd/eventpoll？ <docs/tracks/linux-kernel/139-epoll-del-and-final-close-free-eventfd-eventpoll.rst>`_

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

最新场景
--------

::

   parent read(6, &value, 8)
   → eventfd count 5 → 0
   → EPOLLOUT wake does not match EPOLLIN interest
   → level-triggered epitem remains temporarily on ready list
   → epoll_wait(7, events2, 1, 0)
   → re-poll finds no EPOLLIN
   → remove stale-ready membership and return 0
   → epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
   → remove callback and epitem registration
   → close(6) frees eventfd ctx/file
   → close(7) ends eventpoll lifetime through kfree_rcu

最终fd 6/7均已关闭。eventfd ctx与两份anon-inode file/path已释放；callback同步释放，epitem与eventpoll已经退出活动对象图，其storage由RCU grace period后回收。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、``project/STATE.rst``、章节目录和manifest。
