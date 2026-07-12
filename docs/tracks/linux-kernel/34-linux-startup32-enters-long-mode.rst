第三十四章：Linux startup_32 怎样建立 4 GiB 映射并进入 64 位模式？
================================================================

上一章最后，GRUB relocator 使用 far jump 把控制权交给 Linux 6.12.95：

::

   CS:EIP = 0x10:code32_start
   ESI    = boot_params 物理地址

当前指令已经来自：

::

   arch/x86/boot/compressed/head_64.S:startup_32

这里的 ``startup_32`` 属于 **compressed kernel**。它不是最终解压后的 ``arch/x86/kernel/head_64.S``，也不是 ``start_kernel()``。它的任务是先建立一个能运行 64 位解压器的最小环境。

32 位入口为什么固定在 payload 偏移 0
-----------------------------------

源码首先声明：

::

   32bit entry is 0 and it is ABI so immutable

GRUB 把 ``code32_start`` 指向 protected-mode payload 的起始地址，因此进入点正是压缩 payload 偏移 0。

同一个 ``bzImage`` 还提供 64 位 boot protocol 入口，固定在 payload 起点加 ``0x200``。当前 GRUB 是 i386-pc 32 位 bootloader，所以不能直接使用那个入口；Linux 必须先从偏移 0 的 ``startup_32`` 自己开启 long mode。

第一件事仍是固定方向和中断状态
------------------------------

``startup_32`` 开头再次执行：

.. code-block:: asm

   cld
   cli

GRUB 已经提供 DF=0 和 IF=0，Linux 仍不依赖 bootloader 的善意，立即重新声明自己的前置条件。

``cld`` 保证后面的 ``rep stos`` 与 ``rep movs`` 按地址递增工作。

``cli`` 保证 Linux 尚未建立自己的 IDT 和中断处理路径时，不会被传统 PIC 或其他中断打断。

ESI 是此刻最重要的输入
----------------------

Linux/x86 32-bit Boot Protocol 只把少数寄存器定义为正式接口。其中：

::

   ESI = struct boot_params 的物理地址

GRUB 已在这块低端内存中写入：

* setup header 副本；
* ``cmd_line_ptr``；
* ``ramdisk_image`` 与 ``ramdisk_size``；
* E820 memory map；
* video/console 信息；
* bootloader ID 等字段。

``startup_32`` 在切换栈、重载 GDT 和开启 paging 的整个过程中都必须保住这个指针。后面的 64 位 startup 会把它扩展并保存到长期使用的寄存器中。

为什么先借用 boot_params.scratch 当 4 字节栈
--------------------------------------------

Linux 必须知道 compressed image 实际被 GRUB 放到了哪个物理地址。因为内核支持 relocatable，链接时地址不能直接代表运行时地址。

32 位 x86 没有 RIP-relative addressing。为了取得当前 ``EIP``，代码使用经典的 ``call``/``pop`` 技巧：

.. code-block:: asm

   leal (BP_scratch+4)(%esi), %esp
   call 1f
1: popl %ebp
   subl $rva(1b), %ebp

``call`` 会把下一条指令的运行时地址压栈，``popl %ebp`` 再把它取出。

问题是 Linux 此时还没有自己的栈。于是它暂时把 ``boot_params`` 中偏移 ``0x1e4`` 的 ``scratch`` 字段尾部当作 4 字节栈空间。这里只需要容纳 ``call`` 压入的一个返回地址。

减去标签 ``1`` 相对 ``startup_32`` 的链接偏移后：

::

   EBP = startup_32 的实际运行时物理地址

这个 EBP 成为 compressed image 内所有 ``rva(symbol)`` 引用的运行时基址。

``rva()`` 为什么贯穿整个早期汇编
--------------------------------

``head_64.S`` 定义：

.. code-block:: c

   #define rva(X) ((X) - startup_32)

所以：

::

   rva(X) + EBP = X 的当前运行时地址

