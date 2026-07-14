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
```

最新三章：

- `LK-TCPHANDSHAKE-176`：release_sock怎样处理SYN-ACK并让client发送最终ACK？
- `LK-TCPHANDSHAKE-177`：最终ACK怎样把request_sock替换成ESTABLISHED server child？
- `LK-TCPHANDSHAKE-178`：blocking connect为什么无需真正睡眠就返回0？

进度：当前完成178章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

## 已完成TCP/IPv4 loopback三次握手

```text
server fd 6
→ socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
→ bind(127.0.0.1:28080)
→ listen(6,8)
→ listener L enters TCP_LISTEN and exact-address lhash2

client fd 7
→ socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
→ connect(7,127.0.0.1:28080)
→ local route selects source 127.0.0.1 and lo
→ connect autobinds port 40000
→ C enters TCP_SYN_SENT and ehash
→ C_ISN=0x13572468
→ send SYN through lo
→ listener creates TCP_NEW_SYN_RECV request R
→ S_ISN=0x24681357
→ R enters ehash, arms timer, qlen/young=1/1
→ send SYN-ACK through lo
→ parent owns C, so SYN-ACK enters C.sk_backlog
→ install connect wait entry CW
→ release_sock(C) drains SYN-ACK
→ tcp_rcv_synsent_state_process validates ACK/options
→ original SYN leaves retransmission tree
→ C enters TCP_ESTABLISHED
→ state-change sets CW.WQ_FLAG_WOKEN
→ send final ACK seq=C_ISN+1 ack=S_ISN+1
→ final ACK traverses lo and finds R
→ tcp_check_req validates third ACK
→ create full server child H in TCP_SYN_RECV
→ H inherits 127.0.0.1:28080 bind ownership
→ replace R's ehash identity with H
→ delete R request timer; qlen/young=0/0
→ reuse R as accept FIFO node with R.sk=H
→ L.sk_ack_backlog=1
→ H processes final ACK and enters TCP_ESTABLISHED
→ L.sk_data_ready publishes accept readiness
→ wait_woken sees WQ_FLAG_WOKEN and skips schedule_timeout
→ CS becomes SS_CONNECTED
→ connect returns 0
```

## 当前精确状态

```text
system_state              = SYSTEM_RUNNING
current executor          = parent
CPU/mode                  = CPU0, x86-64 CPL 3
last syscall              = connect(7,127.0.0.1:28080)
last return               = 0
connect schedule count    = 0
connect wait entry CW     = removed

server fd 6               = open, blocking, close-on-exec
server file F6            = active sockfs socket file
server listener L         = TCP_LISTEN
server local endpoint     = 127.0.0.1:28080
server bind/lhash2        = active
server SYN qlen/young     = 0/0
server sk_ack_backlog     = 1
server accept head/tail   = R/R

accept node R             = active in accept FIFO
R.sk                      = H
R ehash identity          = removed/replaced
R request timer           = deleted

server child H            = TCP_ESTABLISHED
H local endpoint          = 127.0.0.1:28080
H remote endpoint         = 127.0.0.1:40000
H established ehash       = active
H bind/bind2 owner        = active
H sk_socket               = NULL
H sockfs file/fd          = none

client fd 7               = open, blocking, close-on-exec
client CS                 = SS_CONNECTED
client C                  = TCP_ESTABLISHED
client local endpoint     = 127.0.0.1:40000
client remote endpoint    = 127.0.0.1:28080
client bind/bind2         = active; SOCK_CONNECT_BIND
client established ehash  = active
client dst                = local route through lo
client snd_una/snd_nxt    = C_ISN+1 / C_ISN+1
client rcv_nxt            = S_ISN+1
client retrans tree       = empty
client socket backlog     = empty

packet/softirq backlog    = empty
next entry                = accept4(6,...,SOCK_CLOEXEC)
next accepted fd          = 8
```

## 必须保持的技术边界

1. `release_sock()`不仅释放用户锁；存在socket backlog时先同步运行`__release_sock()`。
2. `__release_sock()`摘下backlog链并在process context调用协议`sk_backlog_rcv`。
3. SYN-ACK确认`C_ISN+1`后，original SYN从client retransmission tree删除。
4. client先进入`TCP_ESTABLISHED`，socket API层稍后才从`SS_CONNECTING`进入`SS_CONNECTED`。
5. `sk_state_change`即使面对当前仍在运行的task，也会设置`CW.WQ_FLAG_WOKEN`。
6. `WQ_FLAG_WOKEN`与barrier协议防止wakeup发生在`wait_woken()`之前而丢失。
7. 最终ACK是纯ACK，不占用新sequence number，也不进入retransmission tree。
8. `rcu_read_unlock_bh()`可以让final ACK的NET_RX softirq嵌套运行在client ACK发送调用栈中。
9. server final ACK lookup先命中`TCP_NEW_SYN_RECV` request R，不重新只靠listener查找。
10. 完整server child H是新分配的`tcp_sock`，不是在request R上原地扩容。
11. H从listener继承默认配置，从R恢复四元组、ISN、MSS、timestamp与window scaling。
12. `__inet_inherit_port()`把H加入server port 28080的真实bind/bind2 owners。
13. `inet_ehash_nolisten()`先用H替换R的ehash身份。
14. request qlen/young归零与listener `sk_ack_backlog`增加属于不同accounting。
15. R没有在hashdance结束时释放；它转为accept queue节点并保存`R.sk=H`。
16. H在处理final ACK后才从`TCP_SYN_RECV`进入`TCP_ESTABLISHED`。
17. H尚无`struct socket`、sockfs file或fd；这些对象由`accept4()`建立。
18. blocking connect进入等待函数不代表必然调用scheduler；本场景schedule count为0。
19. `connect()=0`只代表client主动建立成功，不代表server应用已经accept。
20. 单章只解释本章路径；不要在批次末章重复总结前三章正文。

## 下一建议场景

```text
accept4(6,user_addr,user_addrlen,SOCK_CLOEXEC)
→ resolve listener socket L
→ tcp_accept waits on/nonblocking-checks accept queue
→ remove accept node R and child H
→ L.sk_ack_backlog 1 → 0
→ release accept-node request R
→ allocate accepted struct socket AS
→ graft H to AS
→ AS.state=SS_CONNECTED
→ create blocking close-on-exec sockfs file F8
→ reserve and publish fd 8
→ copy peer address 127.0.0.1:40000
→ accept4 returns 8
```

开始前固定accept调用是否blocking、peer sockaddr buffer长度、queue removal时R/H引用变化、accepted socket/file/fd对象、`SOCK_CLOEXEC` fdtable bit与server child从orphan kernel endpoint变为用户socket的精确位置。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件，直接提交`main`。
