.. SPDX-License-Identifier: GPL-2.0

================================================================
第三十五章：Linux startup_64 怎样把压缩内核搬到安全解压位置？
================================================================

上一章结束时，CPU 已经从 compressed ``startup_32`` 进入 64 位 long mode。
当前执行的仍然不是解压后的正式内核，而是 ``bzImage`` 中的压缩启动环境，源码入口是：

.. code-block:: asm

   arch/x86/boot/compressed/head_64.S:startup_64

此时已经具备：

* ``CR4.PAE = 1``；
* ``EFER.LME = 1``，进入 64 位代码段后 ``EFER.LMA = 1``；
* paging 已开启；
* 低 4 GiB 已由 2 MiB 大页进行 identity mapping；
* ``RSI`` 保存 GRUB 传入的 ``boot_params`` 物理地址；
* 中断仍关闭；
* 压缩镜像仍位于 GRUB 选择的加载区；
* 解压输出区尚未最终确定；
* ``extract_kernel()`` 尚未调用。

本章只追踪 compressed ``startup_64`` 如何计算两类地址、建立自己的栈、处理 4/5 级分页差异，并把压缩启动环境倒序搬到安全位置。章节结束在跳入重定位后副本的 ``.Lrelocated``。

``startup_64`` 是 bzImage 内部的第二个入口
----------------------------------------------

``head_64.S`` 中的 compressed ``startup_64`` 固定放在相对 ``startup_32`` 偏移 ``0x200`` 的位置：

.. code-block:: asm

   .code64
   .org 0x200
   SYM_CODE_START(startup_64)

这个 ``0x200`` 是 Linux/x86 64 位启动协议的一部分。64 位 bootloader 可以直接进入这个入口；当前固定路径由 32 位 GRUB 交接，因此先经过 compressed ``startup_32``，再由上一章建立的页表和远返回到达这里。

需要提前区分两个同名符号：

* ``arch/x86/boot/compressed/head_64.S:startup_64`` 属于压缩启动环境；
* ``arch/x86/kernel/head_64.S:startup_64`` 属于解压后的正式内核。

本章执行的是前者。后者要等内核完成解压和 ELF 装载后才会出现。

先清方向标志并保持中断关闭
--------------------------

入口最先执行：

.. code-block:: asm

   cld
   cli

``cld`` 把 ``RFLAGS.DF`` 清零，使普通字符串指令默认向高地址递增。后面倒序复制镜像时会临时执行 ``std``，复制结束后再恢复 ``cld``。

``cli`` 再次确保 maskable interrupt 关闭。此时 Linux 还没有正式 IDT、完整异常处理和驱动，中断不能随意进入。

随后代码把数据段寄存器写成零：

.. code-block:: asm

   xorl %eax, %eax
   movl %eax, %ds
   movl %eax, %es
   movl %eax, %ss
   movl %eax, %fs
   movl %eax, %gs

在 64 位模式中，``DS``、``ES`` 和 ``SS`` 的 base 通常不再参与普通线性地址形成，但把它们归零可以消除 bootloader 遗留的选择子状态，并满足 Linux 早期入口对环境的控制要求。

两个容易混淆的基址：``RBP`` 与 ``RBX``
---------------------------------------

compressed ``startup_64`` 接下来计算两个不同的地址：

``RBP``
   最终解压后的内核物理起点，也就是 ``extract_kernel()`` 的输出目标候选。

``RBX``
   压缩启动环境自身搬迁后的运行基址。它位于整个 ``init_size`` 缓冲区的高端，使压缩输入、解压程序、栈和待生成的输出不会互相覆盖。

这两个寄存器不能混为一谈。``RBP`` 指向未来的正式内核；``RBX`` 指向当前 compressed kernel 将要搬去执行的位置。

先计算解压输出起点 ``RBP``
---------------------------

对于可重定位内核，代码先取得 ``startup_32`` 当前真实运行地址：

.. code-block:: asm

   leaq startup_32(%rip), %rbp

