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
```

六个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve、child exit + parent wait4 reap。

最新三章：

- `LK-EXIT-101`：_exit(42) 怎样进入 do_exit() 并释放进程运行资源？
- `LK-EXIT-102`：exit_notify() 怎样发送 SIGCHLD、唤醒 parent 并留下 zombie？
- `LK-EXIT-103`：parent 的 wait4() 怎样读取 status 并最终回收 child？

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

## 已完成 exit/wait 固定场景

```text
parent call         = wait4(child_pid, &status, 0, &rusage)
parent state        = TASK_INTERRUPTIBLE on wait_chldexit before child exits
child call          = _exit(42)
threading           = parent and child single-threaded
children            = parent has only this child
SIGCHLD             = default; no explicit SIG_IGN or SA_NOCLDWAIT
ptrace/subreaper    = disabled
buffers             = status and rusage writable and stable
failure policy      = no signal interruption, allocation failure or copy fault
```

## 已执行控制流

```text
parent wait4
→ kernel_wait4 / do_wait
→ wait_chldexit queue
→ schedule while child remains live

child _exit(42)
→ __x64_sys_exit
→ do_exit(0x2a00)
→ synchronize_group_exit / PF_EXITING
→ finalize accounting before parent wake
→ exit_mm: current->mm = NULL / mmput
→ exit_files / exit_fs / namespace and thread cleanup
→ exit_notify
→ EXIT_ZOMBIE
→ do_notify_parent
→ SIGCHLD: CLD_EXITED, si_status=42
→ __wake_up_parent / wait_chldexit callback
→ do_task_dead / child schedules away forever

parent resumes
→ __do_wait / do_wait_pid
→ wait_consider_task
→ wait_task_zombie
→ cmpxchg EXIT_ZOMBIE to EXIT_DEAD
→ collect child accounting and rusage
→ wo_stat = 0x2a00
→ release_task
→ remove task/process/parent/PID links
→ put_user(status) / copy rusage
→ syscall return child PID
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = exit and wait4 complete
current executor   = parent
CPU mode           = x86-64 CPL 3
wait4 return       = child PID
status             = 0x2a00
WIFEXITED           = true
WEXITSTATUS         = 42
rusage              = copied to parent userspace
parent wait entry   = removed
child mm/files/fs   = released
child zombie        = consumed
child process/PID   = no longer visible
child task memory   = final release follows refcount and RCU rules
parent children     = no longer contains child
next entry          = unselected runtime scenario
```

## 必须保持的技术边界

1. `_exit(42)` 编码为raw wait status `0x2a00`。
2. child在发布zombie之前释放mm/files/fs等重资源。
3. default SIGCHLD不等于显式SIG_IGN；本场景不autoreap。
4. waitqueue wakeup与SIGCHLD生成必须分开叙述。
5. scheduler dead state、`EXIT_ZOMBIE` 和 `EXIT_DEAD` 是不同阶段。
6. `wait4` 返回child PID，status通过pointer写回。
7. `cmpxchg(EXIT_ZOMBIE, EXIT_DEAD)`赋予唯一reaping ownership。
8. `release_task`删除process/PID关系；最终task_struct free可能由RCU延迟。

## 下一建议场景

当前未选择。优先从以下独立主线中选择一条并固定条件：

```text
anonymous mmap → demand-zero fault → reclaim → swap
socket → TCP connect/send/receive
scheduler timer interrupt → preemption → context switch
openat → pathname walk → dentry/inode cache
```

不同运行期实验不是自动连续时间线。开始前固定用户态入口、对象状态、cache状态、并发关系与失败策略。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
