第三十八章：Linux common_startup_64 怎样建立 boot CPU 的最早运行上下文？
======================================================================

第三十七章结束时，解压后的正式内核已经完成页表物理地址修正，并第一次跳到高半区虚拟地址：

.. code-block:: text

   arch/x86/kernel/head_64.S:common_startup_64

此刻执行的已经不是 ``arch/x86/boot/compressed`` 中的解压器，而是正式内核映像中的汇编入口。CPU 处于 64 位 long mode，``CR3`` 指向修正后的 ``early_top_pgt``，``R15`` 保存 bootloader 传入的 ``boot_params`` 地址。

不过，这还不足以安全进入通用 C 初始化。当前页表中仍可能残留临时 identity mapping 的全局 TLB 项；CPU 还没有稳定的逻辑编号和 per-CPU 基址；栈、GDT、IDT、``EFER`` 与 ``CR0`` 也需要按照正式内核要求重新整理。

``common_startup_64`` 就是在完成这次收口。

先清理 ``CR4`` 中不应继承的状态
---------------------------------

入口先构造允许保留的 ``CR4`` 位掩码：

.. code-block:: asm

   movl $(X86_CR4_PAE | X86_CR4_LA57), %edx

启用机器检查支持的配置还会保留 ``CR4.MCE``。随后：

.. code-block:: asm

   movq %cr4, %rcx
   andl %edx, %ecx

这一步不是单纯“设置几个位”，而是主动丢弃 bootloader、解压器或前一阶段可能留下的其他 ``CR4`` 状态。

必须保留的主要项目是：

* ``PAE``：64 位分页结构仍然依赖它；
* ``LA57``：若 compressed 阶段已经切到 5 级分页，此处不能擅自关闭；
* ``MCE``：某些平台强制保持机器检查能力，贸然清除可能直接异常。

为什么要暂时清掉 ``PGE``
--------------------------

``PGE`` 是 Page Global Enable。页表项带 ``Global`` 位时，普通 ``CR3`` 切换不一定把对应 TLB 项清除。

前面正式 ``startup_64`` 虽然已经换到 ``early_top_pgt``，但 compressed 阶段和 identity mapping 可能留下 global translation。内核不希望这些旧的 1:1 地址翻译继续潜伏在 TLB 中。

因此掩码没有保留 ``PGE``。写回 ``CR4`` 时，若原先 ``PGE=1``，它会变成 0。x86 规定这种变化会清除 global TLB entries。

随后代码重新设置：

.. code-block:: asm

   btsl $X86_CR4_PSE_BIT, %ecx
   movq %rcx, %cr4

   btsl $X86_CR4_PGE_BIT, %ecx
   movq %rcx, %cr4

``PSE`` 统一开启大页能力；``PGE`` 在旧 global translation 被冲掉以后重新开启，供正式内核页表使用。

这段顺序可以概括为：

.. code-block:: text

   保存 PAE / LA57 / MCE
   → 清除其余 CR4 状态
   → 借 PGE 从 1 到 0 清掉旧 global TLB
   → 开启 PSE
   → 重新开启 PGE

确定当前逻辑 CPU 编号
---------------------

同一段 ``common_startup_64`` 以后也会被 AP 使用，因此源码同时包含 boot CPU 和 secondary CPU 两条路径。

对于当前 BSP，``smpboot_control`` 中没有 ``STARTUP_READ_APICID`` 标志，低位直接给出 CPU 编号。boot CPU 的编号是 0：

.. code-block:: asm

   movl smpboot_control(%rip), %ecx
   testl $STARTUP_READ_APICID, %ecx
   jnz .Lread_apicid

   andl $(~STARTUP_PARALLEL_MASK), %ecx
   jmp .Lsetup_cpu

因此当前主线中：

.. code-block:: text

   ECX = 0

AP 路径复杂得多。它可能：

* 从 x2APIC ID MSR 读取 APIC ID；
* 或从 local APIC MMIO 的 ``APIC_ID`` 寄存器读取；
* 再扫描 ``cpuid_to_apicid[]``，把硬件 APIC ID 映射成 Linux 逻辑 CPU 编号。

这两条路径共用后面的 ``.Lsetup_cpu``，但当前 BSP 不需要读取 APIC ID。

从 CPU 编号得到 per-CPU offset
-----------------------------

