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
```

二十个运行期实验已闭环：cold read、O_SYNC write、fork、child COW、static ELF exec、exit/wait、ext4 create、delalloc+fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep、anonymous pipe读写与teardown、private futex wait/wake、eventfd counter read/wake、eventfd final close、eventfd level-triggered epoll wake、eventfd/epoll cleanup、blocked SIGUSR1通过signalfd+epoll交付，以及signalfd/epoll cleanup与final teardown。

最新三章：

- `LK-SIGNALFDCLOSE-143`：零超时epoll_wait() 怎样清理signalfd的stale-ready item？
- `LK-SIGNALFDCLOSE-144`：EPOLL_CTL_DEL 怎样拆除signalfd callback与epitem？
- `LK-SIGNALFDCLOSE-145`：close() 怎样释放signalfd与eventpoll，却保留共享sighand wait queue？

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

旧章节中的 `Linux 6.12.95` 是历史显示标签错误；固定commit始终是Linux 7.2-rc1。

## 已完成 signalfd cleanup 固定场景

```text
runtime relation = continuation of LK-SIGNALFD-140..142
CPUs online      = CPU0 only
process          = parent + helper threads in one TGID
files table      = shared through CLONE_FILES
signal state     = shared signal_struct and sighand_struct
scheduler        = both SCHED_NORMAL
blocked mask     = parent/helper both contain SIGUSR1
pending state    = no private/shared SIGUSR1
signalfd fd      = 6, blocking, close-on-exec
signalfd file    = F6
signalfd ctx     = S
epoll fd         = 7, close-on-exec
eventpoll file   = F7
eventpoll object = EP
registration     = one level-triggered EPOLLIN epitem I
event data       = 0x51FD6
callback P       = non-exclusive on shared sighand->signalfd_wqh
entry ready      = stale I on EP.rdllist
stale check      = epoll_wait(7, events2, 1, 0)
delete call      = epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
final closes     = close(6), close(7)
concurrency      = no signal/callback/ctl/wait/close race
failure policy   = no fd/copy/VFS/slab/signal/scheduler failure
```

## 已执行控制流

```text
epoll_wait(7, events2, 1, 0)
→ zero timeout sets timed_out=1
→ stale I makes initial ready check true
→ ep_start_scan moves I to local scan batch
→ ep_item_poll temporarily pins F6
→ signalfd_poll checks private/shared pending under sighand siglock
→ no SIGUSR1 remains, so no EPOLLIN
→ no event copied and I not requeued
→ EP.rdllist becomes empty
→ return 0 without sleeping

epoll_ctl(7, DEL, 6, NULL)
→ lock EP.mtx and find I
→ remove P from shared signalfd_wqh
→ waitqueue lock synchronizes callback removal
→ free P synchronously
→ epi_fget temporarily pins F6
→ under F6.f_lock set F6.f_ep=NULL
→ remove reverse link and free last epitems_head
→ erase I from EP.rbr
→ kfree_rcu(I)
→ EP.refcount 2 -> 1
→ return 0

close(6)
→ remove shared fd 6 and cloexec bit
→ synchronous final __fput(F6)
→ eventpoll release uses F6.f_ep=NULL fast path
→ signalfd_release kfree(S)
→ free [signalfd] pseudo path/file
→ return 0
→ shared sighand->signalfd_wqh remains active and empty

close(7)
→ remove shared fd 7 and cloexec bit
→ synchronous final __fput(F7)
→ ep_eventpoll_release / ep_clear_and_put
→ empty pollwait drain and empty tree drain
→ EP.refcount 1 -> 0
→ ep_free / kfree_rcu(EP)
→ free [eventpoll] pseudo path/file
→ return 0
```

## 当前精确状态

```text
system_state          = SYSTEM_RUNNING
runtime scenario      = signalfd/eventpoll lifecycle complete
current executor      = parent
CPU                   = CPU0
CPU mode              = x86-64 CPL 3
scheduling class      = SCHED_NORMAL
parent state          = TASK_RUNNING
parent on_rq/on_cpu   = 1 / 1
last syscall          = close(7)
last return           = 0
zero epoll_wait return= 0
epoll DEL return      = 0
close(6) return       = 0
fd 6                  = closed and unallocated
fd 7                  = closed and unallocated
signalfd F6/S         = freed
callback P            = synchronously freed
epitem I              = logically dead; kfree_rcu pending/completed
eventpoll F7          = freed
eventpoll EP          = logically dead; kfree_rcu pending/completed
shared sighand        = active
shared signalfd_wqh   = active and empty
blocked masks         = both still contain SIGUSR1
parent private pending= no SIGUSR1
shared pending        = no SIGUSR1
singleton anon inode  = active
global anon_inode_mnt = mounted
helper                = blocked outside old signalfd/eventpoll
filesystem I/O        = none
next entry            = unselected runtime scenario
```

## 必须保持的技术边界

1. zero-time epoll会验证ready candidate，但不会等待新事件。
2. ready-list membership不是永久readiness事实。
3. re-poll无匹配event时，只删除ready membership，不删除registration。
4. `EPOLL_CTL_DEL`使用`(file, fd)` key；event参数可以为NULL。
5. callback entry必须先从target wait queue移除，再释放epitem。
6. waitqueue lock把callback执行与callback removal串行化。
7. `P`同步释放，`I`通过`kfree_rcu`延迟回收storage。
8. 最后watcher删除时`F6->f_ep=NULL`。
9. epitem持有一个eventpoll ref；DEL使`EP.refcount`从2降为1。
10. signalfd ctx与shared sighand wait queue是不同对象。
11. `signalfd_release`只释放private ctx，不销毁`signalfd_wqh`。
12. `signalfd_cleanup/wake_up_pollfree`属于sighand teardown，不属于file close。
13. 显式DEL使signalfd close的eventpoll release走fast path。
14. eventpoll close即使tree为空也保持pollwait-first、tree-second两遍drain。
15. `EP.refcount`从1归零后由`ep_free`结束逻辑生命周期。
16. 关闭signalfd不会解除SIGUSR1 block或恢复旧signal mask。
17. per-file pseudo path结束，全局anon_inodefs继续存在。
18. 整个场景没有磁盘I/O、journal或writeback。

## 下一建议场景

优先候选是`timerfd_create`与epoll组合：

```text
timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC) -> fd 6
timerfd_settime(one-shot relative 20ms)
epoll_create1(EPOLL_CLOEXEC) -> fd 7
epoll_ctl ADD timerfd EPOLLIN
parent epoll_wait blocks
→ local APIC timer interrupt
→ hrtimer callback increments expirations
→ timerfd poll callback queues epitem and wakes parent
→ epoll_wait returns EPOLLIN
→ read(fd 6, &expirations, 8) returns one expiration
```

开始前固定absolute/relative mode、clockid、cancel-on-set、interval、hrtimer base、expiration count、callback和scheduler顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
