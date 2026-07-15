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
   LK-TCPCLEANUP-191..LK-TCPCLEANUP-193

最新三章：

#. ``LK-TCPCLEANUP-191``：TIME_WAIT timer怎样撤销最后的四元组并释放TW？
#. ``LK-TCPCLEANUP-192``：close(6)怎样撤销listener fd并退出TCP_LISTEN？
#. ``LK-TCPCLEANUP-193``：listener怎样释放bind端口与最后的sockfs对象？

进度
----

当前已经完成193章。Linux Kernel目标是完成当前盘点的全部43条源码主线，现已完成19条、剩余24条。主线目标与章节数分开：章节总数不预设，仍按源码控制流和自然叙事边界增长。

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

固定TCP最终清理调用
-------------------

.. code-block:: c

   /* after TCP_TIMEWAIT_LEN */
   int close_result = close(6);

固定条件：

::

   CPUs online               = CPU0 only
   network namespace         = N
   loopback device           = lo UP, MTU 65536
   listener fd               = 6, final unshared reference
   listener endpoint         = 127.0.0.1:28080
   listener state            = TCP_LISTEN
   listener queues           = empty, sk_ack_backlog 0
   listener hash/bind        = lhash2 active; bind/bind2 active
   explicit bind flag        = SOCK_BINDPORT_LOCK
   client/accepted fd        = 7/8 already closed
   client TIME_WAIT object   = true TIME_WAIT, 60-second timer armed
   TW references             = ehash + bind + timer = 3
   SO_LINGER                 = disabled
   failures/races            = none

完整控制流
----------

::

   TW timer expiration
   → CPU0 TIMER_SOFTIRQ invokes tw_timer_handler
   → inet_twsk_kill removes TW from established ehash
   → first __sock_put changes tw_refcnt 3→2
   → inet_twsk_bind_unhash removes bind and bind2 owners
   → second __sock_put changes tw_refcnt 2→1
   → final timer inet_twsk_put changes tw_refcnt 1→0
   → inet_twsk_free returns TW to twsk_slab
   → CPU0 returns to parent userspace

   close(6) listener identity teardown
   → file_close_fd clears fdtable.fd[6] and the open bit
   → fput_close_sync enters __fput synchronously
   → sock_close → __sock_release → inet_release → tcp_close(L,0)
   → set SHUTDOWN_MASK
   → TCP_LISTEN branch calls tcp_set_state(L,TCP_CLOSE)
   → inet_unhash sees old TCP_LISTEN and removes L from lhash2
   → explicit SOCK_BINDPORT_LOCK keeps bind/bind2 and inet_num 28080
   → TCP_CLOSE is published
   → inet_csk_listen_stop finishes empty request/accept/Fast Open queues

   listener protocol and file teardown
   → adjudge_to_death takes a temporary reference and orphans L
   → empty backlog is drained under BH socket lock
   → inet_csk_destroy_sock calls tcp_v4_destroy_sock
   → inet_put_port removes L from bind and bind2 owner chains
   → inet_num becomes 0; empty bind buckets are destroyed
   → final L reference schedules __sk_destruct through SOCK_RCU_FREE
   → socket release clears LS protocol associations
   → __fput releases F6 and sockfs path/inode relationships
   → close(6) returns 0 without waiting for an RCU grace period
   → later __sk_destruct/inet_sock_destruct/sk_prot_free reclaim L storage

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU/mode：CPU0，x86-64 CPL 3；
* last syscall/result：``close(6)=0``；
* parent：``TASK_RUNNING``；
* listener close scheduler count：0；
* fd 6/7/8：closed；
* F6/LS/I6：对parent和socket协议关系不可达；
* listener ``L``：``TCP_CLOSE``、orphan、unhashed；
* L ``lhash2``、bind与bind2身份：removed；
* ``L.inet_num``：0；
* L存储：由 ``SOCK_RCU_FREE`` grace period后的回调最终回收；
* full client ``C``、server child ``H``、request ``R``、TW：gone；
* client端口40000与listener端口28080：不再由旧场景占用；
* request、accept、write、retransmission、receive与backlog queue：empty/gone；
* TCP timer与场景skb：none；
* TCP/IPv4 loopback主线：complete；
* Linux Kernel主线：19/43完成，24条待完成；
* next runtime entry：UDP/IPv4 datagram socket创建。

关键边界
--------

#. TW的ehash、bind和timer引用按3→2→1→0释放。
#. ``inet_twsk_kill`` 在最后put前先让hash与端口检查不再看见TW。
#. close(6)先撤销fdtable身份，再同步进入F6最后一次 ``__fput``。
#. listener close不发送FIN/RST、不创建TIME_WAIT，也不等待网络确认。
#. ``tcp_set_state`` 在发布TCP_CLOSE前按旧TCP_LISTEN状态从lhash2删除L。
#. 显式bind的 ``SOCK_BINDPORT_LOCK`` 让28080保留到协议destroy阶段。
#. 空监听队列仍经过 ``inet_csk_listen_stop``，但没有child/request可处理。
#. ``tcp_v4_destroy_sock`` 中的 ``inet_put_port`` 最终撤销bind、bind2和inet_num。
#. lhash2撤销与bind端口撤销是两个顺序不同的可见性边界。
#. ``SOCK_RCU_FREE`` 只延后L存储回收，不延后listener身份与端口释放。
#. ``close(6)=0`` 不等待RCU grace period。
#. sockfs/VFS对象生命期与协议socket RCU生命期不能合并成一个同步free。
#. TCP主线结束后，全局sockfs、lo、网络命名空间和协议本身仍存在。
#. 43是需要全部完成的源码主线盘点，不是固定章节总数。
#. 章节格式固定跟随第176—178章，资料统一置于章末。

下一任务
--------

::

   mainline 20: UDP/IPv4
   → socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,IPPROTO_UDP)
   → reserve lowest available fd 6
   → allocate sockfs socket/inode and an AF_INET protocol socket
   → inet_create selects udp_prot
   → initialize an unbound, unhashed datagram endpoint
   → sock_alloc_file builds a blocking close-on-exec file
   → fd_install publishes fd 6

开始前必须固定UDP socket创建与fd发布的顺序、 ``inet_create`` 的protocol选择、初始未bind/未hash状态，以及分配失败时的逆序回滚边界。
