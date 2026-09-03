========================================================================================
第 4 节：上下文切换微观过程：__switch_to() 与 __switch_to_asm() 寄存器与栈指针原子切换
========================================================================================

.. note::
   **前置背景与上下文承接**
   * **体系结构基准**：承接模块 09 第 3 节中关于进程创建核心机制（``kernel_clone``）、``copy_process()`` 十二步克隆流水线、``copy_thread()`` 栈帧装配（``childregs->rax = 0``）与 ``wake_up_new_task()`` 调度接入。
   * **核心使命**：解构多任务操作系统实现时间切片与并发运行的终极微观基石——**进程上下文切换（Context Switch / ``kernel/sched/core.c:context_switch()``）**；深度剖析虚拟地址空间切换 ``switch_mm_irqs_off()`` 与内核线程惰性 TLB（Lazy TLB）、PCID 进程上下文标识符硬件加速；逐行解构汇编级栈指针瞬切 ``arch/x86/entry/entry_64.S:__switch_to_asm()``（被调用者保存寄存器 ``RBP/RBX/R12~R15`` 压栈保护、``TASK_threadsp`` 内核栈顶指针原子对调、RSB 返回栈缓冲区防御投机攻击 ``FILL_RETURN_BUFFER``）；剖析 C 语言层 ``arch/x86/kernel/process_64.c:__switch_to()`` 对 Per-CPU 变量 ``current_task`` 更新、TSS.sp0 硬件切栈顶装配、FS/GS 段基址 MSR 刷新、FPU/AVX 向量寄存器惰性状态机（XSAVE/XRSTOR），以及 ``switch_to(prev, next, last)`` 三参数宏黑魔法与 ``finish_task_switch()`` 收尾时序。

----------------------------------------------------------------------------------------

第一幕：上下文切换的物理哲学与宏观全景
--------------------------------------

在对称多处理（SMP）架构中，单个 CPU 物理核心在任意给定纳秒内只能顺序执行一条指令流。多任务操作系统之所以能呈现出成百上千个进程“并行运行”的宏观表象，其核心依托就是以微秒级频率不断执行的 **上下文切换（Context Switch）**。

1.1 什么是上下文切换？
~~~~~~~~~~~~~~~~~~~~~~
上下文切换是指：CPU 核心强行暂停当前正在执行的任务（``prev``），将其此时此刻所有的物理硬件寄存器、虚拟内存映射与内核栈状态完整封存，并无缝载入另一个就绪任务（``next``）的历史封存现场，进而跃迁至 ``next`` 的指令流中继续运行。

::

   +-----------------------------------------------------------------------------------+
   |                           进程上下文切换两大核心维度                              |
   |                                                                                   |
   |  [维度一: 虚拟地址空间切换 (Memory Context Switch)]                               |
   |  - 函数: switch_mm_irqs_off(prev->active_mm, next->mm, next)                      |
   |  - 核心操作: 切换 CR3 页表根基寄存器、管理 TLB 缓存、处理内核线程惰性 TLB (Lazy TLB)|
   |                                                                                   |
   |  [维度二: 处理器硬件现场切换 (Processor Register Context Switch)]                  |
   |  - 汇编层: __switch_to_asm() (保存/恢复通用寄存器、原子切换 RSP 内核栈指针)       |
   |  - C语言层: __switch_to() (更新 current_task、TSS.sp0、TLS/FS/GS 基址、FPU/AVX)   |
   +-----------------------------------------------------------------------------------+

----------------------------------------------------------------------------------------

第二幕：虚拟地址空间跃迁——``switch_mm_irqs_off()`` 与惰性 TLB (Lazy TLB)
-------------------------------------------------------------------------

在 ``kernel/sched/core.c:context_switch()`` 中，调度器首先执行虚拟地址空间的切换。

2.1 用户进程 vs 内核线程（``mm`` 与 ``active_mm`` 的精妙博弈）
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* **用户进程（User Process）**：拥有独立的用户态虚拟地址空间，其 ``task->mm != NULL``；
* **内核线程（Kernel Thread / ``PF_KTHREAD``）**：完全运行在内核空间，没有私有用户页表，其 ``task->mm == NULL``，但其 ``task->active_mm`` 指向借用（Borrow）的内存描述符。