compressed kernel 被链接为 PIE，且可能被 bootloader 放到不同物理地址。早期 32 位代码还不能依赖完整的动态重定位器；``rva()`` 明确使用符号相对入口的固定偏移，避免产生此时无法处理的运行时重定位。

Linux 立即换掉 GRUB 的 GDT
-------------------------

GRUB 已提供符合 boot protocol 的 flat GDT。Linux 仍建立自己的 descriptor table：

.. code-block:: asm

   leal rva(gdt)(%ebp), %eax
   movl %eax, 2(%eax)
   lgdt (%eax)

``gdt`` 前面带有一个 32 位 GDTR descriptor。descriptor 的 base 字段在链接时不能知道运行地址，所以 Linux 用 ``EBP`` 算出真实地址，再现场写入 descriptor 的 base 部分。

新 GDT 包含：

* ``__KERNEL32_CS``：32 位 code segment；
* ``__KERNEL_CS``：64 位 code segment，L bit 为 1；
* ``__KERNEL_DS``：flat data segment；
* 一个早期 TSS descriptor。

随后数据段寄存器全部改成 Linux 自己的 ``__BOOT_DS``/``__KERNEL_DS`` selector。

为什么还要执行一次 32 位 far return
-----------------------------------

仅 ``lgdt`` 不会刷新当前 ``CS`` 的 hidden descriptor cache。Linux 先建立正式 boot stack：

.. code-block:: asm

   leal rva(boot_stack_end)(%ebp), %esp

``BOOT_STACK_SIZE`` 在 x86-64 compressed kernel 中是 ``0x4000``，即 16 KiB。

然后：

.. code-block:: asm

   pushl $__KERNEL32_CS
   pushl $next_address
   lretl

这个 far return 在 **仍然是 32 位模式** 的前提下，把 ``CS`` 切换到 Linux 自己 GDT 的 32 位 code descriptor。

它还不是进入 long mode。此处只是先摆脱 GRUB 的 descriptor cache，确保后续修改 CR4、EFER 和 CR0 时运行在 Linux 自己定义的 32 位段环境中。

``verify_cpu`` 不是只检查一个 long-mode bit
-------------------------------------------

Linux 接着调用：

.. code-block:: asm

   call verify_cpu
   testl %eax, %eax
   jnz .Lno_longmode

``verify_cpu`` 成功返回 0，失败返回 1。它检查的链条包括：

#. CPU 是否支持 CPUID；
#. basic CPUID leaf 1 是否存在；
#. 内核要求的基础 feature bits 是否齐全；
#. extended CPUID ``0x80000001`` 是否存在；
#. long mode 等扩展 feature bits 是否齐全；
#. SSE 是否可用。

对部分旧 AMD CPU，它还会尝试通过 ``MSR_K7_HWCR`` 清除 SSE disable bit 后重新检查。对符合条件的 Intel CPU，代码会清除 ``IA32_MISC_ENABLE.XD_DISABLE``，让 NX/XD 能力不被固件关闭。

若验证失败，``.Lno_longmode`` 会进入永久 ``hlt`` 循环。64 位内核无法退回成 32 位内核继续启动。

EBX 不是最终内核入口，而是安全解压布局的关键
--------------------------------------------

验证 CPU 后，Linux计算一个临时 relocation base。

在 ``CONFIG_RELOCATABLE`` 下，它先把当前 load address ``EBP`` 向上按 boot header 中的 ``kernel_alignment`` 对齐；若结果低于 ``LOAD_PHYSICAL_ADDR``，则至少使用 ``LOAD_PHYSICAL_ADDR``。

随后执行：

.. code-block:: asm

   addl BP_init_size(%esi), %ebx
   subl $rva(_end), %ebx

可写成：

::

   EBX = aligned_output_base + init_size - compressed_image_memory_size

``init_size`` 是内核告诉 bootloader 和 compressed startup 的完整初始化空间需求。把 compressed image 临时移到这段 buffer 的高端，可以让解压输出从低端增长，而不提前覆盖尚未读取的压缩输入。

