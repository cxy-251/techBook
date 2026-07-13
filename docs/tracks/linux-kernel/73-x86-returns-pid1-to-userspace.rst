第七十三章：x86 怎样让 PID 1 从 ret_from_fork 真正进入用户态？
================================================================

第七十二章结束时，成功的 ``kernel_execve()`` 已经替换 PID 1 的地址空间，并把 ELF entry、用户 stack、segment selector 和 flags 写入 ``current_pt_regs()``。

当前 CPU 仍在 Ring 0。``kernel_execve()`` 返回 0 后，控制流依次返回：

.. code-block:: text

   kernel_execve()
   → run_init_process()
   → kernel_init()
   → return 0

这个 ``return 0`` 不会返回到 ``start_kernel()``。PID 1 最初由 ``user_mode_thread(kernel_init, ...)`` 创建，它的底层返回链早已设置为：

.. code-block:: text

   ret_from_fork_asm
   → ret_from_fork()
   → call kernel_init()

过去几章的 PID 1 初始化工作全部发生在 ``ret_from_fork()`` 对 ``kernel_init()`` 的那次函数调用内部。现在 ``kernel_init()`` 返回，控制权才重新回到 ``ret_from_fork()``。

本章追踪 ``ret_from_fork()``、通用 exit-to-user work、x86 PTI/FRED 返回汇编，直到 PID 1 执行用户映像的第一条指令。这里是内核启动主线的最终执行环境交接。

``user_mode_thread`` 与真正 kernel thread 的关键差异
--------------------------------------------------

第六十八章创建 PID 1 时，``user_mode_thread()`` 向 ``kernel_clone()`` 提供：

.. code-block:: text

   fn      = kernel_init
   fn_arg  = NULL
   flags   = CLONE_VM | CLONE_UNTRACED | CLONE_FS
   kthread = 0

``copy_thread()`` 看到 ``args->fn`` 后，先建立与 kernel thread 类似的函数调用 frame，使新 task 第一次运行时可以调用 ``kernel_init``。但 PID 1 没有 ``PF_KTHREAD``。

因此 PID 1 同时具备两个阶段：

.. code-block:: text

   early lifetime
   → start from a kernel C function

   after successful exec
   → return through user pt_regs
   → become a normal userspace task

PID 2 的创建参数设置 ``kthread = 1``，并带有 ``PF_KTHREAD``。它只能持续运行 kernel-thread function，不允许通过 ``kernel_execve()`` 变成用户进程。

新 task 第一次为什么从 ``ret_from_fork_asm`` 开始
------------------------------------------------

x86 ``copy_thread()`` 为 PID 1 的 inactive task frame 写入：

.. code-block:: c

   frame->ret_addr = (unsigned long)ret_from_fork_asm;
   p->thread.sp = (unsigned long)fork_frame;

scheduler 第一次切换到 PID 1 时，``__switch_to_asm`` 恢复这份 kernel stack frame，最终像函数返回一样进入 ``ret_from_fork_asm``。

该汇编把：

.. code-block:: text

   previous task pointer → RDI
   pt_regs pointer       → RSI
   kernel function       → RDX
   function argument     → RCX

然后调用 C 函数 ``ret_from_fork()``。

``schedule_tail()`` 早已发生在 kernel_init 之前
---------------------------------------------

``ret_from_fork()`` 的开头是：

.. code-block:: c

   schedule_tail(prev);

它完成新 task 第一次 context switch 的 scheduler 收尾，例如解除前一 task 相关状态并完成 fork 后的调度 bookkeeping。

随后：

.. code-block:: c

   if (fn)
       fn(fn_arg);

这里对 PID 1 调用了 ``kernel_init(NULL)``。因此 ``schedule_tail()`` 并不是当前章节才执行；它在 PID 1 第一次获得 CPU、进入第六十九章之前就已经完成。

当前章节从 ``fn(fn_arg)`` 返回的下一条语句继续。

为什么 ``regs->ax`` 被强制写成 0
--------------------------------

``kernel_init()`` 在成功 exec 后返回 0。``ret_from_fork()`` 随后执行：

.. code-block:: c

   regs->ax = 0;

这个寄存器框架在语义上类似一次成功的 fork/exec 返回。用户态启动代码不应看到 ``kernel_init`` 的 C 返回值或残留 kernel register 内容。

x86-64 ABI 中 ``RAX`` 也承载 syscall 返回值。清零使用户态入口获得确定状态，并避免把内核地址或临时数值泄露到用户上下文。

``syscall_exit_to_user_mode()`` 为什么能用于 ret-from-fork
---------------------------------------------------------

下一步是：

.. code-block:: c

   syscall_exit_to_user_mode(regs);

PID 1 并没有真正从用户态执行一条 ``syscall`` 进入内核，但“从 kernel function 返回到新用户上下文”需要完成与 syscall exit 相同的通用工作。

