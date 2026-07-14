第一百一十七章：parent 怎样取消 hrtimer、写回 remaining 并进入 SIGUSR1 handler？
================================================================================

上一章结束时，helper已经把 ``SIGUSR1`` 排入parent的private pending queue，并把parent重新加入CPU0 runqueue。sleep hrtimer仍然queued，hard expiry仍是：

.. code-block:: text

   E = T0 + 10 ms

当前时间约为 ``T0 + 4 ms``。helper随即阻塞，scheduler选择parent。本章结束在x86-64 signal frame已经建立，CPU返回CPL 3并开始执行用户态 ``SIGUSR1`` handler。

scheduler 怎样恢复原 nanosleep kernel stack
-------------------------------------------

CPU0执行：

.. code-block:: text

   schedule(helper)
   → __schedule
   → pick_next_task
   → context_switch(helper, parent)

parent不是从syscall入口重新开始。它恢复的是先前阻塞时保存的kernel stack：

.. code-block:: text

   hrtimer_nanosleep
   → do_nanosleep
   → schedule

``schedule()`` 返回后，parent仍位于CPL 0。此时：

.. code-block:: text

   current                  = parent
   parent.__state           = TASK_RUNNING
   parent.TIF_SIGPENDING    = 1
   SIGUSR1 pending          = true
   t.task                   = parent
   t.timer.is_queued        = true

signal handler尚未运行。内核必须先结束当前syscall的阻塞路径。

hrtimer_cancel 怎样移除尚未到期的 timer
--------------------------------------

``do_nanosleep()`` 从 ``schedule()`` 返回后立即执行：

.. code-block:: c

   hrtimer_cancel(&t->timer);

固定timer既没有到期，也没有正在运行callback。取消路径取得CPU0 hrtimer base lock，把它从monotonic timerqueue中移除：

.. code-block:: text

   hrtimer_cancel
   → hrtimer_try_to_cancel
   → remove_hrtimer
   → __remove_hrtimer
   → timerqueue_linked_del

状态变化是：

.. code-block:: text

   t.timer.is_queued = false
   t.task            = parent
   timer callback    = never executed

``t.task`` 没有被清空。只有自然到期的 ``hrtimer_wakeup()`` callback才执行：

.. code-block:: c

   t->task = NULL;

因此 ``t.task != NULL`` 是本次sleep被外部事件打断的关键证据。

删除最早timer后，hrtimer core重新计算CPU0下一次clockevent。原来为 ``E`` 编程的local APIC TSC deadline不再代表本次sleep；它会被撤销、重编程为其他event，或进入无pending event状态。

为什么 do_nanosleep 不再进入下一轮
----------------------------------

``do_nanosleep()`` 把后续mode改为absolute，然后检查loop条件：

.. code-block:: c

   while (t->task && !signal_pending(current));

当前：

.. code-block:: text

   t.task != NULL
   signal_pending(parent) == true

所以loop结束，不会重新enqueue timer。函数恢复task state：

.. code-block:: c

   __set_current_state(TASK_RUNNING);

到这里，parent已经完成scheduler层面的唤醒与timer取消，但syscall还没有决定用户可见结果。

remaining time 怎样计算
-----------------------

因为调用者提供了 ``&remaining``，syscall入口已经设置：

.. code-block:: text

   restart_block.nanosleep.type = TT_NATIVE
   restart_block.nanosleep.rmtp = &remaining

``do_nanosleep()`` 调用：

.. code-block:: c

   rem = hrtimer_expires_remaining(&t.timer);

虽然timer已经从queue移除，timer object仍保存absolute expiry ``E``。remaining按parent恢复并取消timer时的monotonic时间 ``Tc`` 计算：

.. code-block:: text

   rem = E - Tc

固定 ``Ts = T0 + 4 ms``，并保证parent在E前恢复，因此：

.. code-block:: text

   0 < rem < 6 ms