第三十二章中 GRUB 也使用同一个 ``init_size`` 为 initramfs 设置下界。两个不同执行者围绕同一字段完成了相互配合的内存布局：

* GRUB 保证 initramfs 在内核初始化区之外；
* Linux 把压缩输入安排到初始化 buffer 的安全高端。

开启 PAE 是进入 long mode 的先决条件
------------------------------------

Linux 读取 CR4，设置：

::

   CR4.PAE = 1

x86-64 long mode 的 paging 使用扩展页表项和 4 级或 5 级结构。即使物理内存没有超过 4 GiB，开启 long mode 前也必须启用 PAE paging format。

此时 paging 仍然关闭。设置 ``CR4.PAE`` 只是规定下一次打开 paging 时使用哪种页表格式。

最初页表为什么恰好需要 6 页
----------------------------

Linux 定义：

::

   BOOT_INIT_PGT_SIZE = 6 * 4096

用于最初 4 级 paging：

::

   1 页 PML4
   1 页 PDPT
   4 页 Page Directory

总计 6 页。

代码先把这 24 KiB 清零：

.. code-block:: asm

   rep stosl

然后建立三层有效结构；最底层直接使用 2 MiB huge page，不建立 4 KiB Page Table 层。

PML4 只使用第 0 项
------------------

PML4 第 0 项指向下一页的 PDPT：

::

   PML4[0] → PDPT

当前只需要覆盖低 4 GiB，没有建立内核最终使用的高半区映射。这是一张 compressed startup 的临时 identity map。

PDPT 为什么填四项
-----------------

每个 PDPT entry 覆盖 1 GiB。代码连续建立四项：

::

   PDPT[0] → PD0 → 0–1 GiB
   PDPT[1] → PD1 → 1–2 GiB
   PDPT[2] → PD2 → 2–3 GiB
   PDPT[3] → PD3 → 3–4 GiB

因此四个 Page Directory 一共覆盖 4 GiB 线性地址空间。

2048 个 2 MiB entry 怎样覆盖 4 GiB
----------------------------------

四个 Page Directory 各有 512 个 entry：

::

   4 × 512 = 2048 entries

每项映射 2 MiB：

::

   2048 × 2 MiB = 4 GiB

entry 初始值从 ``0x00000183`` 开始，每次物理地址增加 ``0x00200000``。

``0x183`` 中包含 present、writable、page-size 和 global 等位。page-size bit 表示这个 PDE 直接描述 2 MiB 页面，不再指向下一级 page table。

线性地址和物理地址使用相同数值，所以这是 identity mapping：

::

   virtual 0x00100000 → physical 0x00100000

这使当前 compressed code、boot_params、命令行、页表和 4 GiB 以下的 initramfs 在开启 paging 前后仍可用同一数值访问。

SEV 的 encryption bit 是条件分支
-------------------------------

若构建和运行环境启用了 AMD memory encryption，``get_sev_encryption_bit`` 会取得 C-bit 位置，并把对应高位加入页表项。

普通未启用 SEV 的 QEMU q35 路径中，encryption mask 为 0，页表项只包含普通物理地址和 flags。这个条件分支不改变主控制流结构。

CR3 指向新建的 PML4
-------------------

页表完成后：

.. code-block:: asm

   movl page_table_address, %cr3

由于当前代码仍在 32 位模式，页表必须位于 4 GiB 以下，CR3 的目标可以通过 32 位寄存器装入。

写 CR3 此刻还不会启用地址翻译，因为 ``CR0.PG`` 仍是 0。CPU 只是记住下一次开启 paging 时从哪里开始 page walk。

EFER.LME 只表示“允许进入”，还没有激活
-------------------------------------

Linux 读取 ``MSR_EFER``，设置：

::

   EFER.LME = 1

LME 是 Long Mode Enable。单独设置它不会立即让指令变成 64 位。

此时状态是：

::

   CR4.PAE = 1
   CR3     = early PML4
   EFER.LME = 1
   CR0.PG   = 0

CPU 仍执行 32 位指令。