::

   +-----------------------------------------------------------------------------------+
   |                     switch_mm_irqs_off() 决策状态机流水线                         |
   |                                                                                   |
   |  if (unlikely(!next->mm)) {                                                       |
   |      /* 情况 A: 目标是内核线程 (如 kworker/kswapd) */                             |
   |      next->active_mm = prev->active_mm;                                           |
   |      enter_lazy_tlb(prev->active_mm, next);                                       |
   |      /* 【核心物理优化: 惰性 TLB】完全不触碰 CR3，不执行任何 TLB 冲刷! */         |
   |  } else {                                                                         |
   |      /* 情况 B: 目标是用户进程 */                                                 |
   |      if (prev->active_mm == next->mm) {                                           |
   |          /* 同一进程内的多线程切换: 虚拟地址空间完全一致，同样无需切换 CR3! */    |
   |      } else {                                                                     |
   |          /* 跨进程切换: 必须载入 next 的独立页表 */                              |
   |          load_new_mm_cr3(next->mm->pgd, new_asid, true);                         |
   |      }                                                                            |
   |  }                                                                                |
   +-----------------------------------------------------------------------------------+

2.2 惰性 TLB（Lazy TLB）的物理吞吐奇迹
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
内核线程仅访问大于 ``PAGE_OFFSET`` 的内核高位地址空间（在所有进程中这部分页表完全共享）。当 CPU 从用户进程切入内核线程时，内核绝不执行昂贵的 ``mov %cr3, %reg`` 指令，使 CPU 保持旧进程的 TLB 缓存处于“惰性借用”状态，极大地降低了内核中断和后台任务的上下文切换延迟。

2.3 PCID（Process-Context Identifier）硬件标签加速
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在支持硬件 PCID（CR4.PCIDE=1）的现代 x86_64 处理器上：
* 内核为每个进程分配一个 12 位的 PCID 标签（0~4095）；
* 在切换 CR3 时，内核将 CR3 的最高位（Bit 63: ``NOFLUSH``）置 1：
  $$\mathbf{CR3 = Physical\_PGD\_Base \ | \ PCID \ | \ (1ULL \ll 63)}$$
* **硬件级无损保留**：CPU 在载入新页表的同时，**绝不冲刷 TLB**，而是利用 PCID 标签并行保留多个进程的页表转换缓存。当 CPU 再次切回原进程时，TLB 依然保持极高的命中率！

----------------------------------------------------------------------------------------

第三幕：汇编级栈针原子跳跃——``__switch_to_asm()`` 微观指令推导
--------------------------------------------------------------

当地址空间就绪后，调度器调用 ``switch_to(prev, next, prev)``，控制权直接交接给纯汇编实现的 **``arch/x86/entry/entry_64.S:__switch_to_asm()``**。

3.1 被调用者保存寄存器（Callee-saved Registers）的物理哲学
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
根据 System V AMD64 ABI 调用约定：
* **调用者保存（Caller-saved）**：``RAX, RCX, RDX, RSI, RDI, R8~R11``。这些寄存器在进入系统调用或硬件中断时，已经由 ``entry_SYSCALL_64`` 或中断入口压入栈顶的 ``struct pt_regs`` 中，无需在此重复保存；
* **被调用者保存（Callee-saved）**：``RBX, RBP, R12, R13, R14, R15``。这些寄存器保存着内核 C 语言函数的局部上下文，必须在换栈前手动压栈封存。

3.2 ``__switch_to_asm`` 汇编指令逐行物理剖析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