它不能被写成精确6 ms。signal发布、helper阻塞、scheduler切换和timer取消都消耗时间。

``ktime_to_timespec64()`` 把rem转成 ``timespec64``，随后：

.. code-block:: text

   nanosleep_copyout
   → put_timespec64(&rmt, &remaining)

固定copy成功。用户内存中的 ``remaining`` 现在包含正数，表示原10 ms请求中尚未睡完的部分。

内核为什么先返回 ERESTART_RESTARTBLOCK
--------------------------------------

copy完成后，``nanosleep_copyout()`` 返回：

.. code-block:: text

   -ERESTART_RESTARTBLOCK

这是内核内部的syscall restart标记，不是最终暴露给普通用户程序的errno。

``hrtimer_nanosleep()`` 看到该标记后，为relative timer保存：

.. code-block:: text

   restart_block.nanosleep.clockid = CLOCK_MONOTONIC
   restart_block.nanosleep.expires = E
   restart_block.fn                = hrtimer_nanosleep_restart

随后销毁kernel stack上的timer debug object：

.. code-block:: text

   destroy_hrtimer_on_stack(&t.timer)

注意两个不同事实：

#. timer已经取消并从queue移除；
#. restart block保存了原absolute expiry，以便“没有handler阻止restart”的其他情形使用。

本场景存在一个真正要交付的 ``SIGUSR1`` handler，因此x86 signal路径会把restart标记改成 ``-EINTR``，不会重新睡到E。

返回用户态前怎样发现 pending signal
------------------------------------

``__x64_sys_clock_nanosleep`` 把 ``-ERESTART_RESTARTBLOCK`` 留在 ``pt_regs->ax`` 后，syscall进入exit-to-user工作循环。

``parent.TIF_SIGPENDING`` 已设置，因此：

.. code-block:: text

   exit_to_user_mode_loop
   → arch_do_signal_or_restart
   → get_signal

``get_signal()`` 在parent的 ``sighand->siglock`` 下从private pending queue取出 ``SIGUSR1`` 及其siginfo：

.. code-block:: text

   signo  = SIGUSR1
   code   = SI_TKILL
   pid    = H
   uid    = helper UID

固定sigaction不是 ``SIG_IGN`` 或 ``SIG_DFL``，所以 ``get_signal()`` 返回一个可执行handler的 ``struct ksignal``。

为什么 SA_RESTART 也不能重启这次 sleep
--------------------------------------

x86 ``handle_signal()`` 检查当前来自syscall，且：

.. code-block:: text

   syscall_get_error(regs) = -ERESTART_RESTARTBLOCK

对应分支无条件执行：

.. code-block:: c

   regs->ax = -EINTR;

这一分支不读取 ``SA_RESTART``。因此即使应用错误地给handler设置 ``SA_RESTART``，``clock_nanosleep`` 的这类restart-block结果在实际交付handler时仍转换为 ``EINTR``。

固定handler本来就没有 ``SA_RESTART``，最终被signal frame保存的原syscall结果是：

.. code-block:: text

   saved RAX = -EINTR

saved RIP仍是原 ``SYSCALL`` 指令之后的用户态地址；内核没有把RIP倒退到syscall指令。

x64_setup_rt_frame 怎样组织用户栈
---------------------------------

固定handler使用：

.. code-block:: text

   sa_flags = SA_SIGINFO | SA_RESTORER
   sa_handler = sigusr1_handler
   sa_restorer = __restore_rt
   alternate signal stack = disabled

``setup_rt_frame()`` 选择 ``x64_setup_rt_frame()``。没有 ``SA_ONSTACK``，所以frame建立在parent当前普通用户栈上。

x86-64 signal frame准备包括：

#. 为128-byte red zone留出空间；
#. 为FPU/XSAVE state分配并对齐区域；
#. 分配16-byte对齐的 ``struct rt_sigframe``；
#. 保存原用户寄存器、signal mask、stack状态和FPU state；
#. 把 ``SI_TKILL`` siginfo复制到 ``frame->info``；
#. 把 ``sa_restorer`` 写入 ``frame->pretcode``。