Linux 的很多变量在源码中看起来只有一份，运行时每个 CPU 实际拥有自己的副本。访问某个 CPU 的副本时，需要把该 CPU 的 per-CPU offset 加到变量基址上。

汇编执行：

.. code-block:: asm

   movq __per_cpu_offset(,%rcx,8), %rdx

当前 ``RCX=0``，所以 ``RDX`` 得到 CPU 0 的 per-CPU offset。

在完整 per-CPU allocator 尚未运行的阶段，boot CPU 仍主要使用内核映像中的初始 per-CPU 区域。这里先把统一的寻址规则建立起来，使后面的汇编和 C 代码可以通过 CPU-local 数据结构工作。

切到 ``init_task`` 的正式内核栈
------------------------------

上一章正式 ``startup_64`` 临时把 ``RSP`` 指向 ``__top_init_kernel_stack``。进入公共路径后，内核通过 per-CPU ``current_task`` 找到当前任务，再读取它保存的栈顶：

.. code-block:: asm

   movq current_task(%rdx), %rax
   movq TASK_threadsp(%rax), %rsp

boot CPU 当前任务是静态建立的 ``init_task``，因此这一步把：

.. code-block:: text

   current_task[CPU0]
   → init_task
   → init_task.thread.sp
   → RSP

连接起来。

从这里开始，主流程使用的是 task 语义下的正式启动栈，而不是解压器栈或仅用于入口过渡的临时栈。

``trampoline_lock`` 为什么对 BSP 为空
------------------------------------

AP 从 real-mode trampoline 启动时，需要一个锁保护共享的启动跳板。切到自己的栈后，AP 会把锁清零，让下一颗 CPU 可以使用 trampoline。

代码是：

.. code-block:: asm

   movq trampoline_lock(%rip), %rax
   testq %rax, %rax
   jz .Lsetup_gdt
   movl $0, (%rax)

boot CPU 并不是从 AP trampoline 进入，``trampoline_lock`` 指针为 0，所以直接跳到 ``.Lsetup_gdt``。

装入 per-CPU GDT
----------------

正式内核不能长期使用 compressed 阶段或物理入口阶段的 GDT。它在当前栈上临时构造一个 ``desc_ptr``：

.. code-block:: asm

   subq $16, %rsp
   movw $(GDT_SIZE-1), (%rsp)
   leaq gdt_page(%rdx), %rax
   movq %rax, 2(%rsp)
   lgdt (%rsp)
   addq $16, %rsp

``gdt_page(%rdx)`` 表示当前 CPU 的 GDT 页。

随后把数据段寄存器清零：

.. code-block:: asm

   xor %eax, %eax
   movl %eax, %ds
   movl %eax, %ss
   movl %eax, %es
   movl %eax, %fs
   movl %eax, %gs

64 位模式下，``DS/ES/SS`` 的传统 base/limit 语义大多被弱化，但清零能消除遗留 selector；``FS`` 和 ``GS`` 也先清掉可见 selector，真正的基址由 MSR 管理。

把 ``GSBASE`` 指向当前 CPU 的 per-CPU 区域
-----------------------------------------

内核通过 ``MSR_GS_BASE`` 建立当前 CPU 的 per-CPU 基址：

.. code-block:: asm

   movl $MSR_GS_BASE, %ecx
   movl %edx, %eax
   shrq $32, %rdx
   wrmsr

原来的 64 位 per-CPU offset 被拆成 ``EDX:EAX`` 写入 MSR。

从此以后，``%gs:offset`` 可以访问 CPU 0 的局部变量，例如 ``current_task``、CPU 状态和后续栈保护数据。这里建立的是正式内核的 GS-relative per-CPU 语义，不再是上一章最早期的 ``fixed_percpu_data`` 过渡环境。

建立 early IDT
---------------

代码调用：

.. code-block:: asm

   call early_setup_idt

``early_setup_idt()`` 最终装入早期 IDT。它不是最终的完整中断系统，而是保证在正式 ``trap_init()`` 和 ``init_IRQ()`` 之前发生的页错误、虚拟化异常或早期故障能进入可识别的处理路径。

早期异常入口会把：

* exception vector；
* 硬件 error code 或补入的 0；
* 最少的通用寄存器；

整理成统一现场，再调用 ``do_early_exception()``。

其中早期 page fault 还有特殊用途：当内核访问尚未建立 direct mapping 的地址时，``early_make_pgtable()`` 可以临时补出 PMD 映射，然后返回原指令重试。

