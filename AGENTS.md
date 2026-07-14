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
```

十七个运行期实验已闭环：cold read、O_SYNC write、fork、child COW、static ELF exec、exit/wait、ext4 create、delalloc+fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep、anonymous pipe读写与teardown、private futex wait/wake、eventfd counter read/wake、eventfd final close，以及eventfd level-triggered epoll wake。

最新三章：

- `LK-EPOLL-134`：epoll_ctl(ADD) 怎样把eventfd callback挂进wait queue？
- `LK-EPOLL-135`：epoll_wait() 怎样把parent挂到eventpoll自己的wait queue？
- `LK-EPOLL-136`：eventfd write怎样触发epoll callback并让epoll_wait返回1？

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

## 已完成 epoll + eventfd 固定场景

```text
runtime relation = independent scenario
CPUs online      = CPU0 only
process          = parent + helper threads in one TGID
files table      = shared through CLONE_FILES
scheduler        = both SCHED_NORMAL
occupied fds     = 0..5
eventfd call     = eventfd2(0, EFD_CLOEXEC)
eventfd fd       = 6
epoll call       = epoll_create1(EPOLL_CLOEXEC)
epoll fd         = 7
registration     = EPOLL_CTL_ADD fd 6 with EPOLLIN
stored mask      = EPOLLIN | EPOLLERR | EPOLLHUP
trigger mode     = level-triggered
event data       = 0xEFD6
EPOLLEXCLUSIVE   = disabled
EPOLLET          = disabled
EPOLLONESHOT     = disabled
parent wait      = epoll_wait(7, events, 1, -1)
helper write     = write(6, &five, 8), five=5
signal state     = none
scheduler order  = parent blocks, helper writes and blocks, parent resumes
failure policy   = no fd/quota/allocation/copy/signal/scheduler failure
```

## 已执行控制流

```text
eventfd2 -> fd 6 with eventfd_ctx E and count=0
epoll_create1 -> fd 7 with eventpoll EP
EP.rbr empty, EP.rdllist empty, EP.refcount=1

epoll_ctl(7, ADD, 6, EPOLLIN, data=0xEFD6)
→ resolve eventpoll F7 and eventfd F6
→ store EPOLLIN | EPOLLERR | EPOLLHUP
→ allocate epitem I keyed by (F6, 6)
→ attach I to F6->f_ep reverse hlist
→ insert I into EP.rbr
→ EP.refcount 1 -> 2
→ eventfd_poll with ep_ptable_queue_proc
→ allocate eppoll_entry P
→ P.wait.func = ep_poll_callback
→ add P non-exclusively to E.wqh
→ E.count=0 reports only EPOLLOUT
→ I remains off EP.rdllist
→ epoll_ctl returns 0

parent epoll_wait(7, events, 1, -1)
→ no timeout object
→ ready check false
→ stack wait entry W
→ W.func = ep_autoremove_wake_function
→ lock EP.lock
→ parent TASK_INTERRUPTIBLE
→ final ready check false
→ add W exclusively to EP.wq
→ unlock EP.lock
→ schedule out
→ helper runs

helper write(6, u64 5)
→ lock E.wqh.lock
→ E.count 0 -> 5
→ wake_up_locked_poll(E.wqh, EPOLLIN)
→ P invokes ep_poll_callback
→ lock EP.lock
→ EPOLLIN matches I interest
→ append I to EP.rdllist
→ wake EP.wq
→ W wakes parent and auto-removes
→ unlock EP.lock and E.wqh.lock
→ helper write returns 8 and blocks

parent resumes original epoll_wait stack
→ EP.rdllist available
→ ep_send_events under EP.mtx
→ move I to scan batch
→ re-poll eventfd
→ E.count=5 reports EPOLLIN | EPOLLOUT
→ mask to EPOLLIN
→ copy {EPOLLIN, data=0xEFD6}
→ level-triggered I requeued to EP.rdllist
→ epoll_wait returns 1
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = eventfd level-triggered epoll wake complete
current executor   = parent
CPU                = CPU0
CPU mode           = x86-64 CPL 3
scheduling class   = SCHED_NORMAL
parent state       = TASK_RUNNING
parent on_rq       = 1
parent on_cpu      = 1
epoll_wait return  = 1
events[0].events   = EPOLLIN
events[0].data     = 0xEFD6
helper write return= 8
helper             = blocked outside eventfd
fd 6               = open eventfd file F6
E.count            = 5
E.wqh              = contains callback entry P
fd 7               = open eventpoll file F7
EP.refcount        = 2
EP.rbr             = contains epitem I
EP.rdllist         = contains I
EP.ovflist         = EP_UNACTIVE_PTR
EP.wq              = no parent waiter
I interest         = EPOLLIN | EPOLLERR | EPOLLHUP
I data             = 0xEFD6
filesystem I/O     = none
next entry         = unselected runtime scenario
```

## 必须保持的技术边界

1. `E->wqh`与`EP->wq`是两条不同wait queue。
2. `P`是readiness callback entry，`W`才是parent task waiter。
3. `P`是non-exclusive，`W`是exclusive。
4. interest rbtree与ready list是不同集合。
5. epoll key是`(struct file *, fd)`。
6. `EPOLLERR|EPOLLHUP`由内核自动加入interest mask。
7. `epoll_ctl`通过target file的`poll_wait`安装`ep_poll_callback`。
8. count=0时eventfd只报告`EPOLLOUT`，不会让EPOLLIN item ready。
9. `epoll_wait`在`EP->lock`内设置状态、最后检查ready并入队。
10. eventfd writer先修改counter，再发出`EPOLLIN` wake。
11. callback先更新ready list，再唤醒`EP->wq`上的task。
12. parent恢复后必须重新poll watched file，再向用户复制event。
13. returned data来自注册时的event data，不是fd或counter。
14. `epoll_wait`返回1是event数量，eventfd write返回8是字节数。
15. level-triggered epoll只报告readiness，不消费eventfd counter。
16. delivery后E.count仍为5，I仍在EP.rdllist。

## 下一建议场景

优先候选是消费counter并清理level-triggered stale-ready状态：

```text
parent read(6, &value, 8)
→ E.count 5 -> 0
→ eventfd emits EPOLLOUT wake
→ EPOLLOUT does not match I interest
→ I remains on EP.rdllist from prior level delivery
parent epoll_wait(7, events, 1, 0)
→ scan I and re-poll eventfd
→ no EPOLLIN remains
→ remove I from ready list
→ return 0
```

之后继续`EPOLL_CTL_DEL`，再关闭fd 6和fd 7，释放P、I与EP。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