这里使用 RIP-relative addressing。当前页表是 identity mapping，所以这同时是 compressed image 的当前线性地址和物理地址。

然后读取 ``boot_params`` setup header 中的 ``kernel_alignment``：

.. code-block:: asm

   movl BP_kernel_alignment(%rsi), %eax
   decl %eax
   addq %rax, %rbp
   notq %rax
   andq %rax, %rbp

这四步等价于：

.. code-block:: text

   RBP = ALIGN_UP(current_startup_32, kernel_alignment)

Linux 6.12.95 的 x86-64 内核要求最小 2 MiB 对齐；实际 ``kernel_alignment`` 由构建配置写入 setup header。对齐的原因不仅是性能，还因为后续早期页表以 2 MiB PMD 大页映射内核区域。

接着检查这个候选地址是否低于 ``LOAD_PHYSICAL_ADDR``：

.. code-block:: asm

   cmpq $LOAD_PHYSICAL_ADDR, %rbp
   jae 1f
   movq $LOAD_PHYSICAL_ADDR, %rbp

所以结果是：

.. code-block:: text

   RBP = max(ALIGN_UP(actual_load, kernel_alignment), LOAD_PHYSICAL_ADDR)

对于 x86-64，``LOAD_PHYSICAL_ADDR`` 通常以 1 MiB 为基础，并受 ``CONFIG_PHYSICAL_START``、``CONFIG_PHYSICAL_ALIGN`` 等构建值影响。这里不把它简单等同于“永远就是 1 MiB”；源码使用的是构建期常量。

再计算 compressed image 的搬迁基址 ``RBX``
------------------------------------------

setup header 的 ``init_size`` 描述从最终内核输出起点开始，启动阶段需要保留的完整连续内存长度。它不仅覆盖压缩文件大小，还要覆盖：

* 解压后的内核映像；
* 解压器运行空间；
* compressed kernel 的 ``.bss``；
* boot heap；
* boot stack；
* 页表和安全余量。

代码执行：

.. code-block:: asm

   movl BP_init_size(%rsi), %ebx
   subl $rva(_end), %ebx
   addq %rbp, %rbx

因此：

.. code-block:: text

   RBX = RBP + init_size - rva(_end)

``rva(_end)`` 是 ``_end`` 相对 compressed ``startup_32`` 的偏移。

这个公式保证：

.. code-block:: text

   RBX + rva(_end) = RBP + init_size

也就是说，compressed kernel 搬迁后，它自己的末尾 ``_end`` 正好贴到整个初始化缓冲区末端。压缩输入和解压代码被放在高端，低端从 ``RBP`` 开始留给不断增长的解压输出。

内存关系可以抽象成：

.. code-block:: text

   RBP                                                   RBP + init_size
    |                                                           |
    |---- 解压输出与正式内核运行区 ----|---- compressed ZO ----|
                                      ^
                                      RBX

这里的 ZO 是 compressed kernel，也常被称为 ``vmlinux.bin.gz`` 一侧的压缩启动对象；VO 是解压后的 ``vmlinux`` 映像。

栈也必须切换到搬迁后的地址体系
----------------------------

新的栈顶按 ``RBX`` 计算：

.. code-block:: asm

   leaq rva(boot_stack_end)(%rbx), %rsp

``boot_stack`` 位于 compressed image 的 ``.bss`` 区，大小由 ``BOOT_STACK_SIZE`` 决定；x86-64 当前为 ``0x4000``，即 16 KiB。

这里不能继续使用上一章在旧地址上建立的栈，因为接下来 compressed image 会搬迁，旧代码和旧数据区域可能在解压时被覆盖。新的 ``RSP`` 必须指向即将成为正式运行副本的地址。

为什么要重新装载 GDT 和 CS
--------------------------

代码构造 ``gdt64`` 描述符的运行时 base，然后执行 ``lgdt``：

.. code-block:: asm

   leaq gdt64(%rip), %rax
   addq %rax, 2(%rax)
   lgdt (%rax)

