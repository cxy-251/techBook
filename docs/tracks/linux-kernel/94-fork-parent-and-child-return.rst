第九十四章：scheduler 怎样启动 child，并让 fork() 在父子进程返回不同结果？
============================================================================

第九十三章结束时，child已经获得 PID、独立 process resources和 COW页表，也已加入 process tree，但仍处于：

.. code-block:: text

   TASK_NEW
   on_rq = 0

parent仍在 ``kernel_clone()`` 中。本章追踪 ``wake_up_new_task()``、parent正常 syscall返回和 child首次调度进入 ``ret_from_fork_asm`` 的两条控制流。

本章结束时 parent与 child都回到用户态：

.. code-block:: text

   parent fork() return = child PID
   child  fork() return = 0

两者谁先到达用户态由 scheduler时序决定，源码没有规定固定顺序。

``kernel_clone`` 怎样取得 parent 的返回值
----------------------------------------

``copy_process()`` 返回 child ``task_struct *p`` 后，``kernel_clone()`` 取得：

.. code-block:: c

   pid = get_task_pid(p, PIDTYPE_PID);
   nr = pid_vnr(pid);

``nr`` 是相对于 parent当前 active PID namespace可见的 child PID。固定 parent与 child在同一 PID namespace，因此它就是普通用户态看到的 child process ID。

普通 fork没有 ``CLONE_PARENT_SETTID``、pidfd或 ``CLONE_VFORK``，所以不会：

* 向 userspace parent_tid地址写 PID；
* 安装 pidfd；
* 等待 child exec或 exit后才唤醒 parent。

接下来只需要让 child成为 runnable。

``wake_up_new_task`` 怎样把 ``TASK_NEW`` 变成 runnable
----------------------------------------------------

``kernel_clone()`` 调用：

.. code-block:: c

   wake_up_new_task(p);

scheduler先取得 child ``pi_lock``，然后执行：

.. code-block:: c

   WRITE_ONCE(p->__state, TASK_RUNNING);

这一步结束 ``TASK_NEW`` 构造保护，但 child尚未执行。函数随后：

#. 通过 ``select_task_rq()`` 为 child选择初始 CPU；
#. 取得目标 runqueue lock；
#. 更新 runqueue clock；
#. 初始化 child调度实体的 utilization状态；
#. ``activate_task()`` 把 child加入 runqueue；
#. 记录 ``sched_wakeup_new`` tracepoint；
#. ``wakeup_preempt()`` 判断 child是否应促使当前 task重新调度。

完成后：

.. code-block:: text

   p->__state = TASK_RUNNING
   p->on_rq   = 1

这表示 child有资格被 scheduler选中，不表示它已经在 CPU上执行。

为什么 parent 与 child 的先后顺序不固定
--------------------------------------

``wake_up_new_task()`` 可能把 child放到 parent所在 CPU，也可能选择其他允许的 online CPU。``wakeup_preempt()`` 可能标记当前 CPU需要重新调度。

因此至少存在两种合法时序：

.. code-block:: text

   时序 A
   parent继续运行
   → kernel_clone返回 child PID
   → parent返回用户态
   → child稍后首次运行

   时序 B
   wakeup使 parent需要调度
   → scheduler先运行 child
   → child返回用户态 0
   → parent之后恢复并返回 child PID

在多核系统中两者甚至可以近似并行。POSIX只规定返回值和可见语义，不规定哪个 process先执行 fork之后的下一条用户指令。

parent 怎样从 ``kernel_clone`` 返回
----------------------------------

``wake_up_new_task()`` 返回后，``kernel_clone()`` 释放临时 PID reference并：

.. code-block:: c

   return nr;

调用链回到：

.. code-block:: text

   kernel_clone
   → __do_sys_fork / __x64_sys_fork wrapper
   → x64_sys_call
   → do_syscall_x64

``do_syscall_x64()`` 把返回值写入 parent自己的 syscall frame：

.. code-block:: c

   parent_regs->ax = child_pid;

随后 ``syscall_exit_to_user_mode()`` 处理 pending signal、reschedule、audit、trace等 exit work。固定场景没有额外 signal或 tracing work。

``do_syscall_64()`` 检查 parent register state是否满足 SYSRET约束。合法普通路径可以使用 ``SYSRETQ``；若 register、flags或安全检查不满足，则使用 ``IRETQ`` fallback。

parent回到同一 ``SYSCALL`` 后的用户指令，观察：

.. code-block:: text

   RAX = child PID > 0

child 为什么不沿 parent 的 C 调用栈返回
-------------------------------------

child从未执行 ``kernel_clone()``。它自己的 kernel stack由 ``copy_thread()`` 预先布置：

.. code-block:: text

   p->thread.sp    → child fork_frame
   frame->ret_addr → ret_from_fork_asm
   childregs->ax   = 0

scheduler第一次选择 child时，context switch加载 ``p->thread.sp``。``__switch_to_asm`` 恢复 child的 callee-saved frame并返回到：

.. code-block:: asm

   ret_from_fork_asm

