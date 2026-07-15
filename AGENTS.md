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
```

最新三章：

- `LK-TCPDATA-182`：write(7,"hello",5)怎样把5字节排入client TCP write queue？
- `LK-TCPDATA-183`：PSH|ACK数据段怎样通过lo进入H并触发立即ACK？
- `LK-TCPDATA-184`：write怎样在ACK处理后返回5，并让read(8)取出hello？

进度：当前完成184章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

## 已完成TCP/IPv4 loopback数据传递

```text
client fd 7
→ write(7,"hello",5)
→ sock_write_iter resolves F7/CS/C
→ tcp_sendmsg_locked allocates one skb
→ copy five bytes into skb page frag
→ seq C_ISN+1..C_ISN+6, flags ACK|PSH
→ tcp_write_xmit sends a clone through IPv4 output and lo
→ original skb enters C retransmission tree
→ established ehash lookup finds server child H

server child H
→ tcp_rcv_established accepts in-order payload
→ H.rcv_nxt C_ISN+1→C_ISN+6
→ queue one five-byte skb on H.sk_receive_queue
→ tcp_data_ready exposes EPOLLIN on accepted fd 8
→ first-data quickack sends ACK C_ISN+6

client ACK completion
→ parent still owns C, so ACK enters C.sk_backlog
→ release_sock(C) drains ACK in process context
→ C.snd_una C_ISN+1→C_ISN+6
→ original hello skb leaves retransmission tree
→ write returns 5

accepted fd 8
→ read(8,buf,5)
→ tcp_recvmsg_locked finds queue non-empty
→ copy hello without sk_wait_data
→ H.copied_seq C_ISN+1→C_ISN+6
→ remove receive skb
→ read returns 5
```

## 当前精确状态

```text
system_state              = SYSTEM_RUNNING
current executor          = parent
CPU/mode                  = CPU0, x86-64 CPL 3
last syscall              = read(8,buf,5)
last return               = 5
user buffer               = "hello"
write schedule count      = 0
read schedule count       = 0

server fd 6               = open, blocking, close-on-exec
listener L                = TCP_LISTEN
L local endpoint          = 127.0.0.1:28080
L bind/lhash2             = active
L accept queue            = empty
L sk_ack_backlog          = 0

client fd 7               = open, blocking, close-on-exec
client C                  = TCP_ESTABLISHED
C tuple                   = 127.0.0.1:40000 → 127.0.0.1:28080
C snd_una/snd_nxt         = C_ISN+6 / C_ISN+6
C write_seq               = C_ISN+6
C rcv_nxt                 = S_ISN+1
C write/rtx/backlog       = empty / empty / empty
C bind/bind2/ehash/dst    = active

accepted fd 8             = open, blocking, close-on-exec
accepted socket AS        = SS_CONNECTED
server child H            = TCP_ESTABLISHED
H tuple                   = 127.0.0.1:28080 ← 127.0.0.1:40000
H rcv_nxt/copied_seq      = C_ISN+6 / C_ISN+6
H snd_una/snd_nxt         = S_ISN+1 / S_ISN+1
H receive queue           = empty
H readable bytes          = 0
H ehash/bind ownership    = active

packet/softirq backlog    = empty
next entry                = close(7)
```

## 必须保持的技术边界

1. fd 7解析到client C；fd 8只在后续read中访问server child H。
2. 固定write flags为0：没有MSG_MORE、MSG_OOB、MSG_DONTWAIT、zerocopy或splice。
3. negotiated MSS足够容纳5字节；本批只生成一个data skb。
4. tcp_skb_entail先以seq=end_seq=C_ISN+1和ACK初始化空skb。
5. copy完成后C.write_seq与skb.end_seq变为C_ISN+6，snd_nxt要在发送发布后才推进。
6. 没有MSG_MORE时tcp_mark_push增加PSH；PSH不占用sequence number。
7. 没有旧的unacked data，所以Nagle与autocork不会扣住hello。
8. 发送clone通过lo；原始skb进入client retransmission tree用于可靠重传。
9. data segment是seq C_ISN+1、ack S_ISN+1、ACK|PSH、payload hello。
10. established lookup命中H，不回到listener，也不创建request_sock。
11. H未被用户task持有，data直接由NET_RX处理，不进入H.sk_backlog。
12. H.rcv_nxt推进到C_ISN+6；copied_seq在read前保持C_ISN+1。
13. 五字节达到默认sk_rcvlowat=1，tcp_data_ready使accepted fd 8可读。
14. 这是H收到的首份data；ato=0使quickack立即发送ACK C_ISN+6。
15. parent仍持有C，反向ACK先进入C.sk_backlog。
16. release_sock(C)处理ACK后snd_una推进并清空retransmission tree，随后write返回5。
17. write返回5表示TCP接受字节；一般语义不保证peer application已经read。
18. read时receive queue已经非空，不进入sk_wait_data或scheduler。
19. read复制hello、推进H.copied_seq并移除receive skb。
20. quickack已经清除ACK schedule，本次tcp_cleanup_rbuf不再发送第二个ACK。
21. 单章只解释本章路径；第三章不重复概括前两章正文。

## 下一建议场景

```text
close(7)
→ fdtable撤销client fd 7
→ final __fput enters TCP active close
→ C queues and sends FIN through lo
→ H consumes FIN after all hello bytes were read
→ H enters TCP_CLOSE_WAIT
→ accepted fd 8 exposes EOF/readability
→ ACK advances C toward TCP_FIN_WAIT2
→ later close(8) completes peer FIN and connection teardown
```

开始前固定close是否同步进入__fput、FIN sequence、H的CLOSE_WAIT与EOF发布、ACK回到C的ownership时序、fd 8最后close以及TIME_WAIT边界。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件，直接提交`main`。

