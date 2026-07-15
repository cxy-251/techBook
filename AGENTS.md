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
```

最新三章：

- `LK-TCPPEERCLOSE-188`：close(8)怎样撤销accepted fd并发送server FIN？
- `LK-TCPPEERCLOSE-189`：FIN_WAIT2 TW怎样接收server FIN并发送最终ACK？
- `LK-TCPPEERCLOSE-190`：最终ACK怎样结束H的LAST_ACK并让close(8)返回0？

进度：当前完成190章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

## 已完成TCP/IPv4 peer close与四次挥手

```text
close(8)
→ file_close_fd clears fdtable.fd[8] and the open bit
→ fput_close_sync enters __fput synchronously
→ sock_close → inet_release → tcp_close(H,0)
→ empty receive queue selects normal FIN close
→ H changes TCP_CLOSE_WAIT → TCP_LAST_ACK
→ HFIN seq S_ISN+1..S_ISN+2 traverses IPv4 output and lo

client lightweight TW
→ client-direction lookup finds TW, not full C
→ tw_substate TCP_FIN_WAIT2 validates the exact peer FIN
→ tw_rcv_nxt advances S_ISN+1→S_ISN+2
→ tw_substate becomes true TCP_TIME_WAIT
→ TW timer is rearmed for 60 seconds
→ per-CPU control socket sends TACK ack S_ISN+2

server final ACK completion
→ parent still owns H, so TACK enters H.sk_backlog
→ __tcp_close orphans H and __release_sock drains TACK
→ H.snd_una becomes S_ISN+2; original HFIN leaves retransmission tree
→ TCP_LAST_ACK sees snd_una==write_seq and calls tcp_done
→ H enters TCP_CLOSE and full server child is destroyed
→ F8/AS/I8 finish their final lifecycle
→ close(8) returns 0 without scheduling
```

## 当前精确状态

```text
system_state              = SYSTEM_RUNNING
current executor          = parent
CPU/mode                  = CPU0, x86-64 CPL 3
last syscall              = close(8)
last return               = 0
close schedule count      = 0

server fd 6               = open, blocking, close-on-exec
listener L                = TCP_LISTEN
L local endpoint          = 127.0.0.1:28080
L bind/lhash2             = active
L accept queue            = empty
L sk_ack_backlog          = 0

client fd 7               = closed
full client C             = TCP_CLOSE / teardown complete
client tuple identity     = lightweight TW
TW tuple                  = 127.0.0.1:40000 → 127.0.0.1:28080
TW state/substate         = TCP_TIME_WAIT / TCP_TIME_WAIT
TW rcv_nxt/snd_nxt        = S_ISN+2 / C_ISN+7
TW timer                  = rearmed 60 seconds after peer FIN

accepted fd 8             = closed
accepted F8/AS/I8         = final lifecycle complete
server child H            = TCP_CLOSE / destroyed
H established ehash      = removed
H retrans/backlog/timers  = empty / empty / cleared

packet/softirq backlog    = empty
next entry                = TW timer expiration after TCP_TIMEWAIT_LEN
```

## 必须保持的技术边界

1. fd 8先从fdtable撤销并清除open位；最后一个F8引用再同步进入__fput。
2. H receive queue为空，timeout=0仍选择正常FIN而不是RST。
3. TCP_CLOSE_WAIT在应用close时进入TCP_LAST_ACK。
4. HFIN是零payload，仍占用 ``[S_ISN+1,S_ISN+2)`` 一个sequence number。
5. HFIN original留在H retransmission tree，发送clone经IPv4与lo。
6. client方向lookup命中轻量TW，不恢复完整C。
7. tw_state标识轻量对象类型；tw_substate在收到HFIN前仍是TCP_FIN_WAIT2。
8. 合法HFIN必须在window内并精确覆盖tw_rcv_nxt到tw_rcv_nxt+1。
9. FIN_WAIT2轻量对象不接受新的应用payload。
10. HFIN把tw_rcv_nxt推进到S_ISN+2并把substate改为真正TCP_TIME_WAIT。
11. 真正TIME_WAIT timer从peer FIN到达时重新计60秒。
12. TACK由per-CPU control socket发送，seq C_ISN+7、ack S_ISN+2。
13. parent持有H时，TACK先进入H.sk_backlog。
14. sock_orphan切断H与AS；__release_sock仍能在process context消费TACK。
15. TACK把H.snd_una推进到S_ISN+2并清除original HFIN。
16. TCP_LAST_ACK以snd_una==write_seq确认本地FIN完成。
17. tcp_done把H推进到TCP_CLOSE并清除ehash身份与传输timer。
18. passive closer H不创建server TW；client TW承担TIME_WAIT。
19. close(8)=0不等待TW timer，F8/AS/I8与完整H已经结束生命周期。
20. listener L与H独立；H销毁不影响fd 6继续listen。
21. 章节格式以第176—178章为准：连续正文，章末依次为本章结束状态、关键边界、下一入口、资料。

## 下一建议场景

```text
TW timer expires after TCP_TIMEWAIT_LEN
→ tw_timer_handler removes TW from death-row schedule
→ inet_twsk_kill removes ehash and bind identities
→ timer/hash references drop and TW is freed
→ client tuple becomes fully reusable
→ close(6) removes listener fd
→ TCP_LISTEN and lhash2/bind identities are dismantled
→ listener file/socket/sockfs objects finish teardown
```

开始前固定TW timer callback、ehash/bind拆除引用顺序，以及close(6)的listener queue、lhash2、bind与sockfs销毁边界。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化与下一入口。章节格式以第176—178章为基准：正文沿时间线连续展开，章末使用条目式“本章结束状态”，再写“关键边界”“下一入口”，资料统一放在最后；不使用单独“固定源码依据”章节或大块状态表代替正文。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件，直接提交`main`。
