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
```

十四个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve、child exit + parent wait4 reap、ext4 create-open、首次delalloc write + fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep + rt_sigreturn、anonymous pipe blocking read + writer wakeup、pipe close + EOF + teardown，以及private futex wait/wake。

最新三章：

- `LK-FUTEX-125`：FUTEX_WAIT_PRIVATE 怎样建立private key并把parent排入hash bucket？
- `LK-FUTEX-126`：FUTEX_WAKE_PRIVATE 怎样移除waiter并把parent放回runqueue？
- `LK-FUTEX-127`：parent 被唤醒后，futex_wait 为什么返回0却不自动重读用户字？

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

## 已完成 private futex 固定场景

```text
runtime relation = independent scenario
CPUs online      = CPU0 only
threads          = parent + helper in one TGID
mm                = shared through CLONE_VM
scheduler         = both SCHED_NORMAL
user word         = aligned _Atomic uint32_t U
mapping           = resident writable private anonymous page
initial U         = 0
wait call         = futex(&U, FUTEX_WAIT_PRIVATE, 0, NULL, NULL, 0)
store             = atomic_store_explicit(&U, 1, memory_order_release)
wake call         = futex(&U, FUTEX_WAKE_PRIVATE, 1, NULL, NULL, 0)
config            = FUTEX=y, FUTEX_PRIVATE_HASH=y, BASE_SMALL=n
private hash      = 16 buckets
key waiters       = exactly one parent
signal/timeout    = none
scheduler order   = parent blocks, helper stores+wakes+blocks, parent resumes
failure policy    = no alignment/address/page/hash/scheduler failure
```

## 已执行控制流

```text
parent FUTEX_WAIT_PRIVATE expected=0
→ __x64_sys_futex / do_futex / futex_wait
→ no timeout and no hrtimer
→ futex_wait_setup
→ private key K = shared mm + page virtual base + byte offset
→ no VMA lookup, page pin, inode or physical-page key
→ select per-mm bucket H
→ H->waiters 0 -> 1 before spin_lock
→ read U under H lock
→ U == 0
→ parent TASK_INTERRUPTIBLE | TASK_FREEZABLE
→ enqueue stack futex_q in H plist
→ release H lock
→ futex_do_wait / schedule
→ parent leaves CPU0; helper runs

helper atomic_store_release(U, 1)
→ helper FUTEX_WAKE_PRIVATE nr=1
→ reconstruct same key K and bucket H
→ waiters_pending sees 1
→ lock H and match q key/bitset
→ plist_del(q)
→ H->waiters 1 -> 0
→ smp_store_release(q.lock_ptr, NULL)
→ add parent to wake_q
→ unlock H
→ wake_up_q / try_to_wake_up
→ parent TASK_RUNNING on CPU0 runqueue
→ helper returns 1 and blocks outside futex

scheduler restores parent original futex_do_wait stack
→ schedule returns
→ parent state TASK_RUNNING
→ futex_unqueue sees q.lock_ptr == NULL
→ q was already removed by waker
→ __futex_wait returns 0
→ no post-wake kernel read of U
→ parent CPL3 with RAX=0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = private futex wait/wake complete
current executor   = parent
CPU                = CPU0
CPU mode            = x86-64 CPL 3
scheduling class   = SCHED_NORMAL
parent state       = TASK_RUNNING
parent on_rq       = 1
parent on_cpu      = 1
parent wait return = 0
helper wake return = 1
helper             = blocked outside futex
user word U        = 1
kernel reread U    = none after wake
user acquire load  = not yet executed
private hash       = alive, 16 buckets
bucket H waiters   = 0
bucket H chain     = no entry from this wait
bucket H lock      = unlocked
stack futex_q      = lifetime ended
hrtimer/restart    = none
signal pending     = none
next entry         = unselected runtime scenario
```

## 必须保持的技术边界

1. `FUTEX_PRIVATE_FLAG`让key使用`mm + virtual address`，不是physical page identity。
2. private key路径不查VMA、不pin page、不引用inode。
3. bucket可容纳不同key，wake必须匹配完整key和bitset。
4. waiter先增加bucket waiter count，再获取spinlock并检查U。
5. 入队前在bucket lock内重新读取U；不匹配返回`-EWOULDBLOCK`且不睡眠。
6. parent先设置interruptible state，再公开栈上的`futex_q`。
7. task state不等于已经阻塞；context switch才使parent离开CPU。
8. ordinary FUTEX_WAKE不修改U，U=1来自helper release store。
9. waker先从plist删除q，再release-store `q.lock_ptr=NULL`。
10. scheduler wake通过wake_q在bucket lock释放后执行。
11. wake只使parent runnable，不保证立即handoff。
12. WAKE返回1是woken waiter count；WAIT返回0表示q由waker移除。
13. wait成功后kernel不会重新读取U，也不保证业务condition仍成立。
14. user code必须loop重读condition并处理spurious/competitive wake。
15. kernel barriers不替代C/C++ release/acquire；parent应以acquire load读取1。
16. `futex_q`是一次wait的栈上对象，syscall返回后结束生命周期。
17. per-mm private hash不会随单次wait结束而销毁。

## 下一建议场景

优先候选是`eventfd` counter blocking read与writer wakeup：

```text
eventfd2(0, EFD_CLOEXEC)
→ create anon_inode file and eventfd_ctx
→ parent read(eventfd, &value, 8) with counter=0
→ parent joins eventfd wait queue and schedules out
→ helper write(eventfd, value=3)
→ counter 0 -> 3 and wake reader
→ parent consumes counter and returns 8 with value=3
```

开始前固定fd编号、counter/semaphore mode、blocking flags、wait queue、scheduler顺序、signal state与file references。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
