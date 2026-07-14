techBook
========

``techBook`` 当前只写 Linux Kernel。

当前正文
--------

* `Linux Kernel 完整章节目录 <docs/tracks/linux-kernel/index.rst>`_
* `第一百七十六章：release_sock怎样处理SYN-ACK并让client发送最终ACK？ <docs/tracks/linux-kernel/176-release-sock-processes-synack-and-sends-final-ack.rst>`_
* `第一百七十七章：最终ACK怎样把request_sock替换成ESTABLISHED server child？ <docs/tracks/linux-kernel/177-final-ack-replaces-request-with-established-server-child.rst>`_
* `第一百七十八章：blocking connect为什么无需真正睡眠就返回0？ <docs/tracks/linux-kernel/178-blocking-connect-skips-schedule-and-returns-zero.rst>`_

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

最新场景
--------

::

   server fd 6: 127.0.0.1:28080 TCP_LISTEN
   → client fd 7 processes SYN-ACK from C.sk_backlog
   → client enters TCP_ESTABLISHED and wakes connect wait entry
   → final ACK traverses IPv4 output and lo
   → server ehash finds TCP_NEW_SYN_RECV request R
   → create full server child H and inherit port 28080
   → replace R's ehash identity with H
   → request qlen/young become 0/0
   → reuse R as accept FIFO node with R.sk=H
   → H enters TCP_ESTABLISHED
   → listener sk_ack_backlog becomes 1
   → wait_woken observes WQ_FLAG_WOKEN without scheduling
   → CS becomes SS_CONNECTED
   → connect(7,127.0.0.1:28080) returns 0

最终fd 6/7保持open。client fd 7已经连接；server child ``H`` 已在accept queue中，却尚无 ``struct socket``、file或fd。下一章从 ``accept4(6,...,SOCK_CLOEXEC)`` 取出R/H并发布fd 8开始。

开始工作
--------

新的对话或助手先阅读 ``AGENTS.md``、 ``project/STATE.rst``、章节目录和manifest。