``gdt64`` 中保存的 base 最初是相对值。``addq`` 把当前运行地址加入描述符，使 GDTR 指向实际 GDT。

随后通过远返回重新装载 ``CS``：

.. code-block:: asm

   pushq $__KERNEL_CS
   leaq .Lon_kernel_cs(%rip), %rax
   pushq %rax
   lretq

进入 long mode 并不意味着当前 ``CS`` 一定来自 Linux 自己的 GDT。上一章使用的是 compressed ``startup_32`` 建立的过渡描述符；这里重新装载 ``__KERNEL_CS``，保证后续异常返回、模式转换和 5 级分页 trampoline 使用的是当前 Linux GDT 中真实存在的代码段。

把 ``boot_params`` 指针保存到 ``R15``
------------------------------------

Linux/x86 64 位启动协议规定进入入口时 ``RSI`` 指向 ``boot_params``。但后面会调用多个 C 函数，而 ``RSI`` 是 caller-saved register，普通函数调用可以覆盖它。

代码因此执行：

.. code-block:: asm

   movq %rsi, %r15

``R15`` 属于 System V AMD64 ABI 的 callee-saved register。后面的 ``configure_5level_paging()``、SEV 初始化和异常处理代码都必须保留它。

从这里开始，本阶段长期使用：

.. code-block:: text

   R15 = boot_params physical/identity-mapped address
   RBP = candidate decompressed-kernel physical base
   RBX = relocated compressed-kernel base

先装入第一阶段异常处理
----------------------

代码调用：

.. code-block:: asm

   call load_stage1_idt

compressed kernel 此时尚未拥有正式内核 IDT，但接下来会执行 CPUID、控制寄存器和分页模式转换。对于普通机器，错误通常意味着无法继续；对于 SEV-ES/SNP 等 confidential guest，某些指令还可能触发 ``#VC``。

``load_stage1_idt`` 建立的是压缩启动期第一阶段 IDT，不是正式内核后续使用的完整中断描述符表。

随后，如果构建启用 AMD memory encryption，代码把 ``R15`` 作为第一个参数调用 ``sev_enable()``。固定 QEMU q35 路径是否进入该分支取决于虚拟 CPU 和启动参数；正文保留这个真实条件分支，不把它误写成所有系统必经动作。

为什么 4 级与 5 级分页切换需要低端 trampoline
---------------------------------------------

代码先只保留 ``CR4`` 中此阶段必须维持的位：

.. code-block:: asm

   movq %cr4, %rax
   andl $(X86_CR4_PAE | X86_CR4_MCE | X86_CR4_LA57), %eax
   movq %rax, %cr4

然后调用：

.. code-block:: asm

   movq %r15, %rdi
   leaq rva(top_pgtable)(%rbx), %rsi
   call configure_5level_paging

是否需要 5 级分页由三个条件共同决定：

* 内核构建启用 ``CONFIG_X86_5LEVEL``；
* 命令行没有 ``no5lvl``；
* CPU 的 CPUID leaf 7 报告 ``LA57`` 支持。

当前固定命令行没有 ``no5lvl``，但 QEMU 的具体 CPU model 是否暴露 ``LA57`` 仍是运行时条件。

不能在 active long mode 中直接翻转 ``CR4.LA57``。Intel/AMD 架构要求先离开 paging/long-mode active 状态，否则会产生 ``#GP``。因此 ``configure_5level_paging()``：

#. 从 BDA/E820 推导低端可用区域；
#. 在传统 BIOS 内存上界下方保留 8 KiB trampoline；
#. 保存原内容；
#. 复制一段 32 位 trampoline 代码；
#. 临时离开 long mode 和 paging；
#. 切换 ``CR4.LA57``；
#. 装入新的 top-level page table；
#. 再开启 paging 并回到 long mode；
#. 把最终 top-level table 复制到 compressed image 的 ``top_pgtable``；
#. 恢复低端 trampoline 原内容。

如果当前分页层级已经符合内核要求，函数直接返回，不执行 trampoline。

