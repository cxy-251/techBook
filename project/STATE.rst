项目状态
========

最后更新
--------

2026-07-14

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

::

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

最新三章：

#. ``LK-SLEEP-113``：clock_nanosleep() 怎样建立 hrtimer 并让 parent 阻塞？
#. ``LK-SLEEP-114``：local APIC timer interrupt 怎样运行 hrtimer callback 并唤醒 parent？
#. ``LK-SLEEP-115``：scheduler 怎样恢复 parent，并让 clock_nanosleep() 返回 0？

固定来源
--------

::

   x86-64
   → QEMU q35 @ a759542a2c62f0fd3b65f5a66ad9868201014669
   → SeaBIOS @ c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   → GNU GRUB 2.14 i386-pc @ d38d6a1a9b79427848976f53d474392cd29c2a71
   → Linux 7.2-rc1 @ 7404ce51637231382873d0b55edabc2f3b841a9d

已完成的运行期实验
------------------

#. cold-miss ``read(fd, buf, 4096)``；
#. ext4 ``O_SYNC write(fd, buf, 4096)``；
#. native x86-64 ``fork()``；
#. child private-anonymous COW write fault；
#. child static ELF ``execve()``；
#. child ``_exit(42)`` 与 parent ``wait4()`` 回收；
#. ext4 ``openat(O_CREAT|O_EXCL)``；
#. 新文件首次delalloc buffered write与显式 ``fsync``；
#. open-unlinked ext4文件的final close与inode/extent回收；
#. monotonic ``clock_nanosleep``、hrtimer expiry与scheduler wakeup。

本批固定场景
------------

::

   current task       = parent, SCHED_NORMAL
   userspace call     = clock_nanosleep(CLOCK_MONOTONIC, 0, {0,10ms}, NULL)
   CPUs online        = CPU0 only
   timer slack        = 0 ns
   hrtimer mode       = high-resolution, hard expiry, relative monotonic
   clockevent         = CPU0 local APIC TSC-deadline one-shot
   runnable peers     = none; idle/0 is the only task while parent sleeps
   signal/freezer     = none
   migration/hotplug  = none
   delivery           = first local timer interrupt at or after expiry
   failure policy     = no copy, validation, timer or scheduler failure

完整控制流
----------

::

   clock_nanosleep(CLOCK_MONOTONIC, 0, {0,10ms}, NULL)
   → entry_SYSCALL_64 / __x64_sys_clock_nanosleep
   → get_timespec64 / validate
   → clock_monotonic.nsleep
   → common_nsleep_timens
   → hrtimer_nanosleep(HRTIMER_MODE_REL)
   → hrtimer_setup_sleeper_on_stack
   → callback = hrtimer_wakeup; t.task = parent
   → timer slack 0, relative expiry converted to E = now + 10ms
   → enqueue on CPU0 monotonic hrtimer base
   → program lapic-deadline clockevent
   → parent state TASK_INTERRUPTIBLE | TASK_FREEZABLE
   → schedule / __schedule
   → dequeue parent and context-switch to idle/0
   → TSC reaches deadline
   → LOCAL_TIMER_VECTOR
   → sysvec_apic_timer_interrupt
   → local_apic_timer_interrupt
   → hrtimer_interrupt
   → remove expired timer and run hrtimer_wakeup
   → t.task = NULL
   → wake_up_process / try_to_wake_up
   → parent TASK_RUNNING and enqueued on CPU0
   → interrupt exit requests reschedule
   → scheduler switches idle/0 to parent
   → parent resumes original schedule() call
   → hrtimer_cancel sees inactive timer
   → do_nanosleep returns 0
   → destroy_hrtimer_on_stack
   → clock_nanosleep returns userspace RAX=0

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* scheduling class：``SCHED_NORMAL``；
* parent state：``TASK_RUNNING``；
* parent ``on_rq``：1；
* parent ``on_cpu``：1；
* syscall result/RAX：0；
* userspace RIP：原 ``clock_nanosleep`` 后的下一条指令；
* requested interval：10 ms monotonic；
* elapsed semantics：不早于10 ms；
* sleeper task pointer：已在callback中清空；
* hrtimer object：已destroy on stack；
* hrtimer queue：无本次timer；
* local APIC deadline：本次event已消费；
* signal/restart：未发生；
* remaining-time copyout：未发生；
* next runtime scenario：unselected。

关键边界
--------

#. ``clock_nanosleep`` 使用hrtimer，不使用timer wheel。
#. relative时间在enqueue时转换为monotonic absolute expiry。
#. timer slack为0时soft expiry与hard expiry一致。
#. ``TASK_INTERRUPTIBLE`` 只是state；真正睡眠发生在scheduler切走task时。
#. timer callback运行时 ``current`` 仍是被interrupt打断的idle task。
#. wakeup只把parent变成runnable，scheduler随后恢复其原kernel stack。
#. ``t.task=NULL`` 表示hrtimer自然到期。
#. nanosleep保证不早于期限，不保证精确在期限瞬间返回。

下一任务
--------

当前没有已选定场景。优先候选是一次被 ``SIGUSR1`` 中断的relative nanosleep，用来继续追踪signal wakeup、remaining time、signal frame与 ``rt_sigreturn``：

::

   parent clock_nanosleep(..., &remaining)
   → helper sends SIGUSR1 before expiry
   → signal_wake_up / try_to_wake_up
   → do_nanosleep cancels active hrtimer
   → copy remaining time
   → syscall exit builds rt signal frame
   → userspace signal handler
   → rt_sigreturn restores interrupted context

开始前必须固定helper来源、signal disposition、SA_RESTART、发送时刻、remaining-time值和调度顺序。
