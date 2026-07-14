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
```

十六个运行期实验已闭环：cold read、O_SYNC write、fork、child COW、static ELF exec、exit/wait、ext4 create、delalloc+fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep、anonymous pipe读写与teardown、private futex wait/wake、eventfd counter read/wake，以及eventfd final close。

最新三章：

- `LK-EVENTFDCLOSE-131`：close(6) 怎样撤销eventfd fd并同步进入最后一次__fput()？
- `LK-EVENTFDCLOSE-132`：eventfd_release() 怎样发送EPOLLHUP并释放eventfd_ctx？
- `LK-EVENTFDCLOSE-133`：__fput() 怎样释放anon-inode path并让close()返回0？

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

## 已完成 eventfd final close 固定场景

```text
runtime relation = continuation of LK-EVENTFD-128..130
CPUs online      = CPU0 only
process          = parent + helper threads in one TGID
files table      = shared through CLONE_FILES
scheduler        = both SCHED_NORMAL
close caller     = parent
close call       = close(6)
fd 6             = unique eventfd file reference
file mode        = O_RDWR, blocking, close-on-exec
eventfd count    = 0
ctx kref         = 1
wait queue       = empty
poll/epoll       = none
extra ctx refs   = none
helper           = blocked outside eventfd
failure policy   = no close/VFS/dcache/mount/allocator failure
```

## 已执行控制流

```text
parent close(6)
→ __x64_sys_close
→ file_close_fd under shared files->file_lock
→ fdt->fd[6] = NULL
→ clear open and close-on-exec bits
→ fd 6 unavailable to parent and helper
→ filp_flush returns 0
→ fput_close_sync
→ final file reference consumed
→ synchronous __fput(F)
→ eventpoll_release finds no registration
→ eventfd_release
→ wake_up_poll(E.wqh, EPOLLHUP)
→ lock and scan empty wait queue
→ zero task/callback awakened
→ eventfd_ctx_put
→ E.kref 1 -> 0
→ ida_free(E.id)
→ kfree(E)
→ fops/owner/access cleanup
→ dput per-file [eventfd] pseudo dentry
→ drop per-file singleton-inode reference
→ mntput per-file anon_inodefs mount reference
→ file_free(F)
→ close returns 0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = eventfd final close complete
current executor   = parent
CPU                = CPU0
CPU mode           = x86-64 CPL 3
scheduling class   = SCHED_NORMAL
parent state       = TASK_RUNNING
parent on_rq       = 1
parent on_cpu      = 1
close return       = 0
fd 6               = closed and unallocated
open/cloexec bit 6 = cleared
eventfd file F     = freed
eventfd ctx E      = freed
internal eventfd id= returned to eventfd_ida
HUP observers      = 0
pseudo dentry      = no active reference
singleton anon inode = active
global anon_inode_mnt = mounted
helper             = blocked outside eventfd
filesystem I/O     = none
next entry         = unselected runtime scenario
```

## 必须保持的技术边界

1. fdtable publication、file refcount、ctx kref和path refs是不同lifetime。
2. `file_close_fd`先撤销共享fd publication，不立即释放file。
3. `EFD_CLOEXEC`属于fdtable bitmap，显式close时与open bit一起清理。
4. `fput_close_sync`让最后`__fput`在close返回前执行。
5. `eventpoll_release`早于file-specific `release`。
6. `wake_up_poll(..., EPOLLHUP)`传递HUP key；空queue时没有真实observer。
7. eventfd这里使用`wake_up_poll`，不是`wake_up_pollfree`。
8. 无额外ctx引用时，`eventfd_ctx_put`使kref从1直接到0。
9. internal eventfd id与userspace fd number不是同一个编号空间。
10. `kfree(E)`之后不能访问counter、flags、id或wait queue。
11. `release`返回值不决定close结果；close retval来自`filp_flush`。
12. 普通eventfd复用singleton anon inode，不创建独立inode。
13. `dput`结束per-file pseudo dentry，不释放全局singleton inode。
14. `mntput`只归还per-file mount ref，不卸载anon_inodefs。
15. anon-inode teardown不产生磁盘I/O、journal或writeback。

## 下一建议场景

优先候选是用epoll实际观察eventfd wake：

```text
eventfd2(0, EFD_CLOEXEC) -> fd 6
epoll_create1(EPOLL_CLOEXEC) -> fd 7
epoll_ctl(7, EPOLL_CTL_ADD, 6, EPOLLIN)
→ attach epitem callback to eventfd wait queue
parent epoll_wait(7, events, 1, -1)
→ block on eventpoll wait queue
helper write(6, u64 5)
→ eventfd EPOLLIN callback marks epitem ready
→ wake parent
→ epoll_wait copies one event to userspace
```

开始前固定level/edge trigger、event data、EPOLLEXCLUSIVE、fd references、callback顺序、ready-list状态与scheduler顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