::

   +-----------------------------------------------------------------------------------+
   |                     __switch_to_asm() 汇编指令级执行全时序                        |
   |                                                                                   |
   |  /* 入口参数: %rdi = prev 任务指针, %rsi = next 任务指针 */                       |
   |  SYM_FUNC_START(__switch_to_asm)                                                  |
   |      /* 1. 压栈封存 prev 任务的被调用者保存寄存器 (保存在 prev 的内核栈上) */     |
   |      pushq   %rbp                                                                 |
   |      pushq   %rbx                                                                 |
   |      pushq   %r12                                                                 |
   |      pushq   %r13                                                                 |
   |      pushq   %r14                                                                 |
   |      pushq   %r15                                                                 |
   |                                                                                   |
   |      /* 2. 保存当前内核栈顶指针 RSP 到 prev->thread.sp */                         |
   |      movq    %rsp, TASK_threadsp(%rdi)                                            |
   |                                                                                   |
   |      /* 3. 【历史性原子转折点】将 next->thread.sp 载入 CPU 物理 RSP 寄存器! */   |
   |      movq    TASK_threadsp(%rsi), %rsp                                            |
   |                                                                                   |
   |      /* 4. 更新栈金丝雀 (Stack Protector Canary) 防止栈溢出破坏 */                |
   |  #ifdef CONFIG_STACKPROTECTOR                                                     |
   |      movq    TASK_stack_canary(%rsi), %rbx                                        |
   |      movq    %rbx, PER_CPU_VAR(__stack_chk_guard)                                 |
   |  #endif                                                                           |
   |                                                                                   |
   |      /* 5. 填充返回栈缓冲区 (RSB)，粉碎 Spectre-v2 投机分支推测攻击 */            |
   |      FILL_RETURN_BUFFER %r12, RSB_CLEAR_LOOPS, X86_FEATURE_RSB_CTXSW             |
   |                                                                                   |
   |      /* 6. 从 next 任务的内核栈中弹出其历史封存的通用寄存器! */                   |
   |      popq    %r15                                                                 |
   |      popq    %r14                                                                 |
   |      popq    %r13                                                                 |
   |      popq    %r12                                                                 |
   |      popq    %rbx                                                                 |
   |      popq    %rbp                                                                 |
   |                                                                                   |
   |      /* 7. 跳转进入 C 语言硬件环境精细化重构函数 */                               |
   |      jmp     __switch_to                                                          |
   |  SYM_FUNC_END(__switch_to_asm)                                                    |
   +-----------------------------------------------------------------------------------+

.. important::
   **栈指针替换瞬间的物理跃迁**：
   在执行 ``movq TASK_threadsp(%rsi), %rsp`` 的那一个纳秒，CPU 的堆栈基准线瞬间从 ``prev`` 的 16KB 内存页跃迁到了 ``next`` 的 16KB 内存页！随后的 6 条 ``popq`` 指令弹出的完全是 ``next`` 进程在过去某次睡眠时封存的寄存器值！

----------------------------------------------------------------------------------------

第四幕：硬件执行环境重构——``__switch_to()`` C 语言层深水区
----------------------------------------------------------

在完成核心栈指针替换后，代码跳转执行 **``arch/x86/kernel/process_64.c:__switch_to()``**，完成剩余硬件环境的重构：

::

   +-----------------------------------------------------------------------------------+
   |                     __switch_to() 硬件环境精细化重构流水线                        |
   |                                                                                   |
   |  __visible __notrace_funcgraph struct task_struct *                               |
   |  __switch_to(struct task_struct *prev_p, struct task_struct *next_p) {            |
   |      struct thread_struct *prev = &prev_p->thread;                                |
   |      struct thread_struct *next = &next_p->thread;                                |
   |      int cpu = smp_processor_id();                                                |
   |                                                                                   |
   |      /* 1. FPU / AVX 向量浮点上下文状态机准备 */                                  |
   |      switch_fpu_prepare(prev_p, cpu);                                             |
   |                                                                                   |
   |      /* 2. 【核心】更新当前 CPU Per-CPU 变量 current_task 指针 */                 |
   |      this_cpu_write(current_task, next_p);                                        |
   |                                                                                   |
   |      /* 3. 【硬件中断切栈防线】刷新 TSS (任务状态段) 的 sp0 栈顶指针 */           |
   |      raw_cpu_write(cpu_tss_rw.x86_tss.sp0, task_top_of_stack(next_p));            |
   |                                                                                   |
   |      /* 4. 重载 GDT 中的线程局部存储描述符 (load_TLS) */                          |
   |      load_TLS(next, cpu);                                                         |
   |                                                                                   |
   |      /* 5. 刷新 FS / GS 用户态段基址 MSR 寄存器 (WRFSBASE / WRGSBASE) */          |
   |      save_fsgs_for_next(prev);                                                    |
   |      load_seg(next->fsindex, next->fsbase, MSR_FS_BASE);                          |
   |      load_seg(next->gsindex, next->gsbase, MSR_KERNEL_GS_BASE);                   |
   |                                                                                   |
   |      /* 6. 恢复 next 的 FPU / 扩展寄存器现场 (switch_fpu_finish) */               |
   |      switch_fpu_finish(next_p);                                                   |
   |                                                                                   |
   |      /* 7. 返回 prev_p 指针 (存放于 RAX 寄存器供上层收尾) */                      |
   |      return prev_p;                                                               |
   |  }                                                                                |
   +-----------------------------------------------------------------------------------+

