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
```

十二个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve、child exit + parent wait4 reap、ext4 create-open、首次delalloc write + fsync、open-unlinked final close、自然到期nanosleep、SIGUSR1中断nanosleep + rt_sigreturn，以及anonymous pipe blocking read + writer wakeup。

最新三章：

- `LK-PIPE-119`：pipe2() 怎样建立匿名管道并发布 fd 6/7？
- `LK-PIPE-120`：空管道 read() 怎样进入 exclusive wait queue 并阻塞？
- `LK-PIPE-121`：pipe write() 怎样唤醒reader并让 read() 返回5？

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

## 已完成 anonymous pipe 固定场景

```text
runtime relation = independent scenario
CPUs online      = CPU0 only
process          = parent + helper threads in one TGID
files table      = shared through CLONE_FILES
scheduler        = both SCHED_NORMAL
occupied fds     = 0..5
pipe call        = pipe2(pipefd, O_CLOEXEC)
returned fds     = read fd 6, write fd 7
pipe mode        = blocking stream, no O_NONBLOCK/O_DIRECT/watch queue
page size        = 4096
ring             = 16 slots / 65536 bytes
endpoints        = readers=1, writers=1, files=2
reader call      = parent read(6, buf, 5)
writer call      = helper write(7, "hello", 5)
signal state     = none; no SIGPIPE
allocation       = first anonymous page Q succeeds
scheduler order  = parent blocks, helper writes and blocks, parent resumes
failure policy   = no fd/inode/page/copy/waitqueue/scheduler failure
```

## 已执行控制流

```text
parent pipe2(pipefd, O_CLOEXEC)
→ __x64_sys_pipe2 / do_pipe2
→ create pipefs pseudo inode
→ alloc pipe_inode_info and 16 pipe_buffer slots
→ initialize rd_wait/wr_wait/mutex
→ readers=1, writers=1, files=2
→ create read/write struct file objects using pipeanon_fops
→ reserve fd 6/7 with close-on-exec
→ copy {6,7} to userspace
→ fd_install both ends
→ pipe2 returns 0

parent read(6, buf, 5)
→ ksys_read / vfs_read / anon_pipe_read
→ pipe empty, writers=1
→ unlock pipe mutex
→ wait_event_interruptible_exclusive(rd_wait, pipe_readable)
→ parent WQ_FLAG_EXCLUSIVE + TASK_INTERRUPTIBLE
→ schedule out and switch to helper

helper write(7, "hello", 5)
→ ksys_write / vfs_write / anon_pipe_write
→ alloc anonymous page Q
→ copy 5 bytes into Q
→ head 0 -> 1
→ slot 0 = page Q, offset 0, len 5, CAN_MERGE
→ wake_up_interruptible_sync_poll(rd_wait)
→ parent TASK_RUNNING and enqueued
→ write returns 5
→ helper blocks outside pipe

scheduler restores parent original read stack
→ wait condition true
→ finish_wait removes reader entry
→ copy 5 bytes from Q to parent user buffer
→ buffer fully consumed
→ cache Q in pipe->tmp_page[0]
→ tail 0 -> 1
→ head=tail=1, occupancy=0
→ read returns 5
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = anonymous pipe blocking read/writer wakeup complete
current executor   = parent
CPU                = CPU0
CPU mode           = x86-64 CPL 3
scheduling class   = SCHED_NORMAL
parent state       = TASK_RUNNING
parent on_rq       = 1
parent on_cpu      = 1
read return        = 5
user buffer        = "hello"
helper             = write returned 5; blocked outside pipe
fd 6               = open read end, close-on-exec
fd 7               = open write end, close-on-exec
pipe files         = 2
pipe readers       = 1
pipe writers       = 1
ring capacity      = 16 slots / 65536 bytes
head/tail          = 1/1
occupancy          = 0
active buffers     = 0
tmp_page[0]        = anonymous page Q
tmp_page[1]        = NULL
wait entries       = none from this operation
pipe mutex         = unlocked
filesystem I/O     = none
next entry         = unselected runtime scenario
```

## 必须保持的技术边界

1. anonymous pipe使用pipefs pseudo inode，不触发磁盘filesystem或block I/O。
2. ring创建时只分配`pipe_buffer` metadata；data page按write需要分配。
3. read/write end是两个`struct file`，共享一个`pipe_inode_info`。
4. `readers/writers`记录open endpoint数量，不是正在syscall的线程数量。
5. pipe是stream，file position无普通文件语义。
6. 空pipe且writers存在会阻塞；writers为0才返回EOF。
7. reader释放pipe mutex后，以exclusive TASK_INTERRUPTIBLE entry加入`rd_wait`。
8. wakeup只让reader runnable；`WF_SYNC`不是直接handoff。
9. sleeping reader恢复原kernel stack，不重新进入syscall入口。
10. 5-byte write产生一个anonymous `PIPE_BUF_FLAG_CAN_MERGE` buffer。
11. 完全消费后tail推进，pipe重新empty。
12. page count允许时，released page缓存到`tmp_page[]`而非立即归还buddy。
13. pipe empty不等于pipe释放；fd 6/7仍持有对象。

## 下一建议场景

优先候选是pipe write-end关闭、EOF与final free：

```text
close(7)
→ remove shared fd 7
→ pipe_release writers 1 -> 0
→ wake rd_wait
→ read(6, buf, 5) on empty pipe
→ head==tail and writers==0
→ return 0 EOF without sleeping
→ close(6)
→ readers 1 -> 0, files 1 -> 0
→ free tmp_page Q, ring, pipe_inode_info and pseudo inode
```

开始前固定close执行线程、共享fd table影响、是否存在sleeping reader、fput执行上下文与final inode/file reference顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
