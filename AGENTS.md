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
```

十一个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve、child exit + parent wait4 reap、ext4 openat create-open、新文件首次delalloc write + fsync、open-unlinked文件final close与回收、自然到期monotonic nanosleep，以及SIGUSR1中断nanosleep + rt_sigreturn。

最新三章：

- `LK-SIGNAL-116`：tgkill() 怎样排入 SIGUSR1 并唤醒 nanosleep 中的 parent？
- `LK-SIGNAL-117`：parent 怎样取消 hrtimer、写回 remaining 并进入 SIGUSR1 handler？
- `LK-SIGNAL-118`：rt_sigreturn() 怎样恢复被 SIGUSR1 中断的 clock_nanosleep 上下文？

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

## 已完成 interrupted nanosleep 固定场景

```text
parent             = single-threaded SCHED_NORMAL, TGID=TID=P
helper             = separate same-UID process H
CPUs online        = CPU0 only
parent call        = clock_nanosleep(CLOCK_MONOTONIC, 0, {0,10ms}, &remaining)
timer slack        = 0 ns
expiry             = E=T0+10ms
signal send        = tgkill(P,P,SIGUSR1) at T0+4ms
handler flags       = SA_SIGINFO | SA_RESTORER
absent flags        = SA_RESTART | SA_NODEFER | SA_ONSTACK
initial signal mask = SIGUSR1 unblocked, no other pending signal
scheduling          = helper blocks after send; parent resumes before E
failure policy      = no permission/copy/frame/FPU/timer/scheduler failure
```

## 已执行控制流

```text
parent relative clock_nanosleep
→ queue on-stack CPU0 monotonic hrtimer
→ parent TASK_INTERRUPTIBLE|TASK_FREEZABLE
→ context switch to helper

helper tgkill(P,P,SIGUSR1)
→ do_tkill / do_send_specific
→ SI_TKILL siginfo, si_pid=H
→ parent private pending queue
→ set TIF_SIGPENDING
→ signal_wake_up_state / try_to_wake_up
→ parent TASK_RUNNING on CPU0 runqueue
→ helper blocks

scheduler restores parent original do_nanosleep stack
→ hrtimer_cancel removes still-active timer
→ callback never ran, so t.task remains parent
→ signal_pending ends sleep loop
→ calculate remaining = E - actual cancel time
→ 0 < remaining < 6ms
→ put_timespec64
→ -ERESTART_RESTARTBLOCK
→ save absolute restart expiry E
→ destroy hrtimer on stack

exit_to_user_mode_loop sees TIF_SIGPENDING
→ get_signal dequeues SIGUSR1
→ handle_signal changes restart-block error to -EINTR
→ x64_setup_rt_frame on normal user stack
→ save post-SYSCALL RIP, RAX=-EINTR, old RSP/mask/FPU
→ handler args in RDI/RSI/RDX
→ enter CPL3 sigusr1_handler

handler RET
→ sa_restorer / __restore_rt
→ __x64_sys_rt_sigreturn
→ restore signal mask and altstack state
→ restore general registers and FPU/XSAVE
→ restart_block.fn=do_no_restart_syscall
→ orig_ax=-1
→ CPL3 at original post-SYSCALL RIP with raw RAX=-EINTR
```

## 当前精确状态

```text
system_state        = SYSTEM_RUNNING
runtime scenario    = SIGUSR1-interrupted relative nanosleep complete
current executor    = parent
CPU                 = CPU0
CPU mode            = x86-64 CPL 3
scheduling class    = SCHED_NORMAL
parent state        = TASK_RUNNING
parent on_rq        = 1
parent on_cpu       = 1
current user RIP    = original clock_nanosleep post-SYSCALL instruction
raw syscall result  = -EINTR
libc-visible result = usually positive EINTR
remaining           = positive, 0 < remaining < 6ms
signal info         = SIGUSR1 / SI_TKILL / si_pid=H
handler             = completed and returned normally
signal mask         = restored; SIGUSR1 unblocked
pending signal      = consumed; no other pending signal
TIF_SIGPENDING      = clear
rt signal frame     = inactive
user RSP            = restored
FPU/XSAVE            = restored
restart block       = do_no_restart_syscall
orig_ax             = -1
sleep hrtimer       = cancelled, dequeued, destroyed on stack
hrtimer callback    = not executed
next entry          = unselected runtime scenario
```

## 必须保持的技术边界

1. `tgkill`以TGID+TID定位thread，并产生`SI_TKILL`。
2. thread-directed signal进入target private pending queue。
3. signal wakeup只让task runnable，不直接运行handler。
4. parent先恢复原kernel stack，再取消still-active hrtimer。
5. callback未执行时`t.task`不会被清空。
6. remaining按实际cancel时间计算，不是精确6ms。
7. `-ERESTART_RESTARTBLOCK`在实际交付handler时无条件变成`-EINTR`。
8. `SA_RESTART`不能自动重启这一条被handler打断的clock_nanosleep。
9. signal frame保存post-SYSCALL RIP和`RAX=-EINTR`。
10. handler的普通`RET`进入`sa_restorer`，不是直接回原代码。
11. `rt_sigreturn`恢复mask、RIP/RSP、寄存器和FPU state。
12. `orig_ax=-1`与`do_no_restart_syscall`阻止旧sleep被restart。
13. signal frame结束后不再active，但kernel不会专门清零用户栈旧字节。

## 下一建议场景

优先候选是anonymous pipe阻塞read与writer wakeup：

```text
pipe2(pipefd, O_CLOEXEC)
→ allocate pipe_inode_info and read/write struct file
→ reader read(pipefd[0], buf, 5) on empty pipe
→ add reader to pipe wait queue and schedule out
→ writer write(pipefd[1], "hello", 5)
→ allocate pipe_buffer page and copy bytes
→ wake reader
→ reader consumes buffer and returns 5
```

开始前固定fd编号、pipe capacity、reader/writer数量、packet mode、signal状态、scheduler顺序与page allocation结果。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