Linux 还清空 LDT 并装入早期 TSS
------------------------------

代码执行：

.. code-block:: asm

   lldt 0
   ltr __BOOT_TSS

``lldt 0`` 把 LDTR 标记为无效，说明当前不使用 Local Descriptor Table。

``ltr`` 装入新 GDT 中的早期 TSS descriptor。compressed startup 还没有建立最终 per-CPU TSS，但进入 long mode 前先让 task register 处于 Linux 预期的有效状态。

真正激活 long mode 的是 CR0.PG
------------------------------

Linux 把 64 位入口的地址和 64 位 code selector 压到当前 mini stack：

.. code-block:: asm

   pushl $__KERNEL_CS
   pushl $startup_64_runtime_address

随后写入预定义 ``CR0_STATE``。其中最关键的变化是：

::

   CR0.PG = 1

因为 ``CR4.PAE`` 与 ``EFER.LME`` 已经就绪，打开 paging 会使 ``EFER.LMA`` 生效，处理器进入 long-mode active 状态。

不过当前 ``CS`` 仍指向 32 位 descriptor，其 L bit 为 0、D bit 为 1。因此 CPU 暂时运行在 **long mode 的 32 位 compatibility submode**，还没有开始执行 64 位指令。

最后一次 lret 才切进 64 位 code segment
--------------------------------------

栈上已经准备好：

::

   new CS  = __KERNEL_CS
   new RIP = startup_64

``lret`` 同时弹出目标 offset 和 code selector。

``__KERNEL_CS`` descriptor 的 L bit 为 1。装入它之后，CPU 从 compatibility mode 切换到真正的 64-bit mode，并从 compressed image 固定偏移 ``0x200`` 的：

::

   startup_64

开始执行。

这个切换不能用普通 near jump 完成。near jump 不改变 ``CS``，也就不能把 code-segment L bit 从 0 改成 1。

当前机器状态
------------

第三十四章结束在 ``startup_64`` 刚取得控制权：

* 当前执行者：Linux 6.12.95 compressed ``startup_64``；
* 当前主流程 CPU：BSP；
* CPU 模式：64 位 long mode；
* paging：开启；
* paging level：当前为 4 级初始页表；
* mapping：低 4 GiB identity mapped；
* page size：初始主体映射使用 2 MiB pages；
* ``CR4.PAE``：开启；
* ``EFER.LME`` / ``EFER.LMA``：开启；
* interrupts：关闭；
* boot_params 指针：仍由从 32 位入口带来的寄存器值保存；
* compressed image：尚未搬到安全解压位置；
* BSS：尚未清零；
* kernel payload：尚未解压；
* initramfs：尚未解析；
* 最终内核页表：尚未建立；
* ``start_kernel()``：距离当前仍很远。

下一段从 ``startup_64`` 第一条指令继续，追踪它怎样保存 boot_params、计算解压输出地址、处理 5-level paging/KASLR 需要、把 compressed image 向高端倒序复制、清 BSS，随后调用 ``extract_kernel()``。

资料
----

* `Linux 6.12.95：compressed startup_32 与 startup_64 <https://github.com/gregkh/linux/blob/v6.12.95/arch/x86/boot/compressed/head_64.S>`_
* `Linux 6.12.95：verify_cpu 的 long mode 与 SSE 检查 <https://github.com/gregkh/linux/blob/v6.12.95/arch/x86/kernel/verify_cpu.S>`_
* `Linux 6.12.95：BOOT_STACK_SIZE、BOOT_INIT_PGT_SIZE 与初始页表布局 <https://github.com/gregkh/linux/blob/v6.12.95/arch/x86/include/asm/boot.h>`_
* `Linux 6.12.95：Linux/x86 32-bit Boot Protocol <https://github.com/gregkh/linux/blob/v6.12.95/Documentation/arch/x86/boot.rst>`_
* `Linux 6.12.95：setup header 的 alignment、init_size 与 64 位标志 <https://github.com/gregkh/linux/blob/v6.12.95/arch/x86/boot/header.S>`_
