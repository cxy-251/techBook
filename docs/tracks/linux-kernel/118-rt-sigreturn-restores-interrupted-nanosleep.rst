第一百一十八章：rt_sigreturn() 怎样恢复被 SIGUSR1 中断的 clock_nanosleep 上下文？
================================================================================

上一章结束时，parent已经进入用户态 ``SIGUSR1`` handler。普通用户栈上保存着完整 ``rt_sigframe``，其中记录：

.. code-block:: text

   saved RIP = 原 clock_nanosleep SYSCALL 后的下一条指令
   saved RAX = -EINTR
   saved RSP = signal进入前的用户栈指针
   saved mask = handler进入前的signal mask

固定handler只记录signal已经发生，不修改 ``ucontext``、signal mask或stack：

.. code-block:: c

   static void sigusr1_handler(int sig, siginfo_t *info, void *ucontext)
   {
       observed_sigusr1 = 1;
   }

本章从handler执行开始，结束在 ``rt_sigreturn`` 恢复原用户上下文，parent继续执行 ``clock_nanosleep`` 调用之后的代码。

handler 运行时哪些状态是临时的
------------------------------

当前用户态寄存器不是原syscall返回寄存器，而是signal handler调用ABI：

.. code-block:: text

   RDI = SIGUSR1
   RSI = &frame->info
   RDX = &frame->uc
   RIP = sigusr1_handler
   RSP = frame
   RAX = 0

``frame->info`` 中保留helper产生的信息：

.. code-block:: text

   si_signo = SIGUSR1
   si_code  = SI_TKILL
   si_pid   = H
   si_uid   = helper UID

由于sigaction没有 ``SA_NODEFER``，handler运行期间 ``SIGUSR1`` 位于parent的blocked mask中。这只是delivery期间的临时mask；原mask已保存在 ``frame->uc.uc_sigmask``，稍后由 ``rt_sigreturn`` 恢复。

原sleep hrtimer已经取消并销毁。handler执行期间不存在一个继续倒计时、等待恢复的sleep timer。用户内存 ``remaining`` 已经保存打断时尚未完成的时间。

handler 的普通 return 为什么进入 restorer
-----------------------------------------

x86-64 signal ABI要求sigaction提供 ``SA_RESTORER``。建立frame时，内核已经写入：

.. code-block:: text

   frame->pretcode = sa_restorer = __restore_rt

handler入口的 ``RSP`` 指向frame开头，开头位置存放 ``pretcode``。handler执行普通 ``RET`` 时：

.. code-block:: text

   RIP ← frame->pretcode
   RSP ← frame + sizeof(unsigned long)

因此control不会直接回到原 ``clock_nanosleep`` 调用点，而是先进入用户态restorer trampoline ``__restore_rt``。

restorer通常只承担一项职责：执行native x86-64 ``rt_sigreturn`` syscall。它不应把signal frame当成普通C函数参数重新解释，也不自行逐个恢复寄存器。

rt_sigreturn 怎样重新进入内核
-----------------------------

``__restore_rt`` 执行：

.. code-block:: text

   RAX = __NR_rt_sigreturn
   SYSCALL

控制流进入：

.. code-block:: text

   entry_SYSCALL_64
   → do_syscall_64
   → __x64_sys_rt_sigreturn

此时syscall入口创建了新的kernel entry frame，但用户RSP仍指向 ``pretcode`` 之后。x86-64实现用：

.. code-block:: c

   frame = (struct rt_sigframe __user *)(regs->sp - sizeof(long));

减去一个machine word后，重新得到原 ``rt_sigframe`` 起始地址。

为什么必须先验证整个 frame
---------------------------

signal frame位于用户内存，用户程序理论上可以修改它。``rt_sigreturn`` 不能信任其中任何地址或寄存器值，因此先检查：

.. code-block:: text

   access_ok(frame, sizeof(*frame))
   → read uc_sigmask
   → read uc_flags

固定frame完整、地址有效，且handler没有篡改内容，所以不会进入 ``badframe`` / forced ``SIGSEGV`` 路径。

如果frame非法，内核不会“尽量恢复一部分”；它会通过 ``signal_fault()`` 把本次return视为坏signal frame。

signal mask 怎样恢复
--------------------

``rt_sigreturn`` 从：

.. code-block:: text

   frame->uc.uc_sigmask

取回handler进入前的mask，然后调用：

.. code-block:: c

   set_current_blocked(&set);

固定进入handler前 ``SIGUSR1`` 未屏蔽，所以恢复后：

.. code-block:: text

   SIGUSR1 blocked = false

handler期间自动加入的 ``SIGUSR1`` 屏蔽因此被撤销。当前没有第二个pending ``SIGUSR1``，不会立即发生嵌套delivery。

``restore_altstack()`` 同时恢复 ``uc_stack`` 描述。固定场景没有使用alternate signal stack，因此这里只恢复原来的disabled状态。

restore_sigcontext 怎样恢复寄存器
---------------------------------

核心步骤是：

.. code-block:: text

   restore_sigcontext(regs,
                      &frame->uc.uc_mcontext,
                      uc_flags)

它从用户frame复制并恢复通用寄存器：

.. code-block:: text

   RBX RCX RDX RSI RDI RBP
   R8..R15
   RAX RSP RIP RFLAGS
   CS SS

本场景恢复出的关键值是：

.. code-block:: text

   regs->ip = 原 clock_nanosleep SYSCALL 后的下一条指令
   regs->sp = signal进入前的用户RSP
   regs->ax = -EINTR

CS与SS会被强制为CPL 3可用selector，RFLAGS只允许恢复用户可控制的位。

