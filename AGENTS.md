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
```

最新三章：

- `LK-TCPCLOSE-185`：close(7)怎样撤销client fd并发送FIN？
- `LK-TCPCLOSE-186`：client FIN怎样让server H进入TCP_CLOSE_WAIT？
- `LK-TCPCLOSE-187`：FIN ACK怎样完成client关闭并让read返回EOF？

进度：当前完成187章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

## 已完成TCP/IPv4 client active close与server EOF

```text
close(7)
→ file_close_fd clears fdtable.fd[7] and the open bit
→ fput_close_sync enters __fput synchronously
→ sock_close → inet_release → tcp_close(C,0)
→ empty client receive queue selects normal FIN close
→ C enters TCP_FIN_WAIT1
→ FIN seq C_ISN+6..C_ISN+7 traverses IPv4 output and lo

server child H
→ in-order FIN enters H receive queue
→ H.rcv_nxt C_ISN+6→C_ISN+7
→ RCV_SHUTDOWN and SOCK_DONE become visible
→ H enters TCP_CLOSE_WAIT and fd8 becomes EOF-readable
→ remaining quickack sends ACK C_ISN+7

client FIN completion
→ parent still owns C, so FIN ACK enters C.sk_backlog
→ __tcp_close orphans C and __release_sock drains ACK
→ C.snd_una becomes C_ISN+7; original FIN leaves retransmission tree
→ C enters TCP_FIN_WAIT2
→ default 60-second boundary converts full C to TW
→ TW.tw_state=TCP_TIME_WAIT, TW.tw_substate=TCP_FIN_WAIT2
→ close(7) returns 0

accepted fd 8
→ read(8,buf,1) finds zero-payload FIN skb
→ H.copied_seq C_ISN+6→C_ISN+7
→ remove FIN skb without copying a user byte
→ read returns 0 EOF without scheduling
```

## 当前精确状态

```text
system_state              = SYSTEM_RUNNING
current executor          = parent
CPU/mode                  = CPU0, x86-64 CPL 3
last syscall              = read(8,buf,1)
last return               = 0 (EOF)
close/read schedule count = 0 / 0

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
TW state/substate         = TCP_TIME_WAIT / TCP_FIN_WAIT2
TW rcv_nxt/snd_nxt        = S_ISN+1 / C_ISN+7
TW timer                  = 60 seconds, waiting for peer FIN

accepted fd 8             = open, blocking, close-on-exec
accepted socket AS        = SS_CONNECTED
server child H            = TCP_CLOSE_WAIT
H tuple                   = 127.0.0.1:28080 ← 127.0.0.1:40000
H shutdown/SOCK_DONE      = RCV_SHUTDOWN / true
H rcv_nxt/copied_seq      = C_ISN+7 / C_ISN+7
H snd_una/snd_nxt         = S_ISN+1 / S_ISN+1
H receive queue           = empty
H readable bytes          = 0
H ehash/bind ownership    = active

packet/softirq backlog    = empty
next entry                = close(8)
```

## 必须保持的技术边界

1. fd 7先从fdtable撤销并清除open位；旧close-on-exec位允许保留到fd重用时覆盖。
2. 没有SO_LINGER，inet_release使用timeout=0；不linger等待不等于发送RST。
3. client receive queue为空，所以descriptor close不进入unread-data active reset。
4. TCP_ESTABLISHED通过tcp_close_state进入TCP_FIN_WAIT1并发送FIN。
5. FIN是零payload，仍占用 ``[C_ISN+6,C_ISN+7)`` 一个sequence number。
6. CFIN original留在retransmission tree，发送clone通过IPv4 output与lo。
7. H按反向四元组由established ehash命中，不经过listener。
8. H收到FIN时rcv_nxt推进，copied_seq在read消费FIN前保持C_ISN+6。
9. tcp_fin设置RCV_SHUTDOWN、SOCK_DONE并把H推进到TCP_CLOSE_WAIT。
10. EOF readiness不要求存在用户payload；FIN标记已经让blocking read可立即返回。
11. H的quickack计数仍为正，所以FIN ACK在本场景立即发送。
12. parent持有C时，反向ACK先进入C.sk_backlog。
13. sock_orphan切断C与CS；__release_sock仍能在process context消费已有ACK。
14. ACK把snd_una推进到C_ISN+7并清除original FIN，C进入TCP_FIN_WAIT2。
15. 默认tcp_fin_timeout与TCP_TIMEWAIT_LEN均为60秒，严格大于比较为false。
16. tcp_time_wait建立tw_state=TCP_TIME_WAIT、tw_substate=TCP_FIN_WAIT2的轻量TW。
17. TW接管client四元组，完整C进入TCP_CLOSE并结束生命周期。
18. close(7)=0不表示peer已经close，也不表示TW已经消失。
19. read(8)消费FIN时只推进copied_seq，不复制用户字节，返回0 EOF。
20. H保持TCP_CLOSE_WAIT；只有后续close(8)才发送server FIN。
21. 章节格式以第176—178章为准：连续正文，章末依次为本章结束状态、关键边界、下一入口、资料。

## 下一建议场景

```text
close(8)
→ fdtable撤销accepted fd 8
→ final __fput enters tcp_close(H,0)
→ H changes TCP_CLOSE_WAIT → TCP_LAST_ACK
→ server FIN seq S_ISN+1..S_ISN+2 traverses lo
→ client lookup finds TW with tw_substate TCP_FIN_WAIT2
→ TW validates FIN, sends final ACK and enters true TCP_TIME_WAIT
→ H receives ACK and completes TCP_LAST_ACK → TCP_CLOSE
→ later TW timer releases the client tuple
```

开始前固定close(8)到同步__fput、H FIN sequence、TW FIN_WAIT2处理、最终ACK、H LAST_ACK销毁以及TW timer边界。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化与下一入口。章节格式以第176—178章为基准：正文沿时间线连续展开，章末使用条目式“本章结束状态”，再写“关键边界”“下一入口”，资料统一放在最后；不使用单独“固定源码依据”章节或大块状态表代替正文。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件，直接提交`main`。
