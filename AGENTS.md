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
```

最新三章：

- `LK-UNIXSOCKCLOSE-167`：EPOLL_CTL_DEL怎样从persistent-ready Unix socket拆除callback与epitem？
- `LK-UNIXSOCKCLOSE-168`：close(6)怎样释放socket A，却让dead SA继续被peer reference保持？
- `LK-UNIXSOCKCLOSE-169`：close(7)与close(8)怎样释放两端Unix socket和空eventpoll？

进度：当前完成169章。项目没有预设固定总章数；后续按源码主线与必要场景自然推进，不计算剩余章数。

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

## 已完成Unix socketpair最终teardown

```text
initial fd6 registration is persistent-ready after peer SHUT_WR and EOF read
→ epoll_ctl(8,DEL,6,NULL)
→ remove P from socket A wait queue and free it synchronously
→ clear F6.f_ep and reverse link
→ erase I from EP.rbr and EP.rdllist; kfree_rcu(I)
→ EP refcount 2→1
→ close(6)
→ SA orphan, TCP_CLOSE, SHUTDOWN_MASK, unix_peer(SA)=NULL
→ SB gains SHUTDOWN_MASK/HUP semantics
→ drop A-held reference to SB
→ SA remains alive because unix_peer(SB)=SA
→ free F6 and socket A sockfs VFS objects
→ close(7)
→ SB orphan, TCP_CLOSE, SHUTDOWN_MASK
→ clear unix_peer(SB)
→ drop final peer reference to SA
→ unix_sock_destructor frees SA/UA, then SB/UB
→ free F7 and socket B sockfs VFS objects
→ close(8)
→ empty ep_clear_and_put
→ EP refcount 1→0 and kfree_rcu(EP)
→ free F8 and eventpoll pseudo path
```

## 当前精确状态

```text
system_state        = SYSTEM_RUNNING
current executor    = parent
CPU/mode            = CPU0, x86-64 CPL 3
parent state        = TASK_RUNNING, on_rq=1, on_cpu=1
helper              = blocked outside released objects
EPOLL_CTL_DEL       = 0
close(6)            = 0
close(7)            = 0
last syscall        = close(8)
last return         = 0
fd 6/7/8            = closed
callback P          = synchronously freed
epitem I            = logically dead; RCU storage free
socket files F6/F7 = freed
SA/UA               = freed
SB/UB               = freed
Unix peer refs      = none
eventpoll EP        = logically dead; RCU storage free
eventpoll F8        = freed
global sockfs       = active
global anon_inodefs = active
next entry          = unselected
```

## 必须保持的技术边界

1. persistent-ready registration可以直接DEL，无需先消费readiness。
2. callback P同步free；epitem I通过RCU延迟free。
3. `F6.f_ep=NULL`使close(6)不进入eventpoll target-release慢路径。
4. close先撤销共享fdtable中的数字fd，再执行最后`__fput`。
5. `unix_release_sock`把关闭端设为orphan、`TCP_CLOSE`与`SHUTDOWN_MASK`。
6. close(6)只清`unix_peer(SA)`，不会同步清`unix_peer(SB)`。
7. dead SA可以在F6和socket A VFS对象释放后继续由SB peer reference保持。
8. peer B得到full shutdown/HUP语义，但自己的`sk_state`到close(7)才变成`TCP_CLOSE`。
9. close(7)清除最后peer pointer并释放SA的最后reference。
10. socket file、sockfs inode/`struct socket`与`struct sock`有不同lifetime。
11. 两端receive queue为空，所以close不走`ECONNRESET`或skb丢弃分支。
12. eventpoll base reference由F8持有；close(8)使EP refcount归零。
13. epitem和eventpoll storage都可在close返回后等待RCU grace period。
14. sockfs与anon_inodefs是全局pseudo filesystems，不随本场景fd关闭而卸载。
15. Unix socketpair路径不经过IP、路由、网卡、ext4或块设备。

## 下一建议场景

```text
server socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
→ bind(127.0.0.1:fixed_port)
→ listen(backlog)
client socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0)
→ connect(127.0.0.1:fixed_port)
→ loopback route and TCP SYN/SYN-ACK/ACK
→ accept4 publishes connected server fd
```

开始前固定network namespace、loopback device、route、port、socket state、request socket、softirq和scheduler顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件。
