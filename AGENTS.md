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
```

最新三章：

- `LK-TCPLISTEN-170`：socket(AF_INET,SOCK_STREAM)怎样创建TCP endpoint并发布fd 6？
- `LK-TCPLISTEN-171`：bind(127.0.0.1:28080)怎样验证本地地址并占用TCP端口？
- `LK-TCPLISTEN-172`：listen(8)怎样建立空请求队列并把socket加入TCP监听哈希？

进度：当前完成172章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

## 已完成TCP/IPv4 listener建立

```text
fd 0..5 occupied; fd 6 lowest free
→ socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
→ allocate sockfs inode IS and struct socket S
→ select inet_stream_ops and tcp_prot
→ allocate and initialize tcp_sock LTP
→ S.state=SS_UNCONNECTED; L.sk_state=TCP_CLOSE
→ create blocking close-on-exec file F6
→ fd_install(6,F6)
→ bind(6,127.0.0.1:28080)
→ confirm address is RTN_LOCAL in network namespace N
→ create/find inet_bind_bucket TB for port 28080
→ create/find inet_bind2_bucket TB2 for 127.0.0.1:28080
→ attach L to TB2 owners
→ set inet_num/inet_sport and address/port userlocks
→ remain TCP_CLOSE; no listener lookup visibility
→ listen(6,8)
→ effective backlog remains 8
→ initialize empty request/accept queue
→ sk_max_ack_backlog=8; sk_ack_backlog=0
→ TCP_CLOSE→TCP_LISTEN
→ revalidate bound port without duplicate owner insertion
→ insert L into exact-address listener lhash2
→ return 0 without route lookup, skb or packet I/O
```

## 当前精确状态

```text
system_state          = SYSTEM_RUNNING
current executor      = parent
CPU/mode              = CPU0, x86-64 CPL 3
parent state          = TASK_RUNNING, on_rq=1, on_cpu=1
helper                = blocked outside listener objects
last syscall          = listen(6,8)
last return           = 0
fd 6                  = open, blocking, close-on-exec
file F6               = active sockfs socket file
socket S              = SS_UNCONNECTED, SOCK_STREAM
tcp socket L/LTP      = TCP_LISTEN
network namespace     = N
loopback device       = lo UP
local endpoint        = 127.0.0.1:28080
remote endpoint       = unset
bind bucket TB        = active
bind2 bucket TB2      = active; owners contains L
listener bucket ILB2  = active; contains L
sk_max_ack_backlog    = 8
sk_ack_backlog        = 0
request queue         = empty
accept queue          = empty
Fast Open queue       = empty
request socket        = none
accepted child        = none
route/dst cache       = empty
skb/packet            = none
next entry            = client socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
```

## 必须保持的技术边界

1. protocol 0在AF_INET/`SOCK_STREAM`下选择TCP。
2. `struct socket`嵌在sockfs pseudo inode中；`struct tcp_sock`是独立协议对象。
3. `SS_UNCONNECTED`属于socket API状态；`TCP_CLOSE`/`TCP_LISTEN`属于TCP协议状态。
4. 单个`socket()`在协议对象成功建立后才reserve和发布fd。
5. `SOCK_CLOEXEC`设置fdtable bit，不等于file的`O_CLOEXEC` status flag。
6. `bind()`先验证local address，再由`inet_csk_get_port()`建立端口所有权。
7. `inet_bind_bucket`表示namespace/port/L3 domain；`inet_bind2_bucket`增加local address维度。
8. bind hash不是listener hash；bind成功后socket仍不可被入站SYN lookup。
9. `inet_num`使用host byte order；`inet_sport`使用network byte order。
10. `listen()`先按`somaxconn`限制backlog，再进入协议回调。
11. 第一次listen初始化空request/accept queue；backlog不代表预分配request或child。
12. state先写`TCP_LISTEN`，外部可查找性仍以listener hash发布为准。
13. listen重新调用`get_port()`复核listener冲突，不会重复加入已有bind owner链。
14. listener进入按具体local address和port计算的lhash2，并设置`SOCK_RCU_FREE`。
15. socket、bind与listen均不产生route output、skb、SYN或loopback packet。

## 下一建议场景

```text
client socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
→ publish fd 7
→ connect(fd 7,127.0.0.1:28080)
→ choose loopback route and ephemeral source port
→ client enters TCP_SYN_SENT
→ build and transmit SYN through loopback
→ listener lookup finds L
→ allocate and hash request_sock
→ send SYN-ACK
```

开始前固定client ephemeral port、route result、ISN、TCP options、softirq/NAPI边界、request socket引用、CPU0执行顺序与parent阻塞/唤醒位置。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件。
