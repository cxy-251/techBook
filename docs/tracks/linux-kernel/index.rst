Linux Kernel
============

这本书讲 Linux 内核。开头从设备上电后的真实执行过程进入，先交代内核取得控制权之前发生的必要故事；启动链完成后，切换到明确的运行期入口继续追踪。

当前正文
--------

目录按文件名前缀保持数字顺序。每个章节标题由对应RST文档的一级标题提供。

.. toctree::
   :maxdepth: 1
   :glob:

   0[1-9]-*
   [1-9][0-9]-*
   1[0-9][0-9]-*

当前主线
--------

::

   x86-64 → QEMU q35 → SeaBIOS → GNU GRUB 2.14 i386-pc
   → bzImage → Linux 7.2-rc1
   → boot handoff complete
   → cold-miss read and O_SYNC write complete
   → fork / COW / static exec / exit-wait complete
   → ext4 create-write-fsync-unlink-close lifecycle complete
   → natural and SIGUSR1-interrupted monotonic nanosleep complete
   → anonymous pipe lifecycle complete
   → private futex wait/wake complete
   → eventfd, signalfd, timerfd, pidfd and inotify eventpoll lifecycles complete
   → socketpair creates connected AF_UNIX stream fd 6/7
   → eventpoll fd 8 watches fd 6 for EPOLLIN|EPOLLRDHUP
   → parent blocks on eventpoll wait queue
   → helper writes hello through fd 7
   → one skb enters fd 6 receive queue and wakes parent
   → epoll_wait delivers EPOLLIN
   → read(6) consumes 5 bytes and empties the queue
   → next epoll_wait re-polls and removes stale-ready membership
   → helper shutdown(7,SHUT_WR)
   → fd 7 gains SEND_SHUTDOWN and fd 6 gains RCV_SHUTDOWN
   → socket state-change callback wakes parent
   → epoll_wait delivers EPOLLIN|EPOLLRDHUP
   → read(6) returns EOF 0
   → fd 6/7/8 remain open and registration remains persistent-ready

完成范围
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
   LK-TIMERFDCLOSE-149..LK-TIMERFDCLOSE-151
   LK-PIDFD-152..LK-PIDFD-154
   LK-PIDFDCLOSE-155..LK-PIDFDCLOSE-157
   LK-INOTIFY-158..LK-INOTIFY-160
   LK-INOTIFYCLOSE-161..LK-INOTIFYCLOSE-163
   LK-UNIXSOCK-164..LK-UNIXSOCK-166

固定commit的 ``Makefile`` 标识为Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 是历史版本标签错误；技术事实与链接一直以固定commit为准。

进度
----

当前完成166章。项目没有预设固定总章数，也没有固定195章目标。后续按源码主线与必要场景自然推进，因此当前不计算剩余章数。

最新三章
--------

#. `第一百六十四章：socketpair怎样建立双向Unix stream并让parent阻塞在epoll_wait？ <164-unix-socketpair-registers-with-epoll-and-blocks-parent.rst>`_
#. `第一百六十五章：helper写入hello时，Unix stream skb怎样唤醒epoll并让read返回5？ <165-unix-stream-write-wakes-epoll-and-read-consumes-skb.rst>`_
#. `第一百六十六章：shutdown(SHUT_WR)怎样让peer收到EPOLLRDHUP并让read返回EOF？ <166-unix-stream-shutdown-wakes-rdhup-and-read-returns-eof.rst>`_

下一候选
--------

::

   epoll_ctl(8, EPOLL_CTL_DEL, 6, NULL)
   → detach socket wait callback and epitem
   close(6)
   → release socket A and notify peer B of disconnect
   close(7)
   → release socket B and mutual peer references
   close(8)
   → release empty eventpoll

章节组织
--------

正文沿时间线连续讲述。故事达到适合一次阅读的篇幅，并遇到执行者、CPU mode、运行环境或控制入口交接时换章。每章末尾记录当前执行者、当前状态和下一入口。
