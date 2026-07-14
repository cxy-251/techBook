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
```

十八个运行期实验已闭环：cold read、O_SYNC write、fork、child COW、static ELF exec、exit/wait、ext4 create、delalloc+fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep、anonymous pipe读写与teardown、private futex wait/wake、eventfd counter read/wake、eventfd final close、eventfd level-triggered epoll wake，以及eventfd/epoll stale-ready cleanup与final teardown。

最新三章：

- `LK-EPOLLCLOSE-137`：eventfd read() 怎样清零counter却暂时留下ready epitem？
- `LK-EPOLLCLOSE-138`：零超时epoll_wait() 怎样重新poll并清理stale-ready item？
- `LK-EPOLLCLOSE-139`：EPOLL_CTL_DEL与close()怎样拆除callback并释放eventfd/eventpoll？

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

## 已完成 epoll cleanup 固定场景

```text
runtime relation = continuation of LK-EPOLL-134..136
CPUs online      = CPU0 only
process          = parent + helper threads in one TGID
files table      = shared through CLONE_FILES
scheduler        = both SCHED_NORMAL
eventfd fd       = 6
epoll fd         = 7
entry count      = 5
registration     = one level-triggered EPOLLIN epitem I
stored mask      = EPOLLIN | EPOLLERR | EPOLLHUP
callback         = non-exclusive P on E.wqh
entry ready      = I on EP.rdllist
read call        = read(6, &value, 8)
stale check      = epoll_wait(7, events2, 1, 0)
delete call      = epoll_ctl(7, EPOLL_CTL_DEL, 6, NULL)
final closes     = close(6), close(7)
concurrency      = no writer/waiter/ctl/close race
failure policy   = no fd/copy/signal/VFS/slab/scheduler failure
```

## 已执行控制流

```text
read(6)
→ lock E.wqh.lock
→ consume full non-semaphore counter 5
→ E.count 5 -> 0
→ wake eventfd queue with EPOLLOUT
→ P callback ignores unmatched EPOLLOUT key
→ I remains temporarily on EP.rdllist
→ value=5 and read returns 8

epoll_wait(7, events2, 1, 0)
→ zero timeout, no sleeping
→ I makes initial ready-candidate check true
→ ep_start_scan moves I to local batch
→ re-poll eventfd with E.count=0
→ target reports EPOLLOUT only
→ interest intersection is zero
→ no event copied and I not requeued
→ EP.rdllist becomes empty
→ epoll_wait returns 0

epoll_ctl(7, DEL, 6, NULL)
→ lock EP.mtx and find I
→ remove P from E.wqh and free P
→ temporarily pin F6
→ clear F6.f_ep and remove I reverse link
→ erase I from EP.rbr
→ kfree_rcu(I)
→ EP.refcount 2 -> 1
→ epoll_ctl returns 0

close(6)
→ final __fput(F6)
→ empty eventfd HUP wake
→ E.kref 1 -> 0
→ free eventfd id, ctx, pseudo path and file
→ return 0

close(7)
→ final __fput(F7)
→ ep_eventpoll_release / ep_clear_and_put
→ empty pollwait/tree drains
→ EP.refcount 1 -> 0
→ kfree_rcu(EP)
→ free eventpoll pseudo path and file
→ return 0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = eventfd/epoll lifecycle complete
current executor   = parent
CPU                = CPU0
CPU mode           = x86-64 CPL 3
scheduling class   = SCHED_NORMAL
parent state       = TASK_RUNNING
parent on_rq       = 1
parent on_cpu      = 1
last syscall       = close(7)
last return        = 0
read return/value  = 8 / 5
zero wait return   = 0
epoll DEL return   = 0
close(6) return    = 0
fd 6               = closed and unallocated
fd 7               = closed and unallocated
callback P         = synchronously freed during DEL
eventfd F6/E       = freed
internal eventfd id= returned to eventfd_ida
epitem I           = logically dead; kfree_rcu pending/completed
eventpoll F7       = freed
eventpoll EP       = logically dead; kfree_rcu pending/completed
EP rbr/rdllist     = empty before release
singleton anon inode = active
global anon_inode_mnt = mounted
helper             = blocked outside old eventfd
filesystem I/O     = none
next entry         = unselected runtime scenario
```

## 必须保持的技术边界

1. eventfd read清除counter，不直接清理epoll ready list。
2. read发出`EPOLLOUT`，不匹配`EPOLLIN`时callback不改变ready state。
3. ready list保存candidate；交付前必须重新调用target `poll()`。
4. zero-time epoll_wait会验证现有candidate，但不会等待新事件。
5. stale-ready清理只移除ready membership，不删除registration。
6. `EPOLL_CTL_DEL`不读取用户event对象，NULL参数合法。
7. callback entry必须在epitem释放前从target wait queue移除。
8. `epi_fget`临时pin target file，排除final `__fput`竞态。
9. 最后watcher删除时`F6->f_ep=NULL`。
10. DEL移除relationship，不关闭任一fd。
11. epitem持有一个eventpoll ref，DEL使refcount 2->1。
12. `kfree_rcu(I)`和`kfree_rcu(EP)`结束合法访问，physical memory可延迟回收。
13. 显式DEL后，eventfd close的eventpoll release走空fast path。
14. eventpoll close在空RB tree上完成空drain后释放基础ref。
15. 全局singleton anon inode与anon_inodefs mount继续存在。

## 下一建议场景

优先候选是`signalfd4`与epoll组合：

```text
block SIGUSR1 in parent/helper
→ signalfd4(-1, mask(SIGUSR1), SFD_CLOEXEC) -> fd 6
→ epoll_create1(EPOLL_CLOEXEC) -> fd 7
→ EPOLL_CTL_ADD signalfd EPOLLIN
→ parent epoll_wait blocks
→ helper tgkill sends SIGUSR1 to parent
→ blocked signal becomes pending
→ signalfd poll callback marks epitem ready
→ epoll_wait returns EPOLLIN
→ read signalfd_siginfo consumes pending signal
```

开始前固定signal target、private/shared pending queue、thread masks、signalfd wait queue、task wake规则、epoll callback和read dequeue顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
