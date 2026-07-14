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
```

最新三章：

- `LK-TCPCONNECT-173`：client connect怎样选择loopback路由、自动端口并进入TCP_SYN_SENT？
- `LK-TCPCONNECT-174`：tcp_connect怎样构造SYN并通过lo命中server listener？
- `LK-TCPCONNECT-175`：listener怎样创建request_sock并把SYN-ACK排入client backlog？

进度：当前完成175章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

## 已完成TCP/IPv4 listener与主动连接前半段

```text
server fd 6
→ socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
→ bind(127.0.0.1:28080)
→ listen(6,8)
→ listener L enters TCP_LISTEN and exact-address lhash2

client fd 7
→ socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
→ connect(7,127.0.0.1:28080)
→ ip_route_connect selects 127.0.0.1 and lo
→ inet_hash_connect selects source port 40000
→ client tuple 127.0.0.1:40000 → 127.0.0.1:28080
→ C enters TCP_SYN_SENT, bind/bind2 and ehash
→ C_ISN=0x13572468
→ tcp_connect builds original CSYN and sends clone XSYN
→ IPv4 output → dev_queue_xmit → loopback_xmit
→ __netif_rx queues XSYN to CPU0 backlog
→ NET_RX softirq finds L through exact lhash2
→ L allocates request_sock R in TCP_NEW_SYN_RECV
→ R records client options and C_ISN+1
→ S_ISN=0x24681357
→ R enters ehash, arms request timer, qlen/young become 1/1
→ server sends SYN-ACK through lo
→ reverse ehash lookup finds client C
→ parent still owns C, so softirq queues SYN-ACK in C.sk_backlog
→ protocol connect returns 0 and CS becomes SS_CONNECTING
→ inet_wait_for_connect installs wait entry CW
→ stop immediately before release_sock(C)
```

## 当前精确状态

```text
system_state             = SYSTEM_RUNNING
current executor         = parent
CPU/mode                 = CPU0, x86-64 kernel process context
current syscall          = connect(7,127.0.0.1:28080)
parent state             = TASK_RUNNING; not scheduled yet
client wait entry CW     = installed on sk_sleep(C)
client socket user lock  = held by parent

server fd 6              = open, blocking, close-on-exec
server L                 = TCP_LISTEN
server local endpoint    = 127.0.0.1:28080
server bind/lhash2       = active
server request qlen      = 1
server request young     = 1
server accept queue      = empty
server child             = none

client fd 7              = open, blocking, close-on-exec
client CS                = SS_CONNECTING
client C                 = TCP_SYN_SENT
client local endpoint    = 127.0.0.1:40000
client remote endpoint   = 127.0.0.1:28080
client bind/bind2        = active; SOCK_CONNECT_BIND
client ehash             = active
client dst               = local route through lo
client C_ISN             = 0x13572468
client snd_una/snd_nxt   = C_ISN / C_ISN+1
client retrans tree      = contains original CSYN
client retrans timer     = armed
client socket backlog    = contains one SYN-ACK

request R                = TCP_NEW_SYN_RECV
request tuple            = 127.0.0.1:28080 ← 127.0.0.1:40000
request S_ISN            = 0x24681357
request rcv_nxt          = C_ISN+1
request ehash            = active
request timer            = armed
request rsk_refcnt       = 2
next entry               = release_sock(C)
```

## 必须保持的技术边界

1. `struct socket`属于socket API层；`struct tcp_sock`、`request_sock`和未来server child是不同对象与生命周期。
2. client `socket()`复用服务器创建主链，fd 7来自最低空闲描述符。
3. `ip_route_connect()`在local port仍为0时选择local route、source address和`lo`。
4. connect自动选择的source address/port不等同于用户显式bind；端口带`SOCK_CONNECT_BIND`。
5. ephemeral port由带secret与perturbation的扫描算法选择；40000只是固定场景结果。
6. `tcp_v4_connect()`先写`TCP_SYN_SENT`，再自动选端口、插入bind hash与ehash。
7. client在SYN发出前已进入ehash，使反向SYN-ACK能够查到它。
8. TCP保留original CSYN用于重传，IP/device层发送可消费的clone XSYN。
9. local destination仍走IPv4 output、`dev_queue_xmit()`、`loopback_xmit()`与`__netif_rx()`。
10. loopback没有硬件IRQ或DMA；CPU0 NET_RX softirq可嵌套运行在`connect()`发送路径中。
11. SYN方向不匹配client四元组，随后通过具体地址lhash2命中server listener。
12. 普通非cookie SYN分配真实request R；R状态为`TCP_NEW_SYN_RECV`，不是完整child的`TCP_SYN_RECV`。
13. request必须先进入ehash并启动timer，再发送SYN-ACK，避免最终ACK到达时无对象可查。
14. request qlen=1不等于accept queue已有连接；accept queue仍为空。
15. parent持有client socket用户锁时，softirq只能把SYN-ACK放入`C.sk_backlog`。
16. blocking connect先安装CW，再调用`release_sock(C)`，从而不会丢失处理SYN-ACK时的state-change wakeup。
17. 第175章没有完成三次握手，也没有创建server child或让`connect()`返回。
18. 单章只解释本章路径；不要在批次末章重复总结前三章正文。

## 下一建议场景

```text
release_sock(C)
→ __release_sock drains client socket backlog
→ tcp_v4_do_rcv(C,SYN-ACK)
→ TCP_SYN_SENT client validates ACK/options
→ client C enters TCP_ESTABLISHED
→ client sends final ACK through lo
→ server ehash lookup finds request R
→ tcp_check_req creates full server child
→ replace/unhash R and hash child
→ child enters TCP_ESTABLISHED and accept queue
→ listener data_ready / accept wake semantics
→ wait_woken observes prior wake without real sleep
→ connect(7,...) returns 0
```

开始前固定最终ACK时序、request到child的引用替换、child bind继承、accept queue计数、client retransmission cleanup、wakeup flag与是否实际schedule。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件，直接提交`main`。