该函数明确供 architecture syscall path 和 ret-from-fork path 共用。它保证切换前处理：

* audit 与 syscall tracing 状态；
* ptrace single-step；
* restartable sequences；
* pending signal；
* reschedule 请求；
* task work；
* notify-resume；
* context tracking；
* RCU user transition；
* lockdep 和 address-limit 检查。

这些工作必须在仍能安全调度、取得锁或处理中断时完成，不能等到 ``iretq`` 后再处理。

exit-to-user 的三段式顺序
-------------------------

通用实现按三阶段运行：

.. code-block:: text

   1. syscall_exit_to_user_mode_work(regs)
      → one-time audit/trace/ptrace/rseq work

   2. local_irq_disable()
      → syscall_exit_to_user_mode_prepare(regs)
      → loop over pending TIF work

   3. exit_to_user_mode()
      → context tracking / RCU / lockdep final transition

函数入口要求 interrupts enabled；返回时 interrupts disabled。原因是架构汇编即将恢复用户 CR3、GS base 和 register frame，中间不能再被普通中断打断并重新产生待处理 work。

pending signal 会怎样影响第一条用户指令
--------------------------------------

若 PID 1 在进入用户态前已有 pending signal，exit-to-user loop 会先处理 signal delivery。它可能重写用户 stack 和 ``pt_regs``，让首次用户返回进入 signal trampoline，而不是原始 ELF entry。

正常启动路径通常没有此类 signal，但内核不能假设永远不存在。ptrace、seccomp、task work 与 tracing 也可能改变返回行为。

因此第七十二章写入的 ELF entry 是预期入口；最终 ``iretq`` 使用的是所有 exit work 完成后的 ``pt_regs``。

``ret_from_fork()`` 返回汇编入口
--------------------------------

通用 exit work 完成后，``ret_from_fork()`` 返回 ``ret_from_fork_asm``。汇编此时认定 stack 顶部的 register set 已是完整、可返回的用户 frame。

固定源码根据 CPU feature 选择：

.. code-block:: text

   FRED enabled
   → asm_fred_exit_user

   normal x86 entry model
   → swapgs_restore_regs_and_return_to_usermode

FRED（Flexible Return and Event Delivery）是较新的 x86 event-delivery 机制。固定 QEMU CPU model 没有锁定，正文不能断言必定使用 FRED；传统路径仍需完整说明。

传统路径为什么不用 ``SYSRET``
----------------------------

普通 x86-64 syscall 快速返回在满足条件时可以使用 ``SYSRET``。PID 1 的首次用户切换来自 ret-from-fork frame，不是标准 ``SYSCALL`` entry 保存的快速返回布局。

``ret_from_fork_asm`` 直接跳向通用 register restore 路径，最终使用完整 IRET frame：

.. code-block:: text

   RIP
   CS
   RFLAGS
   RSP
   SS

因此传统首次切换使用 ``iretq``，而不是 ``sysretq``。

无 PTI 时的返回路径
------------------

若 PTI 未启用，``swapgs_restore_regs_and_return_to_usermode`` 大致执行：

.. code-block:: text

   mitigation exit work
   → restore general-purpose registers
   → skip orig_ax
   → swapgs
   → clear CPU buffers when required
   → verify IRET frame targets user privilege
   → iretq

``swapgs`` 把 GS base 从 kernel per-CPU base 切换回用户 GS base。x86 内核依赖 kernel GS 访问 per-CPU 数据；用户态必须恢复自己的 GS context。

CPU-buffer clearing 和 IBRS exit 等步骤取决于最终启用的 speculative-execution mitigation。

启用 PTI 时为什么先切 trampoline stack
-------------------------------------

PTI 开启时，用户 page table 只保留进入/退出内核所需的极小映射。当前 kernel stack 在切换到 user CR3 后可能不再可访问。

因此汇编先：

.. code-block:: text

   pop most registers
   → preserve current IRET frame pointer
   → switch to per-CPU trampoline stack
   → copy SS/RSP/RFLAGS/CS/RIP to trampoline stack
   → preserve user RDI
   → SWITCH_TO_USER_CR3
   → restore user RDI
   → swapgs
   → iretq

trampoline stack 同时映射在 kernel 与用户侧最小 entry page table 中，所以切换 CR3 后仍能完成最后几条指令。

这正是第七十一章 ``pti_finalize()`` 必须同步 entry text 和权限的原因：此路径在 kernel mappings 大部分不可见时仍必须可靠执行。

``SWITCH_TO_USER_CR3`` 改变了什么
--------------------------------

启用 PTI 时，该宏把 CR3 从完整 kernel page table 切换到当前 mm 的用户 page table，并按 CPU capability 使用 PCID/flush 优化。

切换之后：

