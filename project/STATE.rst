项目状态
========

最后更新
--------

2026-07-15

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

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

最新三章：

#. ``LK-TCPCLOSE-185``：close(7)怎样撤销client fd并发送FIN？
#. ``LK-TCPCLOSE-186``：client FIN怎样让server H进入TCP_CLOSE_WAIT？
#. ``LK-TCPCLOSE-187``：FIN ACK怎样完成client关闭并让read返回EOF？

进度
----

当前已经完成187章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

固定关闭调用
------------

.. code-block:: c

   int close_result = close(7);

   char byte;
   ssize_t eof_result = read(8, &byte, 1);

固定条件：

::

   CPUs online            = CPU0 only
   network namespace      = N
   loopback device        = lo UP, MTU 65536
   listener fd            = 6
   listener endpoint      = 127.0.0.1:28080
   client fd              = 7, final unshared reference before close
   client endpoint        = 127.0.0.1:40000
   accepted fd            = 8, blocking, close-on-exec
   initial TCP states     = TCP_ESTABLISHED/TCP_ESTABLISHED
   client/server ISN      = C_ISN 0x13572468 / S_ISN 0x24681357
   initial C sequence     = snd_una=snd_nxt=write_seq=C_ISN+6
   initial H sequence     = rcv_nxt=copied_seq=C_ISN+6
   C/H queues             = empty
   SO_LINGER              = disabled
   tcp_fin_timeout        = TCP_FIN_TIMEOUT = 60*HZ
   TCP_TIMEWAIT_LEN       = 60*HZ
   H quickack             = still active after hello ACK
   failures/races         = none

完整控制流
----------

::

   close(7)
   → file_close_fd clears fdtable.fd[7] and the open bit
   → filp_flush returns 0
   → fput_close_sync enters __fput synchronously
   → sock_close → __sock_release → inet_release
   → no SO_LINGER, so tcp_close(C,0)
   → lock_sock(C); set SHUTDOWN_MASK
   → C receive queue is empty, so no unread-data RST
   → tcp_close_state changes TCP_ESTABLISHED to TCP_FIN_WAIT1
   → tcp_send_fin builds ACK|FIN seq=C_ISN+6 end_seq=C_ISN+7
   → C.write_seq and snd_nxt become C_ISN+7
   → original FIN enters C retransmission tree

   FIN clone
   → IPv4 output uses cached local route
   → dev_queue_xmit selects noqueue lo
   → loopback_xmit queues FIN to CPU0 input backlog
   → NET_RX tcp_v4_rcv ehash lookup finds H
   → H is not user-owned, so tcp_rcv_established runs directly
   → queue zero-payload FIN skb on H.sk_receive_queue
   → H.rcv_nxt becomes C_ISN+7; copied_seq remains C_ISN+6
   → tcp_fin sets RCV_SHUTDOWN and SOCK_DONE
   → H enters TCP_CLOSE_WAIT; fd8 becomes EOF-readable
   → active quickack sends pure ACK seq=S_ISN+1 ack=C_ISN+7

   FIN ACK and client close completion
   → reverse ehash lookup finds user-owned C
   → tcp_add_backlog queues HACK on C.sk_backlog
   → tcp_send_fin returns; zero-timeout wait does not schedule
   → sock_orphan(C) cuts the userspace socket association
   → __release_sock(C) drains HACK in process context
   → C.snd_una becomes C_ISN+7
   → original FIN leaves retransmission tree
   → C enters TCP_FIN_WAIT2
   → tcp_fin_time equals TCP_TIMEWAIT_LEN at 60*HZ
   → tcp_time_wait allocates TW with tw_state TCP_TIME_WAIT
   → TW.tw_substate remains TCP_FIN_WAIT2 and timer is armed
   → TW replaces full C in ehash; full C enters TCP_CLOSE
   → close(7) returns 0

   read(8,buf,1)
   → fd8 resolves F8/AS/H
   → tcp_recvmsg_locked finds queued FIN skb
   → no sk_wait_data and no schedule
   → no payload byte is copied
   → H.copied_seq becomes C_ISN+7
   → remove and free FIN skb
   → read returns 0 EOF

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* last syscall/result：``read(8,buf,1)=0`` EOF；
* preceding syscall/result：``close(7)=0``；
* parent：``TASK_RUNNING``；
* close/read scheduler count：0/0；
* server fd 6：open、blocking、close-on-exec；
* listener ``L``：``TCP_LISTEN``，endpoint ``127.0.0.1:28080``；
* listener accept queue：empty，``sk_ack_backlog=0``；
* client fd 7：closed；
* full client ``C``：``TCP_CLOSE``，用户可见生命周期结束；
* client tuple identity：轻量 ``inet_timewait_sock TW``；
* TW tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* ``TW.tw_state=TCP_TIME_WAIT``；
* ``TW.tw_substate=TCP_FIN_WAIT2``；
* ``TW.tw_rcv_nxt=S_ISN+1``；
* ``TW.tw_snd_nxt=C_ISN+7``；
* TW timer：默认60秒，等待server FIN；
* accepted fd 8：open、blocking、close-on-exec；
* accepted socket ``AS``：``SS_CONNECTED``；
* server child ``H``：``TCP_CLOSE_WAIT``；
* H tuple：``127.0.0.1:28080 ← 127.0.0.1:40000``；
* H ``sk_shutdown``：包含 ``RCV_SHUTDOWN``；
* H ``SOCK_DONE``：true；
* H ``rcv_nxt=copied_seq=C_ISN+7``；
* H ``snd_una=snd_nxt=S_ISN+1``；
* H receive queue：empty，readable bytes 0；
* TW/H route、ehash与bind ownership：active；
* packet与CPU0 NET_RX backlog：empty；
* next runtime entry：``close(8)``。

