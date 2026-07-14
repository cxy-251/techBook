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
   LK-SIGNAL-116..LK-SIGNAL-118

最新三章：

#. ``LK-SIGNAL-116``：tgkill() 怎样排入 SIGUSR1 并唤醒 nanosleep 中的 parent？
#. ``LK-SIGNAL-117``：parent 怎样取消 hrtimer、写回 remaining 并进入 SIGUSR1 handler？
#. ``LK-SIGNAL-118``：rt_sigreturn() 怎样恢复被 SIGUSR1 中断的 clock_nanosleep 上下文？

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
#. monotonic ``clock_nanosleep`` 自然到期、hrtimer/APIC/scheduler唤醒；
#. ``SIGUSR1`` 中断relative nanosleep、remaining copyout、rt signal frame与 ``rt_sigreturn``。

本批固定场景
------------

::

   parent             = single-threaded SCHED_NORMAL task, TGID=TID=P
   helper             = separate same-UID process H
   CPUs online        = CPU0 only
   parent call        = clock_nanosleep(CLOCK_MONOTONIC, 0, {0,10ms}, &remaining)
   timer slack        = 0 ns
   timer expiry       = E = T0 + 10 ms
   signal send        = helper tgkill(P, P, SIGUSR1) at Ts = T0 + 4 ms
   handler            = SA_SIGINFO | SA_RESTORER
   absent flags       = SA_RESTART, SA_NODEFER, SA_ONSTACK
   signal mask        = SIGUSR1 initially unblocked; no other pending signal
   scheduling         = helper blocks immediately after tgkill; parent resumes before E
   failure policy     = no permission, copy, frame, FPU, timer or scheduler failure

完整控制流
----------

::

   parent clock_nanosleep(..., &remaining)
   → hrtimer_nanosleep / do_nanosleep
   → on-stack hrtimer_sleeper queued on CPU0 monotonic base
   → parent TASK_INTERRUPTIBLE|TASK_FREEZABLE
   → scheduler switches parent to helper

   helper tgkill(P, P, SIGUSR1)
   → __x64_sys_tgkill
   → do_tkill / do_send_specific
   → SI_TKILL siginfo with si_pid=H
   → send to parent private pending queue
   → set TIF_SIGPENDING
   → wake_up_state(TASK_INTERRUPTIBLE)
   → try_to_wake_up
   → parent TASK_RUNNING and enqueued on CPU0
   → helper blocks

   scheduler restores parent original kernel stack
   → schedule returns inside do_nanosleep
   → hrtimer_cancel removes still-active timer
   → t.task remains parent because callback never ran
   → signal_pending causes loop exit
   → remaining = E - actual cancel time
   → 0 < remaining < 6 ms
   → put_timespec64(&remaining)
   → nanosleep_copyout returns -ERESTART_RESTARTBLOCK
   → save restart expiry E
   → destroy_hrtimer_on_stack

   syscall exit sees TIF_SIGPENDING
   → get_signal dequeues SIGUSR1
   → handle_signal converts -ERESTART_RESTARTBLOCK to -EINTR
   → x64_setup_rt_frame on normal user stack
   → save RIP after original SYSCALL, RAX=-EINTR, old RSP/mask/FPU
   → handler ABI: RDI=SIGUSR1, RSI=&siginfo, RDX=&ucontext
   → return to CPL3 at sigusr1_handler

   handler returns
   → frame->pretcode / __restore_rt
   → __x64_sys_rt_sigreturn
   → restore blocked mask and altstack state
   → restore general registers and FPU/XSAVE state
   → restart_block.fn = do_no_restart_syscall
   → orig_ax = -1
   → return to original user RIP with raw RAX=-EINTR

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
* current user RIP：原 ``clock_nanosleep`` syscall后的下一条指令；
* raw syscall result/RAX：``-EINTR``；
* libc-visible result：通常为正error number ``EINTR``；
* ``remaining``：有效正值，``0 < remaining < 6 ms``；
* delivered signal：``SIGUSR1``，``SI_TKILL``，``si_pid=H``；
* handler：已执行并正常返回；
* signal mask：恢复到handler前状态，``SIGUSR1`` 未屏蔽；
* private pending queue：本次signal已dequeue；
* ``TIF_SIGPENDING``：无其他signal时已清除；
* rt signal frame：不再active；
* user RSP：恢复；
* FPU/XSAVE state：恢复；
* restart block：``do_no_restart_syscall``；
* ``orig_ax``：``-1``；
* sleep hrtimer：已取消、从queue移除并destroy on stack；
* hrtimer callback：未执行；
* original APIC deadline E：不再属于本次sleep；
* next runtime scenario：unselected。

关键边界
--------

#. ``tgkill`` 生成thread-directed ``SI_TKILL`` 并进入target private pending queue。
#. signal wakeup设置 ``TIF_SIGPENDING`` 并唤醒 ``TASK_INTERRUPTIBLE`` task，不直接运行handler。
#. parent恢复原kernel stack后才取消sleep hrtimer。
#. callback未执行时 ``t.task`` 仍指向parent；自然到期才会清空它。
#. remaining按实际cancel时间计算，不能写成精确6 ms。
#. ``-ERESTART_RESTARTBLOCK`` 在交付handler时无条件转成 ``-EINTR``，不受 ``SA_RESTART`` 控制。
#. rt signal frame保存转换后的RAX与原syscall后的RIP。
#. handler普通return先进入 ``sa_restorer``。
#. ``rt_sigreturn`` 恢复mask、RSP/RIP、通用寄存器和FPU state。
#. ``orig_ax=-1`` 与 ``do_no_restart_syscall`` 阻止旧sleep被错误restart。

下一任务
--------

当前没有已选定场景。优先候选是anonymous pipe的阻塞read与writer wakeup：

::

   pipe2(pipefd, O_CLOEXEC)
   → allocate pipe_inode_info and two struct file objects
   → reader read(pipefd[0], buf, 5) on empty pipe
   → reader joins pipe wait queue and schedules out
   → writer write(pipefd[1], "hello", 5)
   → allocate pipe_buffer page and copy bytes
   → wake reader
   → reader consumes pipe_buffer and returns 5

开始前必须固定fd编号、pipe capacity、single/multi-reader writer状态、packet mode、signal状态、scheduler顺序与page allocation结果。
