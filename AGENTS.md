# AGENTS.md

## 当前任务

`techBook` 当前只写 Linux Kernel。

```text
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
```

最新三章：

- `LK-TCPCLEANUP-191`：TIME_WAIT timer怎样撤销最后的四元组并释放TW？
- `LK-TCPCLEANUP-192`：close(6)怎样撤销listener fd并退出TCP_LISTEN？
- `LK-TCPCLEANUP-193`：listener怎样释放bind端口与最后的sockfs对象？

进度：当前完成193章。Linux Kernel目标是完成当前盘点的全部43条源码主线，现已完成19条、剩余24条；章节总数不预设，仍按源码边界自然分章。

## 固定实现

```text
SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
GNU GRUB release  = 2.14
GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
GRUB target       = i386-pc
Linux release     = 7.2-rc1
Linux repository  = gregkh/linux
Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d
partition table   = MBR
first partition   = LBA 2048, ext4
storage           = q35 ICH9 AHCI SATA port 0
```

## 已完成TCP/IPv4最终清理

```text
TW timer expiration on CPU0
→ TIMER_SOFTIRQ invokes tw_timer_handler
→ inet_twsk_kill removes TW from ehash
→ inet_twsk_bind_unhash removes bind and bind2 identities
→ tw_refcnt 3→2→1→0
→ inet_twsk_free returns lightweight TW to twsk_slab

close(6) listener identity teardown
→ file_close_fd clears fdtable.fd[6] and the open bit
→ fput_close_sync enters __fput synchronously
→ sock_close → inet_release → tcp_close(L,0)
→ tcp_set_state unhashes L while old state is TCP_LISTEN
→ L leaves exact-address lhash2 and publishes TCP_CLOSE
→ explicit SOCK_BINDPORT_LOCK keeps port 28080 bound until destroy
→ inet_csk_listen_stop finishes empty request/accept queues

listener protocol and object teardown
→ adjudge_to_death orphans L
→ inet_csk_destroy_sock enters tcp_v4_destroy_sock
→ inet_put_port removes bind, bind2 and inet_num 28080
→ final socket reference schedules __sk_destruct through SOCK_RCU_FREE
→ sockfs/VFS release makes F6, LS and I6 unreachable
→ close(6) returns 0 without waiting for the RCU grace period
→ later RCU callback reclaims L storage
```

## 当前精确状态

```text
system_state                 = SYSTEM_RUNNING
current executor             = parent
CPU/mode                     = CPU0, x86-64 CPL 3
last syscall                 = close(6)
last return                  = 0
listener close schedule count = 0

server/client/accepted fd    = 6/7/8 all closed
listener L                   = TCP_CLOSE / orphan / unhashed
L lhash2                     = removed
L bind/bind2                 = removed
L inet_num                   = 0
L storage                    = reclaimed after SOCK_RCU_FREE grace period

full client C/server H       = gone
request R/TIME_WAIT TW       = gone
client/server old ports      = 40000/28080 no longer owned
TCP queues/timers/skbs       = empty / none / none
packet/softirq backlog       = empty

completed mainlines          = 19 of 43
remaining mainlines          = 24
next mainline                = UDP/IPv4
next entry                   = socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,IPPROTO_UDP)
```

## 必须保持的技术边界

1. TW timer在TIMER_SOFTIRQ执行，ehash、bind、timer三份引用按3→2→1→0释放。
2. ``inet_twsk_kill`` 先撤销ehash，再撤销bind/bind2，最后放timer引用。
3. client端口40000不再被旧TW占用，不代表下一次分配必然选中40000。
4. close(6)先撤销fdtable slot和open位；旧close-on-exec位可留到fd重用时覆盖。
5. 最后F6引用通过 ``fput_close_sync`` 同步进入socket release。
6. listener close不发送FIN/RST，不创建TIME_WAIT，也不等待网络确认。
7. ``tcp_set_state`` 在发布TCP_CLOSE前按旧TCP_LISTEN状态从lhash2 unhash。
8. 显式bind设置 ``SOCK_BINDPORT_LOCK``，端口28080不会在tcp_set_state提前释放。
9. 空request/accept/Fast Open队列仍经过 ``inet_csk_listen_stop``。
10. ``tcp_v4_destroy_sock`` 通过 ``inet_put_port`` 最终撤销bind、bind2和inet_num。
11. lhash2身份撤销与bind端口撤销是前后两个不同边界。
12. listener的 ``SOCK_RCU_FREE`` 只延后存储回收，不延后端口释放或可达性终止。
13. ``close(6)=0`` 不等待RCU grace period。
14. sockfs inode内嵌LS；VFS对象生命期与L的协议RCU回收是两套机制。
15. TCP/IPv4主线完成后，fd 6/7/8、C/H/R/TW/L及旧端口身份均不可达。
16. 总目标固定为完成43条Linux Kernel源码主线；当前19条完成、剩余24条。
17. 43是主线盘点，不是章节总数；章节仍按源码边界自然增长。
18. 章节格式以第176—178章为准：连续正文，章末依次为本章结束状态、关键边界、下一入口、资料。

## 下一建议场景

```text
mainline 20: UDP/IPv4
→ socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,IPPROTO_UDP)
→ reserve lowest available fd 6
→ sock_alloc creates sockfs socket/inode
→ inet_create selects udp_prot and initializes inet_sock
→ sock_alloc_file builds blocking close-on-exec file
→ fd_install publishes datagram fd 6
→ continue with explicit loopback bind, route and UDP datagram delivery
```

开始前固定UDP socket创建时尚未bind、尚未进入UDP hash的状态，以及fd reservation、sockfs对象、协议socket和失败回滚的顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化与下一入口。章节格式以第176—178章为基准：正文沿时间线连续展开，章末使用条目式“本章结束状态”，再写“关键边界”“下一入口”，资料统一放在最后；不使用单独“固定源码依据”章节或大块状态表代替正文。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件，直接提交`main`。
