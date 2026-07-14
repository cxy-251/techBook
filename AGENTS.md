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
```

最新三章：

- `LK-PIDFDCLOSE-155`：reap之后的pidfd为什么让epoll_wait返回EPOLLIN|EPOLLHUP？
- `LK-PIDFDCLOSE-156`：EPOLL_CTL_DEL怎样拆除pidfd callback与epitem？
- `LK-PIDFDCLOSE-157`：close()怎样释放pidfs inode、旧struct pid与eventpoll？

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

## 已完成pidfd cleanup场景

```text
parent epoll_wait(7, events2, 1, 0)
→ pidfd_poll sees no task linkage
→ deliver EPOLLIN|EPOLLHUP
→ level-triggered I remains ready
→ EPOLL_CTL_DEL removes CB and I
→ F6->f_ep=NULL; EP refcount 2→1
→ close(6) prunes pidfs dentry and evicts inode
→ inode put + delayed_put_pid finish old P refs
→ free exit metadata and old struct pid
→ close(7) drains empty EP; refcount 1→0
→ fd 6/7 closed; I/P/EP storage released through their required RCU paths
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
current executor   = parent
CPU/mode           = CPU0, x86-64 CPL 3
last syscall       = close(7)
last return        = 0
fd 6/7             = closed
child task         = absent
numeric PID C      = reusable, not reused in batch
pidfd file/path    = freed
old struct pid P   = logically dead; final storage released
exit metadata      = freed
callback CB        = synchronously freed
epitem I           = logically dead; RCU storage free
eventpoll EP       = logically dead; RCU storage free
global pidfs_mnt   = mounted
global anon_inodefs= active
filesystem I/O     = none
next entry         = unselected
```

## 必须保持的技术边界

1. zombie pidfd poll返回IN/RDNORM；post-reap增加HUP。
2. ADD自动加入ERR/HUP，用户无需显式请求HUP。
3. level-triggered永久ready item每次交付后重新入ready list。
4. DEL先拆target waitqueue callback，再删除epitem。
5. callback同步释放，epitem通过`kfree_rcu`释放storage。
6. pidfd file release不等于pid identity reference drop。
7. 未设置`PIDFD_AUTOKILL`时close不发送SIGKILL。
8. pidfs inode的`i_private`保存`struct pid`并持有reference。
9. `stashed_dentry_prune`必须在final `put_pid`前清掉`P->stashed`。
10. 数字PID释放早于旧`struct pid`storage释放。
11. inode put与`delayed_put_pid`先后可交换，refcount保证唯一final free。
12. `pidfs_free_pid`最终释放exit metadata与P。
13. pidfs mount与anon_inodefs都是全局对象，不因本批最后close而卸载。
14. close返回不要求所有RCU callback已执行，只要求对象已不可访问。

## 下一建议场景

优先候选是inotify与epoll：

```text
inotify_init1(IN_CLOEXEC) -> fd 6
inotify_add_watch(6, /work, IN_CREATE|IN_CLOSE_WRITE)
epoll_create1(EPOLL_CLOEXEC) -> fd 7
epoll_ctl ADD fd 6 EPOLLIN
parent epoll_wait blocks
helper creates and closes /work/new.txt
fsnotify queues inotify records and wakes epoll
parent epoll_wait returns and read(6) consumes records
```

开始前固定watch mask、name、event合并、queue状态与scheduler顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。继续时读取`AGENTS.md`、`project/STATE.rst`、目录、最近章节和manifest；每批固定写三章并同步五份接续文件。
