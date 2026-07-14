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
```

二十三个运行期实验已闭环：cold read、O_SYNC write、fork、child COW、static ELF exec、exit/wait、ext4 create、delalloc+fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep、anonymous pipe读写与teardown、private futex wait/wake、eventfd counter read/wake、eventfd final close、eventfd level-triggered epoll wake、eventfd/epoll cleanup、blocked SIGUSR1通过signalfd+epoll交付、signalfd/epoll cleanup、one-shot timerfd通过LAPIC/hrtimer/epoll交付、timerfd/epoll cleanup，以及pidfd通过pidfs与epoll观察child退出并用waitid(P_PIDFD)回收child。

最新三章：

- `LK-PIDFD-152`：pidfd_open() 怎样建立pidfs file并让epoll_wait监视child？
- `LK-PIDFD-153`：child _exit(42) 怎样通过pid->wait_pidfd唤醒epoll_wait？
- `LK-PIDFD-154`：waitid(P_PIDFD) 怎样读取退出状态并回收child？

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

## 已完成 pidfd 固定场景

```text
runtime relation = independent scenario after LK-TIMERFDCLOSE-151
CPUs online      = CPU0 only
processes        = parent and one direct child, separate TGIDs
process shape    = both single-threaded
files tables     = separate after ordinary fork
scheduler        = both SCHED_NORMAL
child PID        = C in parent's active pid namespace
child exit       = _exit(42), exit_signal=SIGCHLD
SIGCHLD policy   = default; no explicit SIG_IGN or SA_NOCLDWAIT
pidfd fd         = 6, blocking, O_RDWR, close-on-exec
pid object       = P
pidfs inode      = N with i_private=P
epoll fd         = 7, close-on-exec
eventpoll        = EP
registration     = level-triggered EPOLLIN epitem I
event data       = 0x50494436
callback CB      = non-exclusive on P->wait_pidfd
parent wait      = epoll_wait(7, events, 1, -1)
reap call        = waitid(P_PIDFD, 6, &si, WEXITED, NULL)
concurrency      = no ptrace/wait/ctl/close/exec race
failure policy   = no fd/pidfs/copy/slab/signal/scheduler failure
```

## 已执行控制流

```text
ordinary fork creates direct child PID C
→ parent/child have separate files_struct objects

parent pidfd_open(C, 0)
→ find_get_pid resolves stable struct pid P
→ pidfd_prepare locks P->wait_pidfd.lock
→ verify PIDTYPE_PID and PIDTYPE_TGID linkages
→ reserve close-on-exec fd 6
→ pidfs_alloc_file creates/reuses stashed pidfs inode N
→ N.i_private=P and N holds a pid reference
→ publish O_RDWR pidfd file F6 as fd 6

parent epoll_create1 -> fd 7
parent epoll_ctl ADD fd 6 EPOLLIN data=0x50494436
→ allocate epitem I
→ EP.refcount 1 -> 2
→ pidfd_poll attaches CB to P->wait_pidfd
→ live child exit_state=0, so no initial readiness

parent epoll_wait
→ exclusive W waits on EP.wq
→ parent TASK_INTERRUPTIBLE and schedules out
→ child runs on CPU0

child _exit(42)
→ do_exit(42 << 8)
→ exit_notify sets EXIT_ZOMBIE
→ do_notify_parent calls do_notify_pidfd first
→ wake P->wait_pidfd with EPOLLIN|EPOLLRDNORM
→ CB queues I on EP.rdllist
→ eventpoll wake makes parent runnable
→ default SIGCHLD policy leaves child zombie

scheduler restores parent epoll_wait stack
→ pidfd_poll rechecks zombie child
→ report EPOLLIN|EPOLLRDNORM
→ copy {EPOLLIN,data=0x50494436}
→ level-triggered I remains ready
→ epoll_wait returns 1

