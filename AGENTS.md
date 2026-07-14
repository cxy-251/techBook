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
```

十个运行期实验已闭环：cold read、O_SYNC write、fork、child COW write fault、static ELF execve、child exit + parent wait4 reap、ext4 openat create-open、新文件首次delalloc write + fsync、open-unlinked文件final close与回收、monotonic nanosleep + hrtimer/APIC/scheduler wakeup。

最新三章：

- `LK-SLEEP-113`：clock_nanosleep() 怎样建立 hrtimer 并让 parent 阻塞？
- `LK-SLEEP-114`：local APIC timer interrupt 怎样运行 hrtimer callback 并唤醒 parent？
- `LK-SLEEP-115`：scheduler 怎样恢复 parent，并让 clock_nanosleep() 返回 0？

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

## 已完成 nanosleep 固定场景

```text
current task       = parent, SCHED_NORMAL
userspace call     = clock_nanosleep(CLOCK_MONOTONIC, 0, {0,10ms}, NULL)
CPUs online        = CPU0 only
timer slack        = 0 ns
hrtimer mode       = high-resolution hard relative CLOCK_MONOTONIC
clockevent         = CPU0 lapic-deadline one-shot
runnable peers     = none; idle/0 only while parent sleeps
signal/freezer     = none
migration/hotplug  = none
delivery           = first local APIC interrupt at or after expiry
failure policy     = no copy, validation, timer or scheduler failure
```

## 已执行控制流

```text
clock_nanosleep
→ __x64_sys_clock_nanosleep
→ get_timespec64 / validate
→ common_nsleep_timens
→ hrtimer_nanosleep(HRTIMER_MODE_REL)
→ on-stack hrtimer_sleeper
→ callback hrtimer_wakeup; t.task=parent
→ expiry E=now+10ms; slack=0
→ enqueue CPU0 monotonic hrtimer
→ program lapic TSC deadline
→ parent TASK_INTERRUPTIBLE|TASK_FREEZABLE
→ schedule / __schedule
→ dequeue parent; switch to idle/0
→ LOCAL_TIMER_VECTOR
→ sysvec_apic_timer_interrupt
→ local_apic_timer_interrupt
→ hrtimer_interrupt
→ remove timer / run hrtimer_wakeup
→ t.task=NULL
→ wake_up_process / try_to_wake_up
→ parent TASK_RUNNING on CPU0 runqueue
→ reschedule idle/0 to parent
→ parent resumes original schedule()
→ hrtimer_cancel sees inactive timer
→ do_nanosleep returns 0
→ destroy_hrtimer_on_stack
→ userspace RAX=0
```

## 当前精确状态

```text
system_state       = SYSTEM_RUNNING
runtime scenario   = monotonic nanosleep complete
current executor   = parent
CPU                 = CPU0
CPU mode            = x86-64 CPL 3
scheduling class    = SCHED_NORMAL
parent state        = TASK_RUNNING
parent on_rq        = 1
parent on_cpu       = 1
syscall return      = 0
requested interval  = 10 ms monotonic
elapsed semantics   = not earlier than 10 ms
hrtimer object      = destroyed on stack
hrtimer queue       = no timer from this sleep
APIC deadline       = consumed
signal/restart      = none
next entry          = unselected runtime scenario
```

## 必须保持的技术边界

1. `clock_nanosleep` 使用hrtimer，不使用timer wheel。
2. relative interval在enqueue时转换成absolute monotonic expiry。
3. timer slack为0时soft expiry与hard expiry一致。
4. 设置task state不等于已sleep；scheduler context switch才让task离开CPU。
5. hrtimer callback运行时`current`仍是被interrupt打断的idle task。
6. `wake_up_process`只把task放回runqueue，不直接恢复其调用栈。
7. parent从原`schedule()`调用点继续执行。
8. `t.task=NULL`表示timer自然到期。
9. nanosleep保证不早于期限，不保证精确在期限瞬间返回。
10. 无signal时不进入restart block或remaining-time copyout。

## 下一建议场景

优先候选是被`SIGUSR1`中断的relative nanosleep：

```text
parent clock_nanosleep(..., &remaining)
→ helper sends SIGUSR1 before expiry
→ signal_wake_up / try_to_wake_up
→ parent resumes do_nanosleep
→ cancel still-active hrtimer
→ calculate and copy remaining time
→ syscall exit builds rt signal frame
→ userspace handler
→ rt_sigreturn restores context
```

开始前固定helper task、signal action、SA_RESTART、send time、remaining time和调度顺序。

## 连续叙事与流程

每段交代当前执行者、CPU mode、关键对象、锁/引用、状态变化、下一入口和固定源码依据。场景结束后不要虚构用户程序下一条动作。

继续时依次读取：`AGENTS.md`、`project/STATE.rst`、章节目录、已完成章节、manifest和main最近提交。读取fixed source，写三章，随后同步目录、README、manifest、STATE与AGENTS。
