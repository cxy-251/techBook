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
```

最新三章：

- `LK-UNIXSOCK-164`：socketpair怎样建立双向Unix stream并让parent阻塞在epoll_wait？
- `LK-UNIXSOCK-165`：helper写入hello时，Unix stream skb怎样唤醒epoll并让read返回5？
- `LK-UNIXSOCK-166`：shutdown(SHUT_WR)怎样让peer收到EPOLLRDHUP并让read返回EOF？

进度：当前166章。按最初195章目标还剩29章；最终章数未锁死，按当前颗粒度合理总量约190至220章。

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

## 已完成Unix socketpair数据与half-close场景

```text
socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,sv)
→ reserve fd 6/7 and create two PF_UNIX stream sockets
→ unix_peer(SA)=SB, unix_peer(SB)=SA
→ both sk_state=TCP_ESTABLISHED
→ install sockfs files F6/F7
→ epoll_create1 -> fd 8
→ ADD fd 6 EPOLLIN|EPOLLRDHUP data 0x554E4958
→ callback P attaches to socket A wait queue
→ initial poll requested mask is not ready
→ parent blocks on EP.wq
→ helper write(7,"hello",5)
→ one skb enters SA receive queue; UA.inq_len 0→5
→ SA.sk_data_ready invokes P; I enters ready list; parent wakes
→ epoll_wait returns EPOLLIN/data 0x554E4958
→ parent read(6,5) copies hello, consumes skb and UA.inq_len 5→0
→ I remains stale-ready
→ parent re-enters epoll_wait
→ re-poll empty queue removes stale I, then parent sleeps
→ helper shutdown(7,SHUT_WR)
→ SB gains SEND_SHUTDOWN; peer SA gains RCV_SHUTDOWN
→ SA.sk_state_change invokes P and wakes parent
→ epoll_wait returns EPOLLIN|EPOLLRDHUP/data 0x554E4958
→ read(6) sees empty queue plus RCV_SHUTDOWN and returns EOF 0
```

## 当前精确状态

```text
system_state        = SYSTEM_RUNNING
current executor    = parent
CPU/mode            = CPU0, x86-64 CPL 3
parent state        = TASK_RUNNING, on_rq=1, on_cpu=1
helper              = blocked outside socket objects
socketpair result   = 0, sv={6,7}
helper write        = 5
first epoll wait    = 1, EPOLLIN/data 0x554E4958
first read          = 5, bytes hello
shutdown(7,SHUT_WR) = 0
second epoll wait   = 1, EPOLLIN|EPOLLRDHUP/data 0x554E4958
last syscall        = read(6)
last return         = 0 EOF
fd 6/7/8            = open
socket files F6/F7 = active sockfs files
SA/SB state         = TCP_ESTABLISHED
SA shutdown         = RCV_SHUTDOWN
SB shutdown         = SEND_SHUTDOWN
SA peer             = SB
SB peer             = SA
SA/SB receive queue = empty
UA/UB inq_len       = 0/0
callback P          = active on socket A wait queue
epitem I            = active and persistent-ready
EP refcount         = 2
EP wq               = empty
next entry          = unselected
```

## 必须保持的技术边界

1. `socketpair`的fd reserve、用户数组copy和`fd_install`是不同阶段。
2. AF_UNIX socketpair两端互相持有peer reference。
3. Unix stream使用skb与socket wait queue，不经过IP、路由、网卡或块设备。
4. socket file由sockfs承载，不是anon_inodefs。
5. 初始socket可写不会匹配只监听`EPOLLIN|EPOLLRDHUP`的registration。
6. callback P位于socket A wait queue，sleeping parent位于eventpoll wait queue。
7. `unix_stream_sendmsg`通过peer pointer直接找到SA。
8. write数据先复制到skb，再进入SA receive queue。
9. `UA.inq_len`本批为0→5→0。
10. `sk_data_ready`只建立candidate readiness；epoll delivery必须re-poll。
11. Unix stream不保证一次write、一条skb和一次read一一对应。
12. `UA.iolock`串行化同一socket上的stream reader。
13. read清空queue不会主动移除eventpoll ready membership。
14. 第二次epoll_wait先移除stale I，再真正睡眠。
15. `shutdown`不撤销fd，也不释放file。
16. `SHUT_WR`本端设置`SEND_SHUTDOWN`，peer设置`RCV_SHUTDOWN`。
17. half-close不清peer pointer，`sk_state`保持`TCP_ESTABLISHED`。
18. `RCV_SHUTDOWN`使poll报告`EPOLLIN|EPOLLRDHUP`。
19. 单向half-close不报告`EPOLLHUP`。
20. empty queue + `RCV_SHUTDOWN`使stream read返回0 EOF。
21. EOF不是零长度skb。
22. RDHUP是persistent level readiness，read EOF不会消费它。

## 下一建议场景

```text
epoll_ctl(8,EPOLL_CTL_DEL,6,NULL)
→ remove socket wait callback P and epitem I
close(6)
→ release socket A and notify peer B of disconnect/full shutdown
close(7)
→ release socket B and mutual peer references
close(8)
→ release empty eventpoll and sockfs/eventpoll files
```

开始前固定`unix_release_sock`对peer的shutdown/state更新、wake mask、peer reference下降、receive queue清理、sockfs inode/file teardown与eventpoll RCU释放顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件。