关键边界
--------

#. file_close_fd先撤销fd 7并清除open位；旧close-on-exec位允许保留到fd重用时覆盖。
#. timeout=0只取消linger等待；正常FIN仍由tcp_close_state发送。
#. client receive queue为空，因此descriptor close不会因未读数据发送RST。
#. FIN没有payload，仍占用 ``[C_ISN+6,C_ISN+7)`` sequence区间。
#. original FIN留在client retransmission tree，发送clone经IPv4与lo到达H。
#. established lookup命中H；listener与request路径不参与关闭阶段。
#. FIN入队时H.rcv_nxt推进；应用消费FIN前copied_seq保持旧值。
#. tcp_fin发布RCV_SHUTDOWN、SOCK_DONE和TCP_CLOSE_WAIT。
#. fd 8的EOF readiness不要求receive queue中存在用户payload。
#. H的quickack仍active，所以立即确认 ``C_ISN+7``。
#. parent持有C时FIN ACK进入C.sk_backlog，不在softirq中直接改状态。
#. sock_orphan先切断用户socket，__release_sock仍可消费已有ACK。
#. ACK确认FIN后snd_una等于write_seq，C进入TCP_FIN_WAIT2。
#. tcp_fin_timeout与TCP_TIMEWAIT_LEN均为60秒，严格大于比较为false。
#. 轻量TW使用tw_state TCP_TIME_WAIT和tw_substate TCP_FIN_WAIT2。
#. TW接管四元组；完整C进入TCP_CLOSE并结束用户可见生命周期。
#. close(7)=0不表示peer H已经close，也不表示TW已经释放。
#. read消费FIN只推进copied_seq，不向userspace复制字节，返回0 EOF。
#. H保持TCP_CLOSE_WAIT，后续close(8)才发送server FIN。
#. 章节格式固定跟随第176—178章，资料统一置于章末。

下一任务
--------

::

   close(8)
   → fdtable removes F8 publication
   → fput_close_sync enters tcp_close(H,0)
   → H changes TCP_CLOSE_WAIT to TCP_LAST_ACK
   → H sends FIN seq S_ISN+1 end_seq S_ISN+2 through lo
   → client lookup finds TW with tw_substate TCP_FIN_WAIT2
   → TW validates FIN and changes substate to TCP_TIME_WAIT
   → TW sends final ACK and rearms TCP_TIMEWAIT_LEN
   → H receives ACK, clears original FIN and enters TCP_CLOSE
   → accepted file/socket/full H finish teardown
   → later TW timer releases tuple and bind ownership

开始前必须固定close(8)到__fput的同步边界、server FIN与final ACK sequence、TW FIN_WAIT2 receive分支、H LAST_ACK销毁、listener保留状态与TW timer释放边界。
