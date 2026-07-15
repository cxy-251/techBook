Linux Kernel
============

这本书讲 Linux 内核。开头从设备上电后的真实执行过程进入，先交代内核取得控制权之前发生的必要故事；启动链完成后，切换到明确的运行期入口继续追踪。

回溯审查状态
------------

历史正文存在001—193章。当前暂停后续生产，从001开始按固定源码顺序审查；已验证游标与
下一批不在本目录复制。不同对话的接续以
`项目状态 <../../../project/STATE.rst>`_ 和
`审查账本 <../../../project/audits/linux-kernel/index.rst>`_ 为准。

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
   → client fd 7 completes loopback three-way handshake
   → server child H enters accept queue without socket/file/fd
   → accept4 reserves close-on-exec fd 8
   → create accepted socket AS, sockfs inode I8 and blocking file F8
   → remove R/H from accept queue; sk_ack_backlog becomes 0
   → release accept node R and graft H to AS
   → copy peer 127.0.0.1:40000 to userspace
   → publish F8 with fd_install
   → accept4 returns 8
   → client write queues one ACK|PSH hello segment
   → IPv4 output and lo deliver five bytes to server child H
   → H receive queue gains hello and accepted fd 8 becomes readable
   → first-data quickack returns ACK C_ISN+6
   → release_sock(C) drains ACK and write returns 5
   → read(8,buf,5) consumes hello without sleeping
   → close(7) removes client fd and synchronously enters tcp_close
   → C sends FIN C_ISN+6..C_ISN+7 through IPv4 and lo
   → H queues the FIN marker and enters TCP_CLOSE_WAIT
   → RCV_SHUTDOWN and SOCK_DONE expose EOF on accepted fd 8
   → FIN ACK advances C into TCP_FIN_WAIT2
   → full C becomes a lightweight TW with FIN_WAIT2 substate
   → close(7) returns 0
   → read(8,buf,1) consumes the FIN marker and returns EOF
   → close(8) removes accepted fd and synchronously enters tcp_close
   → H enters TCP_LAST_ACK and sends FIN S_ISN+1..S_ISN+2
   → client lightweight TW validates the peer FIN
   → TW advances into true TCP_TIME_WAIT and rearms 60-second timer
   → per-CPU control socket sends final ACK S_ISN+2
   → H drains the ACK, clears its FIN and enters TCP_CLOSE
   → close(8) returns 0 and full H is destroyed
   → TIME_WAIT timer expires and inet_twsk_kill removes TW from ehash
   → bind/bind2 and timer references drop; TW is freed
   → close(6) removes listener fd and synchronously enters tcp_close
   → L leaves exact-address lhash2 and publishes TCP_CLOSE
   → empty listener queues stop without packets or scheduling
   → tcp_v4_destroy_sock releases explicit bind port 28080
   → close(6) returns 0 before the SOCK_RCU_FREE grace period
   → RCU callback reclaims L storage; TCP/IPv4 loopback mainline completes

历史正文范围（不等于已验证）
--------------------------

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
   LK-TCPACCEPT-179..LK-TCPACCEPT-181
   LK-TCPDATA-182..LK-TCPDATA-184
   LK-TCPCLOSE-185..LK-TCPCLOSE-187
   LK-TCPPEERCLOSE-188..LK-TCPPEERCLOSE-190
   LK-TCPCLEANUP-191..LK-TCPCLEANUP-193

固定commit的 ``Makefile`` 标识为Linux 7.2-rc1。旧章节中出现的 ``Linux 6.12.95`` 是
历史版本标签错误；尚未轮到的章节不能仅凭已有链接视为技术正确。

进度
----

当前正文存在193章；当前已验证游标见项目状态。历史19/43主线进度将在审查闭合后重新
计算；43不是固定章节总数。

最新三章
--------

#. `第一百九十一章：TIME_WAIT timer怎样撤销最后的四元组并释放TW？ <191-timewait-timer-kills-lightweight-socket.rst>`_
#. `第一百九十二章：close(6)怎样撤销listener fd并退出TCP_LISTEN？ <192-close-listener-removes-fd-and-listen-hash.rst>`_
#. `第一百九十三章：listener怎样释放bind端口与最后的sockfs对象？ <193-listener-final-teardown-completes-tcp-scenario.rst>`_

历史下一候选（生产已暂停）
------------------------

::

   mainline 20: UDP/IPv4
   → socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,IPPROTO_UDP)
   → reserve lowest available fd 6
   → allocate sockfs socket/inode and UDP inet_sock
   → select udp_prot without bind or UDP hash membership yet
   → build blocking close-on-exec socket file
   → fd_install publishes datagram fd 6
   → continue with loopback bind, route and datagram delivery

该UDP入口尚未在回溯审查后重新确认，当前不得据此生成新章。

章节组织
--------

正文沿时间线连续讲述。故事达到适合一次阅读的篇幅，并遇到执行者、CPU mode、运行环境或控制入口交接时换章。章节格式以第176—178章为准：章末依次使用条目式“本章结束状态”“关键边界”“下一入口”“资料”；不以大块状态表或单独“固定源码依据”代替连续正文。每章只记录自己的当前状态和下一入口；不要在一批的最后一章重复概括前两章。
