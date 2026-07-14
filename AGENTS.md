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
```

十九个运行期实验已闭环：cold read、O_SYNC write、fork、child COW、static ELF exec、exit/wait、ext4 create、delalloc+fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep、anonymous pipe读写与teardown、private futex wait/wake、eventfd counter read/wake、eventfd final close、eventfd level-triggered epoll wake、eventfd/epoll cleanup，以及blocked SIGUSR1通过signalfd+epoll交付。

最新三章：

- `LK-SIGNALFD-140`：signalfd4() 怎样把阻塞信号变成可poll的fd并挂进epoll？
- `LK-SIGNALFD-141`：tgkill() 怎样让blocked SIGUSR1经signalfd callback唤醒epoll_wait？
- `LK-SIGNALFD-142`：parent怎样从epoll event进入signalfd read并取出128字节siginfo？

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

## 已完成 signalfd + epoll 固定场景

```text
runtime relation = independent after LK-EPOLLCLOSE-139
CPUs online      = CPU0 only
process          = parent + helper threads in one TGID
files table      = shared through CLONE_FILES
signal state     = shared signal_struct and sighand_struct
scheduler        = both SCHED_NORMAL
blocked mask     = parent/helper both contain SIGUSR1
initial pending  = no private/shared SIGUSR1
signalfd call    = signalfd4(-1, mask(SIGUSR1), SFD_CLOEXEC)
signalfd fd      = 6, blocking
epoll call       = epoll_create1(EPOLL_CLOEXEC)
epoll fd         = 7
registration     = EPOLL_CTL_ADD fd 6 with EPOLLIN
stored mask      = EPOLLIN | EPOLLERR | EPOLLHUP
trigger mode     = level-triggered
event data       = 0x51FD6
callback P       = non-exclusive on sighand->signalfd_wqh
parent wait      = epoll_wait(7, events, 1, -1)
helper send      = tgkill(tgid, parent_tid, SIGUSR1)
parent read      = read(6, &ssi, 128)
failure policy   = no fd/copy/allocation/permission/signal/scheduler failure
```

## 已执行控制流

```text
parent/helper already block SIGUSR1

signalfd4
→ validate size/flags
→ remove SIGKILL/SIGSTOP
→ invert requested set for dequeue mask semantics
→ allocate signalfd_ctx S
→ create [signalfd] file F6
→ publish close-on-exec fd 6

epoll_create1
→ allocate eventpoll EP
→ initialize mtx/lock/wq/poll_wait/rbr/rdllist
→ publish [eventpoll] file F7 as fd 7

epoll_ctl(7, ADD, 6, EPOLLIN, data=0x51FD6)
→ allocate epitem I keyed by (F6, 6)
→ store EPOLLIN | EPOLLERR | EPOLLHUP
→ attach I to F6.f_ep and EP.rbr
→ EP.refcount 1 -> 2
→ signalfd_poll installs eppoll_entry P
→ P.wait.func = ep_poll_callback
→ add P non-exclusively to shared sighand->signalfd_wqh
→ no pending SIGUSR1, EP.rdllist remains empty

parent epoll_wait(7, events, 1, -1)
→ create stack waiter W
→ add W exclusively to EP.wq
→ parent TASK_INTERRUPTIBLE and schedules out
→ helper runs

helper tgkill(tgid, parent_tid, SIGUSR1)
→ prepare SI_TKILL info with sender TGID/UID
→ target parent private pending queue
→ allocate sigqueue Q
→ signalfd_notify before pending bit set
→ ordinary wake_up gives P a NULL poll key
→ ep_poll_callback appends I to EP.rdllist
→ wake W on EP.wq
→ parent becomes runnable and W auto-removes
→ set parent private pending SIGUSR1 bit
→ blocked PIDTYPE_PID signal performs no ordinary signal_wake_up
→ helper tgkill returns 0 and blocks

parent resumes epoll_wait
→ signalfd_poll under shared sighand siglock
→ confirm parent private pending SIGUSR1
→ copy {EPOLLIN, data=0x51FD6}
→ level-triggered I requeued to EP.rdllist
→ epoll_wait returns 1

parent read(6, &ssi, 128)
→ signalfd_dequeue removes parent private pending SIGUSR1 and Q
→ no read wait path
→ copy one 128-byte signalfd_siginfo
→ ssi_signo=SIGUSR1
→ ssi_code=SI_TKILL
→ ssi_pid=shared TGID, ssi_uid=sender UID, ssi_tid=0
→ read returns 128
→ signalfd read does not remove I from EP.rdllist
```

## 当前精确状态

```text
system_state        = SYSTEM_RUNNING
runtime scenario    = blocked SIGUSR1 signalfd+epoll delivery complete
current executor    = parent
CPU                 = CPU0
CPU mode            = x86-64 CPL 3
scheduling class    = SCHED_NORMAL
parent state        = TASK_RUNNING
parent on_rq/on_cpu = 1 / 1
helper              = blocked outside signalfd/epoll
helper tgkill return= 0
epoll_wait return   = 1
event mask/data     = EPOLLIN / 0x51FD6
signalfd read return= 128
ssi_signo/code      = SIGUSR1 / SI_TKILL
ssi_pid             = shared TGID
ssi_uid             = sender UID
ssi_tid             = 0
blocked masks       = both still contain SIGUSR1
parent private pending = no SIGUSR1
shared pending      = no SIGUSR1
sigqueue Q          = dequeued
fd 6                = open blocking signalfd F6
signalfd ctx S      = active
fd 7                = open eventpoll F7
EP.refcount         = 2
callback P          = attached to sighand->signalfd_wqh
EP.rbr              = contains I
EP.rdllist          = contains stale-ready I
EP.ovflist          = EP_UNACTIVE_PTR
EP.wq               = no parent waiter
actual EPOLLIN      = false
filesystem I/O      = none
next entry          = unselected runtime scenario
```

## 必须保持的技术边界

1. signalfd不自动block signal；blocked mask由用户程序建立。
2. `signalfd_ctx->sigmask`是用户集合的内部反转表示。
3. shared fd/sighand不等于thread-private pending queue共享。
4. callback P挂在`sighand->signalfd_wqh`，task waiter W挂在`EP->wq`。
5. P是non-exclusive，W是exclusive。
6. tgkill把signal放进parent private pending，`si_code=SI_TKILL`。
7. `SI_TKILL`的sender pid字段是TGID，不是helper TID。
8. `signalfd_notify`发生在pending bit设置之前，并使用NULL poll key。
9. NULL poll key只建立ready candidate，最终readiness必须重新poll。
10. parent通过epoll callback链唤醒，不走普通`signal_wake_up`。
11. blocked PIDTYPE_PID signal不建立用户signal frame。
12. epoll交付不消费signal，signalfd read才dequeue。
13. `signalfd_siginfo`固定为128 bytes。
14. helper使用同一fd不能读取parent private pending signal。
15. signalfd read不修改blocked mask或registration。
16. read后level-triggered I暂留ready list，等待下一次scan验证。

## 下一建议场景

优先接续是清理stale-ready并释放对象：

```text
epoll_wait(7, events, 1, 0)
→ re-poll signalfd
→ no pending SIGUSR1
→ remove stale-ready I
→ return 0

epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
→ unregister P and erase I

close(6)
→ signalfd_release frees S

close(7)
→ eventpoll release ends EP through kfree_rcu
```

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