为什么 orig_ax 被设成 -1
-------------------------

``restore_sigcontext()`` 还执行：

.. code-block:: c

   current->restart_block.fn = do_no_restart_syscall;
   regs->orig_ax = -1;

这是重要控制边界：

* ``restart_block.fn`` 不再允许恢复先前保存的nanosleep restart函数；
* ``orig_ax=-1`` 告诉后续syscall-exit逻辑，当前寄存器已经是一个由sigreturn恢复的用户上下文，不要把 ``rt_sigreturn`` 或旧 ``clock_nanosleep`` 当成待restart syscall。

所以 ``rt_sigreturn`` 不会再次执行10 ms sleep，也不会重新enqueue已经取消的hrtimer。

FPU 与扩展状态怎样恢复
----------------------

``restore_sigcontext()`` 最后调用FPU signal restore路径，从signal frame指向的FP/XSAVE区域恢复用户态浮点、SIMD及启用的extended state。

固定frame未被修改，恢复成功。此后handler运行期间产生的临时FPU register状态被丢弃，parent重新获得signal进入前保存的用户计算状态。

shadow stack功能若启用，也由 ``restore_signal_shadow_stack()`` 验证并恢复。固定场景没有shadow-stack错误。

rt_sigreturn 的“返回值”为什么是旧 RAX
-------------------------------------

``SYSCALL_DEFINE0(rt_sigreturn)`` 最后写作：

.. code-block:: c

   return regs->ax;

此时 ``regs->ax`` 已经从signal frame恢复为：

.. code-block:: text

   -EINTR

这里不是让用户程序返回到 ``__restore_rt`` 的下一条指令。真正的效果是：syscall exit使用已经恢复的 ``pt_regs``，返回到signal发生前保存的用户RIP和RSP。

因此control transfer是：

.. code-block:: text

   rt_sigreturn syscall exit
   → CPL 3
   → RIP = clock_nanosleep SYSCALL 后的下一条指令
   → RSP = 原用户栈
   → RAX = -EINTR

原handler frame不再是active stack frame。其内存仍可能暂时保留旧字节，但已经没有kernel或control-flow引用；后续用户栈使用可以覆盖它。

用户程序最终看到什么
--------------------

在raw Linux syscall ABI层面，本次 ``clock_nanosleep`` 的结果是：

.. code-block:: text

   RAX = -EINTR

并且：

.. code-block:: text

   remaining = E - Tc
   0 < remaining < 6 ms

使用POSIX libc ``clock_nanosleep()`` wrapper时，wrapper通常把negative kernel errno转换成函数返回的正 ``EINTR`` error number；``clock_nanosleep`` 的API语义与多数返回 ``-1`` 并设置 ``errno`` 的函数不同。内核源码主线在raw ``RAX=-EINTR`` 处已经闭环。

即使sigaction带 ``SA_RESTART``，本场景也不会自动继续sleep。x86 signal delivery已经把 ``-ERESTART_RESTARTBLOCK`` 固定转换为 ``-EINTR``，而sigreturn又清除了restart能力。

当前精确状态
------------

* ``system_state``：``SYSTEM_RUNNING``；
* current executor：parent；
* CPU：CPU0；
* CPU mode：x86-64 CPL 3；
* parent state：``TASK_RUNNING``，``on_rq=1``、``on_cpu=1``；
* current user RIP：原 ``clock_nanosleep`` syscall之后的下一条指令；
* raw syscall result/RAX：``-EINTR``；
* libc-visible result：通常为正error number ``EINTR``；
* ``remaining``：有效正值，固定 ``0 < remaining < 6 ms``；
* ``SIGUSR1`` handler：已执行并正常返回；
* ``SIGUSR1`` blocked state：恢复为未屏蔽；
* private pending queue：本次 ``SIGUSR1`` 已dequeue；
* ``TIF_SIGPENDING``：无其他signal时已清除；
* rt signal frame：不再active；
* user RSP：恢复为signal进入前的值；
* FPU/XSAVE state：恢复；
* restart block：``do_no_restart_syscall``；
* ``orig_ax``：``-1``；
* sleep hrtimer：不存在于queue，on-stack object已经destroy；
* local APIC：不会再为本次原expiry E唤醒parent；
* next runtime scenario：unselected。

关键边界
--------

#. handler的普通 ``RET`` 先进入 ``sa_restorer``，不能直接恢复完整CPU context。
#. ``rt_sigreturn`` 从用户 ``rt_sigframe`` 恢复mask、stack、通用寄存器和FPU state。
#. saved ``RIP`` 是原syscall后的地址，saved ``RAX`` 是 ``-EINTR``。
#. ``orig_ax=-1`` 阻止signal return路径错误restart syscall。
#. ``rt_sigreturn`` 的syscall exit使用恢复后的register frame，不返回restorer下一条指令。
#. signal frame恢复后不再active，但用户栈内存不会由kernel专门清零。
#. interrupted relative ``clock_nanosleep`` 不会因 ``SA_RESTART`` 自动继续。
#. remaining time是实际cancel时刻计算出的正值，不是理论上的精确6 ms。

资料
----

* `Linux 7.2-rc1 arch/x86/kernel/signal_64.c：x64_setup_rt_frame、rt_sigreturn与restore_sigcontext <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/signal_64.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/signal.c：signal delivery与syscall restart结果处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/signal.c>`_
* `Linux 7.2-rc1 kernel/signal.c：signal_delivered、blocked mask与signal_setup_done <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/signal.c>`_
* `Linux 7.2-rc1 kernel/time/hrtimer.c：interrupted nanosleep restart block与timer销毁 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/hrtimer.c>`_