正式打开 ``SYSCALL`` 与 NX 能力
-------------------------------

接着内核用 CPUID ``0x80000001`` 检查 NX 支持，再读取 ``MSR_EFER``：

.. code-block:: asm

   btsl $_EFER_SCE, %eax

``EFER.SCE`` 打开 ``SYSCALL/SYSRET`` 指令能力。这里尚未建立最终 syscall entry MSR，但先让处理器具备该机制。

若 CPUID 表明支持 NX：

.. code-block:: asm

   btsl $_EFER_NX, %eax
   btsq $_PAGE_BIT_NX, early_pmd_flags(%rip)

两件事同时发生：

* ``EFER.NXE`` 允许页表使用 NX bit；
* ``early_pmd_flags`` 加入 NX，使以后生成的早期数据映射能够标记为不可执行。

源码还会比较修改前后的 ``EFER``。没有变化时不执行 ``wrmsr``，这是对 TDX 等环境的兼容处理，不做没有必要的敏感 MSR 写入。

最后规范化 ``CR0`` 和 ``RFLAGS``
---------------------------------

代码把 ``CR0`` 写成内核定义的 ``CR0_STATE``，统一保护模式、分页、写保护和浮点相关控制状态。

随后：

.. code-block:: asm

   pushq $0
   popfq

把可写的 ``RFLAGS`` 状态清零。中断保持关闭，方向标志保持清除。

``initial_code`` 把汇编交给第一个正式 C 入口
------------------------------------------

最后把 ``boot_params`` 作为第一个 C 参数：

.. code-block:: asm

   movq %r15, %rdi

清空 frame pointer 后，通过函数指针调用：

.. code-block:: asm

   callq *initial_code(%rip)

静态初值是：

.. code-block:: asm

   initial_code:
       .quad x86_64_start_kernel

因此当前 BSP 的真实控制流是：

.. code-block:: text

   common_startup_64
   → initial_code
   → x86_64_start_kernel(boot_params_address)

``initial_code`` 做成变量，是因为 AP 启动、CPU hotplug 或特殊恢复路径以后可以把它改成其他入口。对第一次启动的 BSP，它就是 ``x86_64_start_kernel``。

调用返回后紧跟 ``ud2``。``x86_64_start_kernel()`` 被声明为 ``__noreturn``，正常情况下永远不会返回；若错误返回，``ud2`` 会立即触发 invalid opcode，而不是继续执行未知内存。

当前机器状态
------------

本章结束时：

* 当前执行者：即将进入 Linux 6.12.95 ``x86_64_start_kernel()``；
* CPU：BSP，Linux 逻辑 CPU 0；
* 模式：64 位 long mode；
* RIP：正式内核高半区；
* interrupts：关闭；
* ``CR3``：``early_top_pgt``；
* 旧 global identity TLB：已通过 PGE toggle 清理；
* ``CR4``：保留 PAE/LA57/MCE，已重新开启 PSE/PGE；
* current task：``init_task``；
* stack：``init_task`` 的启动栈；
* GDT：CPU 0 的 ``gdt_page``；
* GS base：CPU 0 的 per-CPU offset；
* early IDT：已装入；
* ``EFER.SCE``：已开启；
* ``EFER.NXE``：在 CPU 支持时已开启；
* ``RDI``：bootloader 传入的 ``boot_params`` 物理地址；
* ``start_kernel()``：尚未调用。

下一段从 ``arch/x86/kernel/head64.c:x86_64_start_kernel()`` 开始，清除 identity-map trampoline、清 BSS、初始化 KASAN/SME/TDX、复制 boot data、加载 BSP microcode，并进入 ``x86_64_start_reservations()``。

资料
----

* `Linux 6.12.95 head_64.S：common_startup_64、CPU 编号、per-CPU、GDT、IDT 与 initial_code <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head_64.S>`_
* `Linux 6.12.95 head64.c：early page fault 补页与 early_setup_idt <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head64.c>`_
* `Linux 6.12.95 verify_cpu.S：正式内核早期 CPU 能力验证 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/verify_cpu.S>`_
* `Linux 6.12.95 processor-flags.h：CR0、CR4 位定义 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/uapi/asm/processor-flags.h>`_
* `Linux 6.12.95 msr-index.h：EFER、GSBASE 与 APIC MSR 定义 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/msr-index.h>`_