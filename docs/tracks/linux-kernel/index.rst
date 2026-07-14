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
   → inotify_init1 creates blocking close-on-exec fd 6
   → inotify_add_watch installs wd 1 on ext4 /work
   → internal mark watches CREATE, CLOSE_WRITE, UNMOUNT and child events
   → eventpoll fd 7 attaches callback to group notification wait queue
   → parent blocks on eventpoll wait queue
   → helper creates /work/new.txt as fd 8
   → fsnotify queues wd1 IN_CREATE and wakes parent
   → helper write MODIFY is ignored by the selected watch mask
   → helper close queues wd1 IN_CLOSE_WRITE without merging
   → epoll_wait returns EPOLLIN and data 0x494E4F36
   → read(6) copies two 32-byte FIFO records and returns 64
   → notification queue becomes empty
   → watch and fd 6/7 remain active
   → level-triggered epitem remains stale-ready

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

固定commit的 ``Makefile`` 标识为Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 是历史版本标签错误；技术事实与链接一直以固定commit为准。

最新三章
--------

#. `第一百五十八章：inotify怎样建立目录watch并让parent阻塞在epoll_wait？ <158-inotify-watch-registers-with-epoll-and-blocks-parent.rst>`_
#. `第一百五十九章：helper创建并关闭new.txt时，fsnotify怎样排入两条inotify事件？ <159-fsnotify-queues-create-and-close-write-events.rst>`_
#. `第一百六十章：parent怎样从epoll event读取两条inotify_event记录？ <160-epoll-returns-inotify-and-read-consumes-two-records.rst>`_

下一候选
--------

::

   epoll_wait(7, events2, 1, 0)
   → re-poll empty inotify queue and remove stale-ready item
   → inotify_rm_watch(6, 1)
   → mark teardown queues IN_IGNORED and removes wd from IDR
   → callback makes epitem ready again
   → epoll_wait returns EPOLLIN
   → read(6) consumes a 16-byte IN_IGNORED record
   → EPOLL_CTL_DEL removes callback and epitem
   → close(6) destroys fsnotify group
   → close(7) releases eventpoll

章节组织
--------

正文沿时间线连续讲述。故事达到适合一次阅读的篇幅，并遇到执行者、CPU mode、运行环境或控制入口交接时换章。每章末尾记录当前执行者、当前状态和下一入口。
