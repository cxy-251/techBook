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
```

十三个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve、child exit + parent wait4 reap、ext4 create-open、首次delalloc write + fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep + rt_sigreturn、anonymous pipe blocking read + writer wakeup，以及pipe write-end close + EOF + final teardown。

最新三章：

- `LK-PIPECLOSE-122`：close(7) 怎样撤销 write end 并把 writers 降为 0？
- `LK-PIPECLOSE-123`：空管道在 writers=0 时，read() 为什么直接返回 EOF？
- `LK-PIPECLOSE-124`：最后一次 close(6) 怎样释放pipe page、ring与pseudo inode？

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

## 已完成 pipe close/EOF 固定场景

```text
runtime relation  = continuation of LK-PIPE-119..121
CPUs online       = CPU0 only
process           = parent + helper threads in one TGID
files table       = shared through CLONE_FILES
scheduler         = both SCHED_NORMAL
initial fd 6      = open read end, close-on-exec
initial fd 7      = open write end, close-on-exec
initial endpoints = readers=1, writers=1, files=2
initial ring      = head=tail=1, occupancy=0
cached page       = Q in tmp_page[0]
wait queues       = no waiter
first call        = helper close(7)
second call       = parent read(6, eofbuf, 5)
eofbuf initial    = "XXXXX"
final call        = parent close(6)
extra references  = none
signal state      = none
failure policy    = no close/copy/VFS/allocator failure
```

## 已执行控制流

```text
helper close(7)
→ file_close_fd under shared files->file_lock
→ fdt->fd[7] = NULL
→ fd 7 disappears for both threads
→ filp_flush returns 0
→ fput_close_sync
→ synchronous __fput
→ pipe_release
→ writers 1 -> 0, readers stays 1
→ wake rd_wait/wr_wait because endpoint sides differ
→ no actual waiter
→ put_pipe_info files 2 -> 1
→ release write-side path and file
→ helper RAX=0

parent read(6, eofbuf, 5)
→ anon_pipe_read
→ head==tail and writers==0
→ break with ret=0
→ no wait queue entry
→ no schedule
→ no copy_page_to_iter
→ eofbuf remains "XXXXX"
→ parent RAX=0 EOF

parent close(6)
→ remove shared fd 6
→ fput_close_sync
→ synchronous __fput
→ pipe_release
→ readers 1 -> 0, writers stays 0
→ put_pipe_info files 1 -> 0
→ inode->i_pipe = NULL
→ free_pipe_info
→ release pipe page accounting
→ __free_page(Q)
→ free 16-slot ring
→ free pipe_inode_info
→ dput final pseudo dentry
→ drop pseudo inode reference
→ mntput per-file pipefs mount ref
→ free read-side file
→ parent RAX=0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = anonymous pipe EOF and final teardown complete
current executor   = parent
CPU                = CPU0
CPU mode           = x86-64 CPL 3
scheduling class   = SCHED_NORMAL
parent state       = TASK_RUNNING
parent on_rq       = 1
parent on_cpu      = 1
final close return = 0
previous EOF read  = 0
eofbuf             = "XXXXX"
fd 6               = closed
fd 7               = closed
write file         = released
read file          = released
pipe_inode_info    = freed
ring               = freed
page Q             = returned to page allocator
pseudo dentry/inode= no longer active; slab free may be RCU-deferred
global pipe_mnt    = still present
helper             = blocked outside pipe
filesystem I/O     = none
next entry         = unselected runtime scenario
```

## 必须保持的技术边界

1. `file_close_fd`先撤销共享fd publication，另一个thread也立即失去该fd。
2. fdtable slot清空不等于`pipe_release`已经运行。
3. userspace `close()`使用`fput_close_sync`，最后`__fput`在syscall返回前执行。
4. `writers`从1降到0会通知partner wait queues，即使当前没有waiter。
5. `empty && writers==0`的pipe read立即返回0 EOF。
6. EOF不会清空用户buffer，也不会自动close read endpoint。
7. pipe是stream，没有普通文件position语义。
8. `readers/writers`决定I/O语义，`files`决定`pipe_inode_info` lifetime。
9. `files==0`才进入`free_pipe_info`。
10. consumed buffer的`buf->ops`已清空，final free不会重复release page。
11. `tmp_page`中的Q在pipe销毁时才归还page allocator。
12. pipefs pseudo inode不产生磁盘I/O、journal或writeback。
13. dentry/inode memory可RCU延迟回收，但用户已不能引用。
14. final `mntput`只下降per-file引用，不卸载global pipefs。

## 下一建议场景

优先候选是private futex wait/wake：

```text
private user word = 0
parent futex(FUTEX_WAIT_PRIVATE, expected=0)
→ build private futex key
→ enqueue waiter in hash bucket
→ verify word still equals 0
→ parent TASK_INTERRUPTIBLE and schedule out
→ helper atomic_store(word, 1)
→ futex(FUTEX_WAKE_PRIVATE, 1)
→ remove one waiter and wake parent
→ parent returns 0
```

开始前固定user address、mapping、alignment、atomic store memory ordering、futex flags、hash bucket、signal state与scheduler顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