所以 child第一次内核执行位置不是 syscall入口，也不是 ``copy_process()`` 的中间位置。

``ret_from_fork_asm`` 怎样调用 C helper
--------------------------------------

汇编入口把 context-switch返回的 previous task与 child ``pt_regs`` 传给：

.. code-block:: c

   ret_from_fork(prev, regs, fn, fn_arg);

普通 userspace fork中：

.. code-block:: text

   fn = NULL
   fn_arg = NULL

``ret_from_fork()`` 首先调用：

.. code-block:: c

   schedule_tail(prev);

它完成第一次 context switch后的 scheduler收尾，例如释放 previous runqueue相关状态和执行 balance callbacks。child从此是正常 running task。

因为 ``fn == NULL``，不会执行 kernel-thread function。函数直接调用：

.. code-block:: c

   syscall_exit_to_user_mode(regs);

这让 child执行与 syscall exit相同的 signal、reschedule和 userspace-entry检查，但它并没有走 parent正在展开的 ``do_syscall_64()`` C调用栈。

child 为什么固定使用 IRETQ 返回
-------------------------------

``ret_from_fork_asm`` 在 C helper返回后跳到：

.. code-block:: asm

   swapgs_restore_regs_and_return_to_usermode

固定场景排除 FRED。该路径恢复 child ``pt_regs``，在启用 PTI时切换到 user CR3，执行 ``swapgs``，最终通过：

.. code-block:: asm

   iretq

恢复 child的用户 RIP、CS、RFLAGS、RSP和 SS。

它与 parent的 syscall fast-return路径不同：parent可以根据 ``do_syscall_64()`` 的检查选择 SYSRETQ；new child从预构造 ``pt_regs`` 通过通用 IRETQ路径第一次进入用户态。

child 返回 0 的来源是什么
-------------------------

第九十三章中 ``copy_thread()`` 已执行：

.. code-block:: c

   childregs->ax = 0;

IRETQ恢复通用寄存器后，child在 fork之后的同一用户 RIP继续执行，观察：

.. code-block:: text

   RAX = 0

parent与 child的用户 RIP、RSP和大多数寄存器值初始相同，是因为 child ``pt_regs`` 从 parent syscall frame复制；返回值不同，是因为两套独立 ``pt_regs`` 中的 ``RAX`` 分别被设置。

COW 页面此时处于什么状态
------------------------

parent与 child都回到用户态后，固定 anonymous folio仍未复制：

.. code-block:: text

   parent private PTE --read-only--┐
                                   ├→ same anonymous folio F
   child private PTE  --read-only--┘

两者读取该地址都会看到 fork时相同内容。任一进程第一次写入时会产生 protection page fault，内核再判断是否需要复制 folio并安装新的 writable PTE。

fork完成不等于 COW已经发生；当前只完成 COW关系建立。

当前精确状态
------------

在 scheduler最终分别运行两个 task后：

.. code-block:: text

   parent
   CPU mode       = CPL 3
   fork result    = child PID
   mm             = parent mm
   task PID       = original parent PID

   child
   CPU mode       = CPL 3
   fork result    = 0
   mm             = child mm
   task PID/TGID  = allocated child PID
   real_parent    = parent
   exit_signal    = SIGCHLD

共同状态：

* parent与 child ``task_struct``：不同；
* kernel stacks：不同；
* mm和页表根：不同；
* files/fs/sighand/signal/cred：不同对象；
* namespaces：相同 namespace objects；
* fd table：不同；
* open file descriptions：对应 fd仍引用相同 ``struct file``；
* 固定 anonymous folio：仍由父子只读 PTE共享；
* child state：正常 ``TASK_RUNNING`` 或后续 scheduler状态；
* child首次 userspace entry：已通过 ``ret_from_fork_asm`` 与 IRETQ完成；
* fork runtime scenario：complete。

关键边界
--------

#. ``wake_up_new_task()`` 使 child runnable，不保证 child立即执行。
#. parent与 child谁先返回用户态没有固定顺序。
#. parent返回值来自 ``kernel_clone()`` 的 child PID。
#. child返回值来自 ``copy_thread()`` 预置的 ``childregs->ax=0``。
#. child首次执行从 ``ret_from_fork_asm`` 开始，不重新运行 syscall入口。
#. parent可能使用 SYSRETQ或 IRETQ；child首次 userspace return走 IRETQ路径。
#. fork完成只建立 COW映射，物理 folio仍未因普通 fork立即复制。

资料
----

* `Linux 7.2-rc1 kernel/fork.c：kernel_clone 与 wake_up_new_task调用 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/fork.c>`_
* `Linux 7.2-rc1 kernel/sched/core.c：sched_fork、wake_up_new_task 与 runqueue enqueue <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/sched/core.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/process.c：copy_thread 与 ret_from_fork <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/process.c>`_
* `Linux 7.2-rc1 arch/x86/entry/entry_64.S：ret_from_fork_asm 与 IRETQ userspace return <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/entry_64.S>`_
* `Linux 7.2-rc1 arch/x86/entry/syscall_64.c：parent syscall return selection <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/syscall_64.c>`_