parent waitid(P_PIDFD, 6, ..., WEXITED)
→ pidfd_get_pid obtains P from pidfs inode
→ verify target is effective child
→ cmpxchg EXIT_ZOMBIE -> EXIT_DEAD
→ collect exit status and accounting
→ fill SIGCHLD / CLD_EXITED / PID C / status 42
→ release_task
→ pidfs_exit stores exit metadata in P->attr
→ remove task/PID linkages
→ free_pid removes numeric PID C from namespace IDR
→ numeric PID C becomes reusable
→ pidfs inode keeps old P alive
→ waitid returns 0
```

## 当前精确状态

```text
system_state          = SYSTEM_RUNNING
runtime scenario      = pidfd exit notification and P_PIDFD reap complete
current executor      = parent
CPU                   = CPU0
CPU mode              = x86-64 CPL 3
scheduling class      = SCHED_NORMAL
parent state          = TASK_RUNNING
parent on_rq/on_cpu   = 1 / 1
epoll_wait return     = 1
event                 = EPOLLIN, data 0x50494436
waitid return         = 0
siginfo               = SIGCHLD, CLD_EXITED, pid C, status 42
child task            = reaped and absent from active process graph
numeric PID C         = removed from namespace IDR and reusable
pidfd fd 6            = open
pidfd file F6         = active
pidfs inode N         = active, i_private=P
old struct pid P      = active due pidfs references
P task linkage        = none
P attr                = exit bit set, exit_code 42 << 8
P wait_pidfd           = contains callback CB
epoll fd 7            = open
eventpoll EP          = active, refcount=2
EP.rbr                = contains I
EP.rdllist            = contains level-triggered I
EP.wq                 = empty
next pidfd poll       = EPOLLIN|EPOLLRDNORM|EPOLLHUP
filesystem I/O        = none
next entry            = unselected runtime scenario
```

## 必须保持的技术边界

1. pidfd固定`struct pid` identity，不固定可复用numeric PID。
2. 当前pidfd由pidfs inode承载，不是singleton anon inode。
3. pidfs inode `i_private=P`并持有pid reference。
4. ordinary fork后parent与child files table分离，child看不到稍后创建的fd 6/7。
5. `pidfd_prepare`在`P->wait_pidfd.lock`下确认task linkages。
6. `P->wait_pidfd`上的callback与`EP.wq`上的sleeping task waiter属于不同queue。
7. child先进入`EXIT_ZOMBIE`，再发送pidfd wake。
8. pidfd wake与SIGCHLD/`wait_chldexit`是不同通知通道。
9. epoll交付只报告readiness，不消费退出状态。
10. `waitid(P_PIDFD)`中的upid是fd number，不是numeric PID。
11. pidfd不会绕过自然parent或ptrace wait权限检查。
12. `cmpxchg(EXIT_ZOMBIE, EXIT_DEAD)`让一个waiter独占reap。
13. waitid成功返回0；PID与status通过siginfo返回。
14. `pidfs_exit`在task linkage消失前保存exit metadata。
15. reap后numeric PID可复用，open pidfd仍指向旧struct pid。
16. task linkage消失后pidfd poll增加EPOLLHUP。
17. level-triggered I仍在ready list，下一次wait会继续交付。
18. pidfs是memory pseudo filesystem，本场景没有磁盘I/O。

## 下一建议场景

优先接续post-reap pidfd HUP与最终teardown：

```text
epoll_wait(7, events2, 1, 0)
→ pidfd_poll sees no task linkage
→ return EPOLLIN|EPOLLRDNORM|EPOLLHUP
→ copy one post-reap event and return 1

epoll_ctl(7, DEL, 6, NULL)
→ remove CB from P->wait_pidfd
→ erase I and drop EP.refcount 2 -> 1

close(6)
→ release pidfs file/path/inode
→ pidfs_evict_inode put_pid(P)
→ old P and pidfs attr may reach final release

close(7)
→ empty eventpoll teardown
```

开始前核对pidfs stashed dentry prune、inode eviction、pid reference/attr free时点、post-reap HUP mask和eventpoll teardown顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