``ucontext`` 中保存的关键原上下文为：

.. code-block:: text

   uc_mcontext.RIP = clock_nanosleep syscall后的下一条指令
   uc_mcontext.RAX = -EINTR
   uc_mcontext.RSP = signal到达前的用户RSP
   uc_sigmask      = handler进入前的signal mask

内核随后把 ``pt_regs`` 改成handler入口ABI：

.. code-block:: text

   RDI = SIGUSR1
   RSI = &frame->info
   RDX = &frame->uc
   RIP = sigusr1_handler
   RSP = frame
   RAX = 0
   CS  = __USER_CS

因为没有 ``SA_NODEFER``，``signal_delivered()`` 在handler执行期间临时屏蔽 ``SIGUSR1``，防止同一signal默认递归进入。

CPU 怎样开始用户态 handler
--------------------------

signal frame构造成功后，exit-to-user路径使用体系结构允许的安全返回机制进入CPL 3。具体使用SYSRETQ还是IRETQ取决于最终寄存器是否满足快速返回条件；本章不把它固定成唯一指令。

架构语义已经确定：

.. code-block:: text

   current = parent
   CPL     = 3
   RIP     = sigusr1_handler
   RSP     = rt_sigframe

handler第一次执行时，原 ``clock_nanosleep`` 的用户调用点还没有恢复。它被保存在rt signal frame中，等待 ``rt_sigreturn``。

当前精确状态
------------

* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* current user RIP：``sigusr1_handler``；
* handler arguments：``SIGUSR1``、``siginfo_t *``、``ucontext_t *``；
* delivered siginfo：``SI_TKILL``，``si_pid=H``；
* parent state：``TASK_RUNNING``，``on_rq=1``、``on_cpu=1``；
* sleep hrtimer：已取消并从queue移除；
* hrtimer callback：未执行；
* on-stack hrtimer object：已destroy；
* ``remaining``：已写入，满足 ``0 < remaining < 6 ms``；
* saved syscall result：``-EINTR``；
* saved user RIP：原 ``clock_nanosleep`` syscall后的下一条指令；
* rt signal frame：位于普通用户栈；
* handler期间signal mask：包含 ``SIGUSR1``；
* next user control transfer：handler正常return到 ``__restore_rt`` restorer。

关键边界
--------

#. signal唤醒后，parent先恢复原kernel stack，再处理handler。
#. ``hrtimer_cancel`` 移除未到期timer；callback没有执行，所以 ``t.task`` 不为NULL。
#. remaining按实际取消时刻计算，不能简单写成10 ms减发送时刻。
#. ``-ERESTART_RESTARTBLOCK`` 是内核内部标记，signal handler交付时转换为 ``-EINTR``。
#. 该转换不受 ``SA_RESTART`` 控制。
#. signal frame保存的是转换后的 ``RAX=-EINTR`` 与syscall后的RIP。
#. handler入口寄存器与被中断上下文不同；旧上下文位于 ``ucontext`` 中。

资料
----

* `Linux 7.2-rc1 kernel/time/posix-timers.c：clock_nanosleep restart block初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/posix-timers.c>`_
* `Linux 7.2-rc1 kernel/time/hrtimer.c：timer取消、remaining copyout与ERESTART_RESTARTBLOCK <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
* `Linux 7.2-rc1 kernel/entry/common.c：TIF_SIGPENDING与exit_to_user_mode_loop <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/entry/common.c>`_
* `Linux 7.2-rc1 kernel/signal.c：get_signal与signal mask更新 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/signal.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/signal.c：restart结果转换与setup_rt_frame <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/signal.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/signal_64.c：x64 rt signal frame布局与handler寄存器 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/signal_64.c>`_
