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
```

二十二个运行期实验已闭环：cold read、O_SYNC write、fork、child COW、static ELF exec、exit/wait、ext4 create、delalloc+fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep、anonymous pipe读写与teardown、private futex wait/wake、eventfd counter read/wake、eventfd final close、eventfd level-triggered epoll wake、eventfd/epoll cleanup、blocked SIGUSR1通过signalfd+epoll交付、signalfd/epoll cleanup、one-shot timerfd通过LAPIC/hrtimer/epoll交付，以及timerfd/epoll cleanup与final teardown。

最新三章：

- `LK-TIMERFDCLOSE-149`：零超时epoll_wait() 怎样清理timerfd的stale-ready item？
- `LK-TIMERFDCLOSE-150`：EPOLL_CTL_DEL 怎样拆除timerfd callback与epitem？
- `LK-TIMERFDCLOSE-151`：close() 怎样释放timerfd与eventpoll并结束两套RCU生命周期？

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

## 已完成 timerfd cleanup 固定场景

```text
runtime relation = continuation of LK-TIMERFD-146..148
CPUs online      = CPU0 only
process          = parent + helper threads in one TGID
files table      = shared through CLONE_FILES
scheduler        = both SCHED_NORMAL
timerfd fd       = 6, blocking, close-on-exec
timerfd file     = F6
timerfd ctx      = T
clock             = CLOCK_MONOTONIC
interval          = 0, one-shot
hrtimer           = inactive and not queued
T state           = ticks=0, expired=0, tintv=0
epoll fd          = 7, close-on-exec
eventpoll file    = F7
eventpoll object  = EP
registration      = one level-triggered EPOLLIN epitem I
event data        = 0x71FD6
callback P        = non-exclusive on T.wqh
entry ready       = stale I on EP.rdllist
stale check       = epoll_wait(7, events2, 1, 0)
delete call       = epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
final closes      = close(6), close(7)
concurrency       = no expiry/callback/ctl/wait/close race
failure policy    = no fd/copy/VFS/slab/timer/scheduler failure
```

## 已执行控制流

```text
epoll_wait(7, events2, 1, 0)
→ zero timeout, existing stale I makes initial ready check true
→ ep_start_scan moves I to local scan batch
→ timerfd_poll runs with no new queue callback
→ lock T.wqh and observe T.ticks=0
→ no EPOLLIN, no event copy, no level-triggered requeue
→ EP.rdllist becomes empty
→ return 0 without sleeping

epoll_ctl(7, DEL, 6, NULL)
→ resolve F7/F6 and lock EP.mtx
→ find I by (F6, fd 6)
→ remove P from T.wqh under waitqueue lock
→ free P synchronously
→ epi_fget pins F6
→ under F6.f_lock set F6.f_ep=NULL for last watcher
→ remove reverse link
→ erase I from EP.rbr
→ kfree_rcu(I)
→ EP.refcount 2 -> 1
→ return 0

close(6)
→ remove shared fd 6 and cloexec bit
→ synchronous final __fput(F6)
→ eventpoll release uses F6.f_ep=NULL fast path
→ timerfd_remove_cancel no-op for CLOCK_MONOTONIC
→ hrtimer_cancel(inactive) returns 0
→ kfree_rcu(T)
→ free [timerfd] pseudo path/file
→ return 0

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
runtime scenario      = timerfd/eventpoll lifecycle complete
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
timerfd F6            = freed
timerfd ctx T         = logically dead; kfree_rcu pending/completed
callback P            = synchronously freed
epitem I              = logically dead; kfree_rcu pending/completed
eventpoll F7          = freed
eventpoll EP          = logically dead; kfree_rcu pending/completed
singleton anon inode  = active
global anon_inode_mnt = mounted
helper                = blocked outside old timerfd/eventpoll
blocked masks         = both still contain SIGUSR1
pending SIGUSR1       = none
filesystem I/O        = none
next entry            = unselected runtime scenario
```

## 必须保持的技术边界

1. zero-time epoll处理已有ready candidate，但不等待未来event。
2. ready-list membership不是永久readiness事实。
3. re-poll无匹配event时只删除ready membership，不删除registration。
4. `EPOLL_CTL_DEL`使用`(file, fd)` key；event参数可以为NULL。
5. callback entry必须先从target wait queue移除，再释放epitem。
6. waitqueue lock串行化timerfd wake callback与callback removal。
7. `P`同步释放，`I`通过`kfree_rcu`延迟回收storage。
8. 最后watcher删除时`F6->f_ep=NULL`。
9. epitem持有一个eventpoll ref；DEL使`EP.refcount`从2降为1。
10. CLOCK_MONOTONIC relative timerfd不进入cancel-on-set list。
11. 已到期one-shot hrtimer为inactive，release中的`hrtimer_cancel`返回0。
12. timerfd ctx通过`kfree_rcu(T)`结束storage生命周期。
13. 显式DEL使timerfd close的eventpoll release走fast path。
14. eventpoll close即使tree为空也保持pollwait-first、tree-second两遍drain。
15. `EP.refcount`从1归零后由`ep_free`结束逻辑生命周期。
16. `I`、`T`、`EP`的RCU callback互相独立。
17. close返回时对象已不可访问，不代表RCU storage free一定已经执行。
18. per-file pseudo path结束，全局anon_inodefs继续存在。
19. 整个场景没有磁盘I/O、journal或writeback。

## 下一建议场景

优先候选是pidfd与epoll组合：

```text
fork/clone child
→ pidfd_open(child_pid, 0) -> fd 6
→ epoll_create1(EPOLL_CLOEXEC) -> fd 7
→ epoll_ctl ADD pidfd EPOLLIN
→ parent epoll_wait blocks
→ child exits and becomes waitable
→ pidfd poll callback queues epitem and wakes parent
→ epoll_wait returns one event
→ waitid(P_PIDFD, fd 6, ...) consumes exit status
```

开始前固定clone flags、child exit status、pidfd type、wait semantics、zombie/reap时点、poll mask、callback和scheduler顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
