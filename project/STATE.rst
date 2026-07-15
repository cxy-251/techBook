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
   LK-TCPPEERCLOSE-188..LK-TCPPEERCLOSE-190

最新三章：

#. ``LK-TCPPEERCLOSE-188``：close(8)怎样撤销accepted fd并发送server FIN？
#. ``LK-TCPPEERCLOSE-189``：FIN_WAIT2 TW怎样接收server FIN并发送最终ACK？
#. ``LK-TCPPEERCLOSE-190``：最终ACK怎样结束H的LAST_ACK并让close(8)返回0？

进度
----

当前已经完成190章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

固定peer关闭调用
----------------

.. code-block:: c

   int close_result = close(8);

固定条件：

::

   CPUs online            = CPU0 only
   network namespace      = N
   loopback device        = lo UP, MTU 65536
   listener fd            = 6
   listener endpoint      = 127.0.0.1:28080
   client fd              = 7, already closed
   client endpoint        = 127.0.0.1:40000
   accepted fd            = 8, final unshared reference before close
   initial client object  = TW state TIME_WAIT, substate FIN_WAIT2
   initial server state   = TCP_CLOSE_WAIT
   client/server ISN      = C_ISN 0x13572468 / S_ISN 0x24681357
   initial TW sequence    = rcv_nxt S_ISN+1, snd_nxt C_ISN+7
   initial H sequence     = snd_una=snd_nxt=write_seq=S_ISN+1
   H queues               = empty
   SO_LINGER              = disabled
   TCP_TIMEWAIT_LEN       = 60*HZ
   failures/races         = none

完整控制流
----------

::

   close(8)
   → file_close_fd clears fdtable.fd[8] and the open bit
   → filp_flush returns 0
   → fput_close_sync enters __fput synchronously
   → sock_close → __sock_release → inet_release
   → no SO_LINGER, so tcp_close(H,0)
   → lock_sock(H); set SHUTDOWN_MASK
   → H receive queue is empty, so no unread-data RST
   → tcp_close_state changes TCP_CLOSE_WAIT to TCP_LAST_ACK
   → tcp_send_fin builds ACK|FIN seq=S_ISN+1 end_seq=S_ISN+2
   → H.write_seq and snd_nxt become S_ISN+2
   → original HFIN enters H retransmission tree

   HFIN clone
   → IPv4 output uses cached local route
   → dev_queue_xmit selects noqueue lo
   → loopback_xmit queues HFIN to CPU0 input backlog
   → NET_RX tcp_v4_rcv ehash lookup finds lightweight TW
   → do_time_wait enters FIN_WAIT2 substate processing
   → exact FIN passes PAWS, window and end_seq=rcv_nxt+1 checks
   → TW.tw_rcv_nxt becomes S_ISN+2
   → TW.tw_substate becomes TCP_TIME_WAIT
   → time-wait timer is rearmed for 60 seconds
   → per-CPU control socket sends TACK seq=C_ISN+7 ack=S_ISN+2

   TACK and server close completion
   → reverse ehash lookup finds user-owned H
   → tcp_add_backlog queues TACK on H.sk_backlog
   → tcp_send_fin returns; zero-timeout wait does not schedule
   → sock_orphan(H) cuts the userspace socket association
   → __release_sock(H) drains TACK in process context
   → H.snd_una becomes S_ISN+2
   → original HFIN leaves retransmission tree
   → TCP_LAST_ACK sees snd_una==write_seq
   → tcp_done changes H to TCP_CLOSE and clears timers/hash identity
   → full H, AS, F8 and I8 finish teardown
   → close(8) returns 0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* last syscall/result：``close(8)=0``；
* parent：``TASK_RUNNING``；
* close scheduler count：0；
* server fd 6：open、blocking、close-on-exec；
* listener ``L``：``TCP_LISTEN``，endpoint ``127.0.0.1:28080``；
* listener accept queue：empty，``sk_ack_backlog=0``；
* client fd 7：closed；
* full client ``C``：``TCP_CLOSE``，用户可见生命周期结束；
* client tuple identity：轻量 ``inet_timewait_sock TW``；
* TW tuple：``127.0.0.1:40000 → 127.0.0.1:28080``；
* ``TW.tw_state=TCP_TIME_WAIT``；
* ``TW.tw_substate=TCP_TIME_WAIT``；
* ``TW.tw_rcv_nxt=S_ISN+2``；
* ``TW.tw_snd_nxt=C_ISN+7``；
* TW timer：从server FIN到达时重新计60秒；
* accepted fd 8：closed；
* F8/AS/I8：最后生命周期完成；
* server child ``H``：``TCP_CLOSE``，完整socket已销毁；
* H established ehash identity：removed；
* H retransmission tree、backlog与timer：empty、empty、cleared；
* TW ehash与bind ownership：active；
* packet与CPU0 NET_RX backlog：empty；
* next runtime entry：TW在 ``TCP_TIMEWAIT_LEN`` 后timer到期。

关键边界
--------

#. file_close_fd先撤销fd 8并清除open位，fput_close_sync再同步释放F8。
#. H receive queue为空，timeout=0仍选择正常server FIN而不是RST。
#. TCP_CLOSE_WAIT在应用close时进入TCP_LAST_ACK。
#. HFIN没有payload，仍占用 ``[S_ISN+1,S_ISN+2)`` sequence区间。
#. original HFIN留在H retransmission tree，发送clone经IPv4与lo到达TW。
#. client完整C已经销毁，lookup只命中轻量TW。
#. tw_state标识对象类型，tw_substate在收到peer FIN前标识TCP_FIN_WAIT2。
#. 合法HFIN必须精确满足end_seq=tw_rcv_nxt+1，FIN_WAIT2 TW不接收新payload。
#. peer FIN把tw_rcv_nxt推进到S_ISN+2并进入真正TIME_WAIT。
#. TIME_WAIT timer从peer FIN到达时重新计60秒。
#. TACK由per-CPU control socket发送，seq C_ISN+7、ack S_ISN+2。
#. parent持有H时TACK进入H.sk_backlog，不在softirq中直接结束LAST_ACK。
#. sock_orphan切断H与AS，__release_sock仍可消费TACK。
#. TACK确认HFIN并使snd_una等于write_seq。
#. TCP_LAST_ACK满足确认条件后调用tcp_done进入TCP_CLOSE。
#. passive closer H不创建server TW，client TW承担TIME_WAIT。
#. close(8)=0不等待TW timer，完整H与F8/AS/I8已结束生命周期。
#. listener L与H独立，仍可通过fd 6接受连接。
#. 下一批不得重复四次挥手，应从TW timer到期开始。
#. 章节格式固定跟随第176—178章，资料统一置于章末。

下一任务
--------

::

   TW timer expires after TCP_TIMEWAIT_LEN
   → tw_timer_handler removes TW from timer schedule
   → inet_twsk_kill removes ehash and bind identities
   → final timer/hash references drop
   → inet_twsk_free releases lightweight TW
   → close(6) removes listener fd
   → tcp_close(L,0) stops TCP_LISTEN
   → lhash2, bind ownership and empty request/accept queues are dismantled
   → listener file/socket/sockfs objects finish teardown

开始前必须固定TW timer callback的引用与hash/bind删除顺序，以及listener close对lhash2、bind bucket、空request queue和sockfs对象的销毁边界。
