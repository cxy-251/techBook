Linux Kernel
============

这本书讲 Linux 内核。开头从设备上电后的真实执行过程进入，先交代内核取得控制权之前发生的必要故事；启动链完成后，切换到明确的运行期入口继续追踪。

当前正文
--------

目录按文件名前缀保持数字顺序。每个章节标题由对应RST文档的一级标题提供。

.. toctree::
   :maxdepth: 1
   :glob:

   [0-9][0-9][0-9]-*

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
   → Unix stream socketpair data, half-close and final teardown complete
   → server fd 6 listens on 127.0.0.1:28080
   → client fd 7 autobinds 127.0.0.1:40000 and sends SYN
   → listener creates request R and sends SYN-ACK
   → release_sock drains SYN-ACK from client backlog
   → client enters TCP_ESTABLISHED and sends final ACK
   → final ACK replaces R's ehash identity with server child H
   → R becomes accept FIFO node and H enters TCP_ESTABLISHED
   → wait_woken skips scheduling because WQ_FLAG_WOKEN is already set
   → client socket API state becomes SS_CONNECTED
   → connect returns 0
   → server accept queue contains one unaccepted child

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
   LK-UNIXSOCKCLOSE-167..LK-UNIXSOCKCLOSE-169
   LK-TCPLISTEN-170..LK-TCPLISTEN-172
   LK-TCPCONNECT-173..LK-TCPCONNECT-175
   LK-TCPHANDSHAKE-176..LK-TCPHANDSHAKE-178

固定commit的 ``Makefile`` 标识为Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 是历史版本标签错误；技术事实与链接一直以固定commit为准。

进度
----

当前完成178章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

最新三章
--------

#. `第一百七十六章：release_sock怎样处理SYN-ACK并让client发送最终ACK？ <176-release-sock-processes-synack-and-sends-final-ack.rst>`_
#. `第一百七十七章：最终ACK怎样把request_sock替换成ESTABLISHED server child？ <177-final-ack-replaces-request-with-established-server-child.rst>`_
#. `第一百七十八章：blocking connect为什么无需真正睡眠就返回0？ <178-blocking-connect-skips-schedule-and-returns-zero.rst>`_

下一候选
--------

::

   accept4(6,...,SOCK_CLOEXEC)
   → remove R/H from listener accept queue
   → sk_ack_backlog 1 → 0
   → allocate accepted struct socket
   → graft H to accepted socket
   → create sockfs file
   → publish close-on-exec fd 8
   → copy peer sockaddr
   → return 8

章节组织
--------

正文沿时间线连续讲述。故事达到适合一次阅读的篇幅，并遇到执行者、CPU mode、运行环境或控制入口交接时换章。每章末尾记录当前执行者、当前状态和下一入口；不要在一批的最后一章重复概括前两章。