* 用户程序映射可访问；
* kernel direct map、vmalloc 和大部分 kernel text 不再映射；
* 仅 entry trampoline、CPU entry area 等必要页面保留；
* TLB 是否刷新取决于 PCID 与 generation 状态。

这不是加载用户程序的动作。用户 ELF mappings 已在第七十二章建立；CR3 切换只是让 CPU 采用那套地址翻译视图。

``iretq`` 如何同时完成 Ring 0 → Ring 3
-------------------------------------

``iretq`` 从 stack 弹出 ``RIP``、``CS``、``RFLAGS``、``RSP``、``SS``。由于目标 ``CS`` 的 RPL 是 3，CPU 识别出 privilege-level change，并执行：

.. code-block:: text

   CPL 0 → CPL 3
   kernel RIP → user ELF/interpreter entry
   kernel RSP → new user stack
   kernel segment context → user segment context
   RFLAGS.IF → enabled

从 ``iretq`` 完成的瞬间起，PID 1 才真正处于用户态。

若 CPU 使用 FRED，最终硬件指令序列不同，但结果相同：恢复 user register context、user page table 和 privilege level，并进入准备好的用户 entry。

第一条用户指令不是 C 的 ``main``
--------------------------------

最终 ``RIP`` 取决于映像类型：

.. code-block:: text

   static ELF
   → executable ELF e_entry

   dynamically linked ELF with PT_INTERP
   → dynamic linker e_entry

   #! script
   → interpreter ELF entry

动态 linker 首先读取用户 stack 上的 argv/envp/auxv，完成 relocation、TLS、library loading 等工作，之后才跳向 executable startup code。C runtime 再建立语言运行环境，最后调用 ``main``。

因此“内核启动完成”与“init 的 main 开始执行”之间仍有用户态 loader/runtime 路径。

PID 1 身份在切换中保持不变
-------------------------

``iretq`` 不创建 task，也不改变 PID。切换前后：

.. code-block:: text

   task_struct = same PID 1
   credentials = exec committed credentials
   mm          = new userspace mm
   files       = inherited except close-on-exec
   namespaces  = inherited initial namespaces
   cgroup      = inherited root membership

变化的是 CPU 当前使用的 privilege level、page table view、register state 和 instruction stream。

启动内核调用链到这里结束
----------------------

第一个用户指令开始后，不存在从用户程序正常“返回”到 ``kernel_init()`` 的路径。旧的内核启动调用链已经完成使命。

PID 1 后续只能通过以下事件重新进入内核：

* syscall；
* page fault 或其他 exception；
* interrupt 抢占；
* signal delivery/return；
* scheduler context switch。

内核仍持续运行，但启动主线从“单向 C 函数调用序列”变成由用户请求、硬件事件和 scheduler 驱动的运行期系统。

本章结束时的机器状态
--------------------

本章结束时：

* system state：``SYSTEM_RUNNING``；
* PID 0：每个 CPU 的 idle task 按需运行；
* PID 1：已进入用户态 init/early-userspace 映像；
* PID 2：``kthreadd`` 在内核态服务 kthread 创建请求；
* CPU mode：运行 PID 1 的 CPU 为 CPL 3；
* user CR3：若 PTI 启用，已切换到用户 page table；
* user RIP：ELF entry、dynamic linker entry 或 script interpreter entry；
* user RSP：指向 argc/argv/envp/auxv 构成的初始 stack；
* interrupts：用户 ``RFLAGS.IF`` 已置位；
* kernel ``__init`` memory：已回收；
* kernel boot handoff：完成。

从这一刻继续按真实时间线，需要固定实际 initramfs 内容、最终 init executable 及其动态链接器。当前固定主线没有锁定这些用户态文件，因此不能伪造“第一条 syscall”或 init 的具体业务流程。

若继续研究 Linux 内核，下一阶段应改用明确的运行期入口，例如固定一个 ``read()``、``openat()``、``fork()``、page fault、timer interrupt 或 block I/O 场景，从用户态重新进入内核并追踪完整调用路径。

资料
----

* `Linux 7.2-rc1 arch/x86/kernel/process.c：copy_thread 与 ret_from_fork <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/process.c>`_
* `Linux 7.2-rc1 arch/x86/entry/entry_64.S：ret_from_fork_asm、PTI restore、swapgs 与 iretq <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/entry/entry_64.S>`_
* `Linux 7.2-rc1 include/linux/entry-common.h：syscall_exit_to_user_mode 三阶段处理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/entry-common.h>`_
* `Linux 7.2-rc1 arch/x86/kernel/process_64.c：start_thread_common 生成用户 pt_regs <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/process_64.c>`_
* `Linux 7.2-rc1 fs/binfmt_elf.c：ELF entry、stack 与 START_THREAD <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/binfmt_elf.c>`_
* `Linux 7.2-rc1 Documentation/core-api/entry.rst：kernel entry/exit state model <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/core-api/entry.rst>`_