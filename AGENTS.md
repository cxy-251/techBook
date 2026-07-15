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
```

最新三章：

- `LK-TCPACCEPT-179`：accept4怎样先预留fd 8并创建尚未graft的socket与file？
- `LK-TCPACCEPT-180`：inet_csk_accept怎样取出R/H并把child graft到accepted socket？
- `LK-TCPACCEPT-181`：peer地址怎样写回用户态并最终发布close-on-exec fd 8？

进度：当前完成181章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

## 已完成TCP/IPv4 loopback accept

```text
server fd 6
→ socket/bind/listen
→ L is TCP_LISTEN on 127.0.0.1:28080

client fd 7
→ connect to 127.0.0.1:28080
→ autobind 127.0.0.1:40000
→ complete SYN/SYN-ACK/final ACK
→ C is SS_CONNECTED/TCP_ESTABLISHED

server child
→ final ACK creates H
→ H is TCP_ESTABLISHED in ehash
→ R becomes accept FIFO node with R.sk=H

accept4(6,&peer,&peer_len,SOCK_CLOEXEC)
→ FD_ADD reserves fd 8 before do_accept
→ open_fds[8]=1; close_on_exec[8]=1; fd[8]=NULL
→ sock_alloc creates accepted socket AS and sockfs inode I8
→ sock_alloc_file creates blocking F8
→ inet_csk_accept removes R/H from accept queue
→ L.sk_ack_backlog 1→0; queue head/tail become NULL
→ reqsk_put ends R lifetime
→ sock_graft links H, AS and AS.wq
→ AS.state=SS_CONNECTED
→ inet_getname returns peer 127.0.0.1:40000
→ move_addr_to_user writes 16-byte sockaddr_in
→ fd_install publishes F8 at fd 8
→ accept4 returns 8
```

## 当前精确状态

```text
system_state              = SYSTEM_RUNNING
current executor          = parent
CPU/mode                  = CPU0, x86-64 CPL 3
last syscall              = accept4(6,&peer,&peer_len,SOCK_CLOEXEC)
last return               = 8
accept schedule count     = 0

server fd 6               = open, blocking, close-on-exec
server file F6            = active sockfs socket file
listener L                = TCP_LISTEN
L local endpoint          = 127.0.0.1:28080
L bind/lhash2             = active
L SYN qlen/young          = 0/0
L accept queue            = empty
L sk_ack_backlog          = 0

accept node R             = released

client fd 7               = open, blocking, close-on-exec
client socket CS          = SS_CONNECTED
client C                  = TCP_ESTABLISHED
C tuple                   = 127.0.0.1:40000 → 127.0.0.1:28080
C bind/bind2/ehash/dst    = active
C retransmission tree     = empty

accepted fd 8             = open, blocking, close-on-exec
accepted file F8          = active sockfs socket file
accepted socket AS        = SS_CONNECTED
AS.sk                     = H
AS.file                   = F8
server child H            = TCP_ESTABLISHED
H tuple                   = 127.0.0.1:28080 ← 127.0.0.1:40000
H established ehash       = active
H bind/bind2 owner        = active
H.sk_socket               = AS
H.sk_wq                   = &AS.wq

peer sockaddr             = AF_INET 127.0.0.1:40000
peer_len                  = 16
packet/softirq backlog    = empty
next entry                = write(7,"hello",5)
```

## 必须保持的技术边界

1. `FD_ADD`先调用`get_unused_fd_flags`预留fd，再计算`do_accept`返回file的表达式。
2. 预留fd时`open_fds`与`close_on_exec`已设置，`fdtable.fd[8]`仍为NULL。
3. `SOCK_CLOEXEC`表达fdtable属性；它不会让`F8.f_flags`包含`O_NONBLOCK`。
4. `sock_alloc`先创建sockfs inode与空`struct socket AS`，不会创建新的TCP child。
5. `sock_alloc_file`发生在协议accept之前；F8可存在而尚未`fd_install`。
6. blocking accept允许等待，不代表本次一定睡眠；queue非空时不调用`inet_csk_wait_for_connect`。
7. `reqsk_queue_remove`在queue lock下把`sk_ack_backlog`从1减为0，并清空head/tail。
8. SYN阶段qlen/young与accept backlog是不同accounting；本章只修改后者。
9. 普通非TFO路径在移除后`reqsk_put(R)`结束R生命周期。
10. H是原有TCP child；accept不会复制或重新建立连接。
11. `sock_graft`写入`H.sk_wq=&AS.wq`、`AS.sk=H`和`H.sk_socket=AS`。
12. H的TCP状态先前已是`TCP_ESTABLISHED`；AS在graft后才进入`SS_CONNECTED`。
13. peer地址来自H的remote endpoint，即client `127.0.0.1:40000`。
14. peer copy发生在`fd_install`之前；copy失败会fput F8并关闭已取出的H，而不会重新排队。
15. `fd_install`是fd 8真正获得F8 pointer的发布点。
16. accepted fd 8是blocking、close-on-exec；listener file status不自动继承。
17. accept路径不发送TCP segment，不运行route lookup，也不触发NET_RX。
18. 单章只解释本章路径；不要在第三章重复概括前两章正文。

## 下一建议场景

```text
write(7,"hello",5)
→ x86-64 write syscall resolves client F7/CS/C
→ tcp_sendmsg_locked copies five bytes into client send queue
→ tcp_push/tcp_write_xmit builds data skb
→ transmit through IPv4 output and lo
→ established lookup finds H
→ tcp_rcv_established advances H.rcv_nxt
→ queue hello on H.sk_receive_queue
→ H.sk_data_ready marks accepted fd 8 readable
→ client write returns 5
→ read(8,buf,5) consumes hello
```

开始前固定write flags、Nagle/MSG_MORE状态、data segment sequence/ACK、loopback softirq timing、H receive queue ownership、ACK策略以及write返回与server read的章节边界。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件，直接提交`main`。