4.1 为什么必须更新 ``TSS.sp0``？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当 ``next`` 进程未来在用户态（Ring 3）运行期间发生硬件中断（如定时器中断）或 CPU 异常时，x86_64 CPU 硬件逻辑会自动从当前 CPU 的 **TSS（Task State Segment）中的 ``sp0`` 字段** 提取内核栈顶指针，自动完成 Ring 3 $\rightarrow$ Ring 0 的硬件切栈。如果不在此处更新 ``TSS.sp0``，中断发生时 CPU 将错误地压栈到 ``prev`` 甚至更早进程的内核栈中，导致灾难性的内存覆盖！

----------------------------------------------------------------------------------------

第五幕：三参数宏黑魔法与生命周期终结（``switch_to(prev, next, last)``）
-----------------------------------------------------------------------

5.1 经典的“三参数”宏设计之谜
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 Linux 调度器宏 ``switch_to(prev, next, last)`` 中，传入了三个参数：

::

   #define switch_to(prev, next, last) \
       ((last) = __switch_to_asm((prev), (next)))

**核心物理困境**：
假设系统中有三个进程 $A$、$B$、$C$。CPU 调度时序如下：
1. 进程 $A$ 运行，决定切换给进程 $B$：执行 ``switch_to(A, B, A)``，进程 $A$ 陷入沉睡；
2. 进程 $B$ 运行，稍后切换给进程 $C$；
3. 进程 $C$ 运行，最终决定切换回进程 $A$：执行 ``switch_to(C, A, C)``。

当进程 $A$ 重新苏醒时，其指令流直接从当初睡眠点（步骤 1）继续执行。在进程 $A$ 局部的栈帧中，局部变量 ``next`` 依然记录着 $B$！如果调度器后续需要对“刚刚让出 CPU 的那个前驱任务”执行收尾清理，进程 $A$ 如何知道究竟是谁（$C$）把 CPU 移交给了自己？

**神级解法**：
* ``__switch_to()`` 在执行完毕时，通过 **``RAX`` 寄存器返回当前刚刚交出 CPU 的真实任务指针（$C$）**；
* 宏通过内联汇编将 ``RAX`` 强制写入第三个输出参数 **``last``**；
* 使得进程 $A$ 醒来后，能够精准得知“前驱任务是 $C$”！

5.2 ``finish_task_switch(last)`` 僵尸清理与锁释放
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当进程苏醒并获得 ``last`` 指针后，立即调用 ``kernel/sched/core.c:finish_task_switch(last)``：
1. **释放运行队列锁**：调用 ``raw_spin_unlock_irq(&rq->lock)``，解除调度自旋锁；
2. **终结僵尸进程（Zombie Reaping）**：若 ``last`` 任务的状态为 **``TASK_DEAD``**（该进程在切出前已调用 ``do_exit()`` 终结），则在此刻由新进程代为调用 ``put_task_struct(last)``，彻底释放其 16KB 内核栈物理页与 ``task_struct`` 结构体内存！

----------------------------------------------------------------------------------------

小结与下章导读
--------------

本节深入剖析了 Linux 7.2 进程上下文切换的底层物理全链路：虚拟地址空间切换与惰性 TLB（Lazy TLB）、PCID 硬件标签加速、``__switch_to_asm()`` 寄存器压栈与 ``RSP`` 栈指针原子替换、RSB 防御推测攻击、``__switch_to()`` 更新 Per-CPU ``current_task``、TSS.sp0 中断切栈顶、FS/GS 段基址 MSR 刷新、FPU/AVX 向量寄存器惰性切换，以及 ``switch_to(prev, next, last)`` 三参数宏黑魔法与 ``finish_task_switch()`` 僵尸收尾。

上下文切换是操作系统交接控制权的执行机构。然而，调度器究竟应该在何时、依照何种数学公平性法则从红黑树中挑选下一个运行的进程？

在 **第 5 节：EEVDF 调度器数学模型：虚拟运行时间 (vruntime)、Lag 计算与 cfs_rq 运行队列** 中，我们将深入剖析 Linux 6.6+ 及 7.2 全面普及的全新一代调度算法之王——EEVDF（Earliest Eligible Virtual Deadline First）的数学模型、时间差额（Lag）积分方程、虚拟资格时间（Eligible Time）与虚拟截止时间（Virtual Deadline）红黑树高效检索时序。