清零 ``RFLAGS``
----------------

模式配置结束后执行：

.. code-block:: asm

   pushq $0
   popfq

这会清除当前可写的状态标志，包括可能由前面代码留下的 arithmetic flags。``IF`` 仍为零，方向标志也为零。compressed 启动环境从一个确定的 flags 状态继续。

为什么必须从高地址向低地址倒序复制
----------------------------------

现在代码把 compressed image 的已初始化部分搬到以 ``RBX`` 为基址的新位置：

.. code-block:: asm

   leaq (_bss-8)(%rip), %rsi
   leaq rva(_bss-8)(%rbx), %rdi
   movl $(_bss - startup_32), %ecx
   shrl $3, %ecx
   std
   rep movsq
   cld

源末端：

.. code-block:: text

   current _bss - 8

目标末端：

.. code-block:: text

   RBX + rva(_bss - 8)

复制长度：

.. code-block:: text

   _bss - startup_32

所以复制范围覆盖 compressed image 的代码和已初始化数据，停在 ``.bss`` 之前。``.bss`` 本来就不需要从旧位置复制，下一章会在新位置清零。

使用 ``std`` 后，``rep movsq`` 每复制 8 字节就同时递减 ``RSI`` 和 ``RDI``。这样即使源区和目标区部分重叠，也不会让先写入的目标数据破坏后面尚未读取的源数据。

它等价于 ``memmove`` 在 ``dest > src`` 且区域重叠时选择的从尾部向头部复制策略。

复制结束必须立即 ``cld``，因为后续 C 代码和字符串操作都假定方向标志为零。

GDT 也要切到搬迁后的副本
------------------------

当前 GDTR 仍指向旧位置的 GDT。旧 compressed image 后续可能被解压输出覆盖，所以代码重新构造新副本的 ``gdt64``：

.. code-block:: asm

   leaq rva(gdt64)(%rbx), %rax
   leaq rva(gdt)(%rbx), %rdx
   movq %rdx, 2(%rax)
   lgdt (%rax)

现在 GDTR 指向 ``RBX`` 地址体系中的 GDT。即使旧压缩镜像被覆盖，当前 CPU 仍有可用的描述符表。

跳入搬迁后的 ``.Lrelocated``
----------------------------

最后计算新副本中 ``.Lrelocated`` 的绝对地址：

.. code-block:: asm

   leaq rva(.Lrelocated)(%rbx), %rax
   jmp *%rax

这是本章的自然控制权交接点。

CPU 没有切换模式，也没有换执行者；变化发生在代码和数据位置：同一份 compressed kernel 从 GRUB 原始加载位置转移到为安全原地解压安排的高端位置。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 compressed ``.Lrelocated``；
* CPU：BSP；
* 模式：64 位 long mode；
* paging：开启；
* 分页层级：已经按 CPU、构建配置和 ``no5lvl`` 条件调整；
* ``R15``：``boot_params`` 地址；
* ``RBP``：解压后内核物理目标候选；
* ``RBX``：compressed image 新运行基址；
* ``RSP``：新副本中的 16 KiB boot stack；
* compressed 代码和已初始化数据：已倒序复制到安全位置；
* GDTR：已指向新副本中的 GDT；
* ``.bss``：尚未清零；
* 更完整 identity maps：尚未建立；
* KASLR 最终输出位置：尚未选择；
* ``extract_kernel()``：尚未调用；
* 正式内核：尚未解压。

下一段控制流从 ``.Lrelocated`` 第一条 ``rep stosq`` 开始。

资料
----

* `Linux 6.12.95 compressed head_64.S：startup_64 与 .Lrelocated <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/head_64.S>`_
* `Linux 6.12.95 pgtable_64.c：configure_5level_paging <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/pgtable_64.c>`_
* `Linux 6.12.95 asm/boot.h：BOOT_STACK_SIZE 与 BOOT_INIT_PGT_SIZE <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/boot.h>`_
* `Linux/x86 Boot Protocol：32 位与 64 位入口要求 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_
