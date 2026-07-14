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
   → eventfd, signalfd, timerfd and pidfd eventpoll lifecycles complete
   → inotify watches /work for CREATE and CLOSE_WRITE
   → helper creates, writes and closes /work/new.txt
   → epoll_wait delivers EPOLLIN
   → read copies IN_CREATE and IN_CLOSE_WRITE records
   → zero-time epoll_wait removes stale-ready membership
   → inotify_rm_watch queues wd1 IN_IGNORED before IDR removal
   → mark detaches from group and /work inode connector
   → epoll_wait delivers IN_IGNORED readiness
   → read copies one 16-byte IN_IGNORED record
   → EPOLL_CTL_DEL removes callback and epitem
   → close(6) destroys fsnotify group and waits mark SRCU reaper
   → close(7) releases empty eventpoll
   → parent CPL3 with close RAX=0 and fd 6/7 closed
   → /work/new.txt remains present

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

固定commit的 ``Makefile`` 标识为Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 是历史版本标签错误；技术事实与链接一直以固定commit为准。

最新三章
--------

#. `第一百六十一章：零超时epoll_wait怎样清除inotify的stale-ready item？ <161-zero-time-epoll-wait-removes-inotify-stale-ready-item.rst>`_
#. `第一百六十二章：inotify_rm_watch怎样先排入IN_IGNORED再销毁mark？ <162-inotify-rm-watch-queues-ignored-and-destroys-mark.rst>`_
#. `第一百六十三章：读取IN_IGNORED后，close怎样释放inotify group与eventpoll？ <163-read-ignored-and-final-close-free-inotify-eventpoll.rst>`_

下一候选
--------

::

   socketpair(AF_UNIX, SOCK_STREAM|SOCK_CLOEXEC, 0, sv)
   → fd 6/7 form one connected unix socket pair
   epoll_create1(EPOLL_CLOEXEC) → fd 8
   epoll_ctl(8, ADD, 6, EPOLLIN|EPOLLRDHUP)
   → parent blocks in epoll_wait
   → helper write(7, "hello", 5)
   → unix stream receive queue wakes parent
   → parent epoll_wait returns and read(6) consumes 5 bytes
   → helper shutdown(7, SHUT_WR)
   → parent observes EPOLLRDHUP and read EOF

章节组织
--------

正文沿时间线连续讲述。故事达到适合一次阅读的篇幅，并遇到执行者、CPU mode、运行环境或控制入口交接时换章。每章末尾记录当前执行者、当前状态和下一入口。
