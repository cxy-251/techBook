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
```

二十一个运行期实验已闭环：cold read、O_SYNC write、fork、child COW、static ELF exec、exit/wait、ext4 create、delalloc+fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep、anonymous pipe读写与teardown、private futex wait/wake、eventfd counter read/wake、eventfd final close、eventfd level-triggered epoll wake、eventfd/epoll cleanup、blocked SIGUSR1通过signalfd+epoll交付、signalfd/epoll cleanup，以及one-shot timerfd通过LAPIC/hrtimer/epoll交付。

最新三章：

- `LK-TIMERFD-146`：timerfd怎样建立一次性hrtimer并让parent阻塞在epoll_wait？
- `LK-TIMERFD-147`：local APIC定时器中断怎样让timerfd callback唤醒epoll_wait？
- `LK-TIMERFD-148`：parent怎样从epoll event进入timerfd read并取出expiration count？

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

## 已完成 timerfd + epoll 固定场景

```text
runtime relation = independent after LK-SIGNALFDCLOSE-145
CPUs online      = CPU0 only
process          = parent + helper threads in one TGID
files table      = shared through CLONE_FILES
scheduler        = both SCHED_NORMAL
high-res timers  = enabled
PREEMPT_RT       = disabled
clock-event      = CPU0 local APIC one-shot
timerfd call     = timerfd_create(CLOCK_MONOTONIC, TFD_CLOEXEC)
timerfd fd       = 6, blocking, close-on-exec
timer value      = relative 20ms
timer interval   = 0, one-shot
settime flags    = 0
cancel-on-set    = disabled
epoll fd         = 7, close-on-exec
registration     = level-triggered EPOLLIN
event data       = 0x71FD6
callback P       = non-exclusive on timerfd ctx T.wqh
parent wait      = epoll_wait(7, events, 1, -1)
read call        = read(6, &expirations, 8)
failure policy   = no fd/copy/allocation/timer/signal/scheduler failure
```

## 已执行控制流

```text
timerfd_create
→ allocate timerfd_ctx T
→ initialize T.wqh/cancel_lock and embedded monotonic hrtimer
→ callback = timerfd_tmrproc
→ create [timerfd] file F6
→ publish fd 6

timerfd_settime(relative 20ms, interval 0)
→ lock T.wqh
→ inactive timer cancel result 0
→ reset ticks/expired/tintv
→ convert relative value to absolute monotonic expiry
→ enqueue T.t.tmr on CPU0 hard-hrtimer base
→ reprogram LAPIC clock-event when required
→ return 0

epoll_create1 / epoll_ctl ADD
→ create EP/F7 and publish fd 7
→ allocate epitem I
→ store EPOLLIN|ERR|HUP and data 0x71FD6
→ attach I to F6 and EP.rbr
→ EP.refcount 1 -> 2
→ timerfd_poll installs callback P on T.wqh
→ ticks=0, ready list empty

parent epoll_wait
→ stack waiter W on EP.wq
→ parent TASK_INTERRUPTIBLE
→ schedule out
→ CPU0 idle

LAPIC timer deadline
→ sysvec_apic_timer_interrupt
→ local_apic_timer_interrupt
→ hrtimer_interrupt
→ remove expired T.t.tmr from CPU0 tree
→ run timerfd_tmrproc outside CPU-base lock
→ lock T.wqh
→ T.expired 0 -> 1
→ T.ticks 0 -> 1
→ EPOLLIN wake invokes P
→ P queues I on EP.rdllist
→ wake W and make parent runnable
→ W auto-removes from EP.wq
→ callback returns HRTIMER_NORESTART
→ T.t.tmr remains inactive

parent resumes epoll_wait
→ re-poll timerfd and confirm ticks=1
→ copy {EPOLLIN,data=0x71FD6}
→ level-triggered I requeued
→ epoll_wait returns 1

parent read(6, &expirations, 8)
→ timerfd_read_iter locks T.wqh
→ condition ticks!=0 already true
→ save ticks=1
→ T.expired 1 -> 0
→ T.ticks 1 -> 0
→ no periodic restart because tintv=0
→ copy u64 1
→ return 8
```

## 当前精确状态

```text
system_state          = SYSTEM_RUNNING
runtime scenario      = one-shot timerfd/epoll delivery complete
current executor      = parent
CPU                   = CPU0
CPU mode              = x86-64 CPL 3
scheduling class      = SCHED_NORMAL
parent state          = TASK_RUNNING
parent on_rq/on_cpu   = 1 / 1
helper                = blocked outside timerfd/epoll
epoll_wait return     = 1
event mask/data       = EPOLLIN / 0x71FD6
timerfd read return   = 8
userspace expirations = 1
fd 6                  = open timerfd F6
timerfd ctx T         = active
T hrtimer             = inactive, not queued
T tintv               = 0
T expired             = 0
T ticks               = 0
callback P            = attached to T.wqh
fd 7                  = open eventpoll F7
EP.refcount           = 2
EP.rbr                = contains I
EP.rdllist            = contains stale-ready I
EP.wq                 = empty
actual timerfd EPOLLIN= false
blocked masks         = parent/helper still contain SIGUSR1
pending SIGUSR1       = none
filesystem I/O        = none
next entry            = unselected runtime scenario
```

## 必须保持的技术边界

1. timerfd ctx内嵌hrtimer、ticks、expired、interval与wait queue。
2. create只初始化timer，settime才arm。
3. relative timer由hrtimer core转换成absolute monotonic expiry。
4. LAPIC clock-event产生硬件interrupt，不直接操作timerfd ctx。
5. `hrtimer_interrupt`在per-CPU base中选择到期timer。
6. callback前timer从active tree移除，并由`base->running`标记。
7. callback在CPU-base lock外运行，在`T.wqh.lock`下修改ticks。
8. target callback P和sleeping task waiter W属于不同wait queue。
9. callback只建立ready candidate，epoll交付前必须re-poll target。
10. one-shot callback返回`HRTIMER_NORESTART`。
11. epoll delivery不消费expiration count。
12. timerfd read要求至少8字节，并在锁内清零ticks/expired。
13. `tintv=0`使read不执行periodic restart。
14. timerfd read不会主动清除epoll ready-list membership。
15. read后I是stale-ready candidate，fd与registration仍active。
16. 整个场景没有磁盘I/O、journal或writeback。

## 下一建议场景

优先接续是timerfd/epoll cleanup：

```text
epoll_wait(7, events2, 1, 0)
→ timerfd_poll sees ticks=0
→ remove stale-ready I
→ return 0

epoll_ctl(7, DEL, 6, NULL)
→ remove P from T.wqh
→ erase I and kfree_rcu

close(6)
→ hrtimer_cancel sees inactive timer
→ timerfd_release kfree_rcu(T)

close(7)
→ empty eventpoll drain
→ kfree_rcu(EP)
```

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
