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
```

十五个运行期实验已闭环：cold read、O_SYNC write、fork、child COW、static ELF exec、exit/wait、ext4 create、delalloc+fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep、anonymous pipe读写与teardown、private futex wait/wake，以及eventfd counter blocking read/writer wakeup。

最新三章：

- `LK-EVENTFD-128`：eventfd2() 怎样建立counter并发布fd 6？
- `LK-EVENTFD-129`：eventfd read() 怎样在counter为0时进入locked wait queue？
- `LK-EVENTFD-130`：eventfd write() 怎样唤醒reader并让read()返回counter？

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

## 已完成 eventfd 固定场景

```text
runtime relation = independent scenario
CPUs online      = CPU0 only
process          = parent + helper threads in one TGID
files table      = shared through CLONE_FILES
scheduler        = both SCHED_NORMAL
occupied fds     = 0..5
create call      = eventfd2(0, EFD_CLOEXEC)
returned fd      = 6
file mode        = O_RDWR, blocking, close-on-exec
semaphore mode   = disabled
initial count    = 0
reader call      = parent read(6, &value, 8)
writer call      = helper write(6, &three, 8), three=3
wait entry       = non-exclusive TASK_INTERRUPTIBLE
signal state     = none
scheduler order  = parent blocks, helper writes and blocks, parent resumes
failure policy   = no allocation/fd/copy/signal/scheduler failure
```

## 已执行控制流

```text
parent eventfd2(0, EFD_CLOEXEC)
→ __x64_sys_eventfd2 / do_eventfd
→ allocate eventfd_ctx E
→ initialize kref, waitqueue and count=0
→ anon_inode_getfile_fmode with eventfd_fops and O_RDWR
→ reserve/publish shared fd 6 with close-on-exec
→ parent returns 6

parent read(6, &value, 8)
→ eventfd_read
→ lock E.wqh.lock with IRQ disabled
→ E.count==0 and blocking mode
→ wait_event_interruptible_locked_irq
→ non-exclusive stack wait entry
→ parent TASK_INTERRUPTIBLE
→ unlock+enable IRQ and schedule out
→ helper runs on CPU0

helper write(6, &three, 8)
→ eventfd_write
→ copy u64 3 from userspace
→ lock E.wqh.lock
→ E.count 0 -> 3
→ wake_up_locked_poll(..., EPOLLIN)
→ parent TASK_RUNNING and enqueued
→ helper write returns 8
→ helper blocks outside eventfd

scheduler restores parent original read stack
→ reacquire E.wqh.lock
→ count condition true
→ remove parent wait entry
→ non-semaphore eventfd_ctx_do_read returns full count 3
→ E.count 3 -> 0
→ unlock E.wqh.lock
→ copy u64 3 to userspace
→ parent read returns 8
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = eventfd blocking read/writer wakeup complete
current executor   = parent
CPU                = CPU0
CPU mode           = x86-64 CPL 3
scheduling class   = SCHED_NORMAL
parent state       = TASK_RUNNING
parent on_rq       = 1
parent on_cpu      = 1
read return        = 8
user value         = 3
helper write return= 8
helper             = blocked outside eventfd
fd 6               = open O_RDWR, blocking, close-on-exec
eventfd ctx E      = active
E.count            = 0
semaphore mode     = disabled
wait entries       = none from this operation
E.wqh.lock         = unlocked
anon-inode file    = active
filesystem I/O     = none
next entry         = unselected runtime scenario
```

## 必须保持的技术边界

1. eventfd创建一个`O_RDWR` fd，不创建read/write两个endpoint。
2. `eventfd_ctx.count`与wait queue由`ctx->wqh.lock`共同保护。
3. `EFD_CLOEXEC`落实到fdtable bitmap，不等于`O_NONBLOCK`。
4. read和write都要求用户buffer正好或至少覆盖一个8字节`u64`。
5. count为0且blocking时，reader进入non-exclusive locked wait。
6. `do_wait_intr_irq`发布wait entry、设置`TASK_INTERRUPTIBLE`、释放锁和IRQ后才schedule。
7. writer在锁内先修改count，再wake reader。
8. wake只把reader变成runnable，不直接完成read。
9. reader恢复原kernel stack并重新取得waitqueue lock。
10. 非semaphore模式一次read取得整个counter并清零。
11. read返回8表示字节数，counter值3通过用户buffer输出。
12. read完成后fd和ctx仍存在；只有final close才进入`eventfd_release`。
13. anon-inode eventfd不产生磁盘I/O、journal或writeback。

## 下一建议场景

优先候选是eventfd final close：

```text
parent close(6)
→ remove shared fd 6
→ fput_close_sync / final __fput
→ eventfd_release
→ wake poll waiters with EPOLLHUP
→ eventfd_ctx_put
→ kref reaches zero
→ free eventfd id and eventfd_ctx
→ release anon-inode file/path
```

开始前固定是否存在poll/epoll引用、额外eventfd ctx引用、close执行线程、waiter状态以及final file/path引用顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
