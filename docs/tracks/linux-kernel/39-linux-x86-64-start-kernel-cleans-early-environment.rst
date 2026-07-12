第三十九章：x86_64_start_kernel 怎样清理临时环境并保存启动数据？
================================================================

第三十八章结束时，正式内核汇编已经完成 CPU 0 的栈、GDT、GSBASE、early IDT、``EFER`` 和 ``CR0`` 设置，并通过：

.. code-block:: asm

   callq *initial_code(%rip)

进入第一个正式 C 入口：

.. code-block:: c

   x86_64_start_kernel(real_mode_data)

参数 ``real_mode_data`` 是 bootloader 传入的 ``boot_params`` 物理地址。函数虽然叫 ``start_kernel``，它还不是通用内核入口 ``init/main.c:start_kernel()``。它属于 x86-64 架构专用的最后清理阶段。

先把当前 ``CR4`` 状态记入 shadow
--------------------------------

函数首先调用：

.. code-block:: c

   cr4_init_shadow();

Linux 后续修改 ``CR4`` 时，不希望每次都把硬件寄存器当作普通变量随意读写。内核维护一份 per-CPU ``CR4`` shadow，统一追踪已经启用的功能位。

当前 CPU 已在汇编中整理过 ``PAE``、``PSE``、``PGE``、``LA57`` 等状态。这里把真实值同步进软件 shadow，使后续 ``cr4_set_bits()``、``cr4_clear_bits()`` 等操作有正确起点。

销毁早期 identity-map trampoline
--------------------------------

接下来执行：

.. code-block:: c

   reset_early_page_tables();

其核心是：

.. code-block:: c

   memset(early_top_pgt, 0, sizeof(pgd_t) * (PTRS_PER_PGD - 1));
   next_early_pgt = 0;
   write_cr3(__sme_pa_nodebug(early_top_pgt));

``early_top_pgt`` 最后一项保存正式内核高半区映射，前面的 entries 曾用于 identity mapping 和早期动态补页。

函数清零前 ``PTRS_PER_PGD - 1`` 项，只保留最后一个高半区 kernel mapping。随后重新写 ``CR3``，让 CPU 使用收紧后的页表。

因此这一步的真实含义是：

.. code-block:: text

   保留高半区正式内核映射
   → 删除低地址临时 identity map
   → 重置 early page-table 分配计数
   → 重新加载 CR3

从这一刻开始，内核不能再假设任意物理地址都能用相同数值作为虚拟地址访问。后续物理内存访问必须通过 direct map、fixmap 或专门映射。

同步 5 级分页的动态虚拟布局
---------------------------

若 compressed 阶段已经启用 5-level paging，函数把三个动态基址改成 L5 版本：

.. code-block:: c

   page_offset_base = __PAGE_OFFSET_BASE_L5;
   vmalloc_base     = __VMALLOC_BASE_L5;
   vmemmap_base     = __VMEMMAP_BASE_L5;

它们分别控制：

* 物理内存 direct map 的虚拟基址；
* ``vmalloc`` 区域基址；
* ``struct page`` 数组的 ``vmemmap`` 基址。

前面 compressed code 只决定是否启用 ``CR4.LA57``；这里正式内核把自己的地址空间布局变量同步到实际分页级数。

清除正式内核 BSS 与 brk
-----------------------

随后：

.. code-block:: c

   clear_bss();

它清零两个区域：

.. code-block:: c

   memset(__bss_start, 0, __bss_stop - __bss_start);
   memset(__brk_base, 0, __brk_limit - __brk_base);

``.bss`` 中的静态变量在 ELF 文件里通常不保存成片的零字节，只记录运行时需要的大小。解压器搬运 ``PT_LOAD`` segment 后，内核必须自己保证 BSS 初值为 0。

``brk`` 是最早期内核在完整内存分配器可用前预留的线性空间。把它清零避免使用到压缩目标区中残留的数据。

这也是为什么前面的汇编和解压代码不能随便把尚未清零的 BSS 变量当成 0。必须等到这里以后，正式内核的普通静态零初始化语义才可靠。

为什么还要单独清零 ``init_top_pgt``
-----------------------------------

函数继续执行：

.. code-block:: c

   clear_page(init_top_pgt);

``init_top_pgt`` 将用于后续正式 direct map 和内存初始化。它不是当前正在执行的 ``early_top_pgt``，所以可以安全清空。

源码要求这一步发生在 ``kasan_early_init()`` 之前，因为 KASAN 可能立即向该页表加入 shadow memory 映射。若先让 KASAN 写入，再清页表，刚建立的映射会被抹掉。

SME 早期初始化必须先于可能的 page fault
---------------------------------------

接着调用：

.. code-block:: c

   sme_early_init();

在启用 AMD Secure Memory Encryption 时，页表项中的物理地址需要携带 encryption mask。``sme_early_init()`` 可能修改 ``early_pmd_flags``，使后续动态建立的 PMD 带上正确 C-bit。

这必须发生在任何可能触发 early page fault 的操作之前。否则 ``do_early_exception()`` 临时补出的页表项可能缺少加密属性，导致同一物理页以不一致方式访问。

没有启用 SME 时，这条路径退化为空操作，但顺序仍然固定。

建立最早期 KASAN shadow
-----------------------

随后：

.. code-block:: c

   kasan_early_init();

KASAN 通过 shadow memory 记录普通内存字节的可访问状态。完整 shadow mapping 此时还不可能建立，因为伙伴分配器和完整页表体系尚未初始化。

``kasan_early_init()`` 先创建一个最小可运行环境，使接下来的早期 C 代码即使被 KASAN instrumentation 插桩，也不会因为 shadow 地址完全不存在而立刻 fault。

完成后，函数再刷新 global TLB：

.. code-block:: c

   __native_tlb_flush_global(this_cpu_read(cpu_tlbstate.cr4));

之所以放在 KASAN 之后，是因为某些 KASAN 配置会插桩 ``native_write_cr4()``；必须先让 shadow 可用，再执行这类被插桩的底层操作。

把 early IDT 换成正式早期 handler 表
-------------------------------------

函数调用：

.. code-block:: c

   idt_setup_early_handler();

第三十八章建立的 IDT 保证刚进入 C 前不会完全失去异常处理。这里进一步装入架构定义的 early handler 表，覆盖早期 exception vectors，并为后续页错误、调试异常、通用保护异常等建立更稳定的入口。

它仍然不是系统运行后的最终 IDT。完整 trap 和 IRQ 初始化要等 ``start_kernel()`` 后续的 ``trap_init()``、``init_IRQ()`` 等步骤。

TDX 平台识别为什么必须这么早
----------------------------

随后：

.. code-block:: c

   tdx_early_init();

TDX guest 对 CPUID、I/O、MSR 和部分异常的处理方式与普通裸机不同。后面的代码可能调用 ``cc_platform_has()`` 查询 confidential-computing 属性，因此必须先识别并建立 TDX 早期状态。

固定 QEMU q35 主线若未启用 TDX，这条路径不会改变普通启动流程，但正文保留它，因为它位于真实控制流中，并决定后续抽象接口能否安全使用。

把 bootloader 数据复制进内核自己的静态区
----------------------------------------

到目前为止，``real_mode_data`` 仍指向 GRUB 分配的低端 ``boot_params`` 页面。内核不能永久依赖这块外部内存。

``copy_bootdata()`` 执行：

.. code-block:: c

   memcpy(&boot_params, real_mode_data, sizeof(boot_params));
   sanitize_boot_params(&boot_params);

全局 ``boot_params`` 是正式内核自己的静态对象。复制完成后，固件内存图、initramfs 地址、RSDP、screen info、setup header 和其他启动字段都进入内核控制的存储区。

然后拼接命令行的高低地址字段：

.. code-block:: c

   cmd_line_ptr  = boot_params.hdr.cmd_line_ptr;
   cmd_line_ptr |= (u64)boot_params.ext_cmd_line_ptr << 32;

若地址非零，命令行被复制到：

.. code-block:: c

   boot_command_line[COMMAND_LINE_SIZE]

当前固定命令行因此从 GRUB 缓冲区进入内核静态数组：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

SME 条件路径会在复制前为 boot data 建立 decrypted mapping，复制完成后再移除，避免低端启动数据长期以错误的加密属性映射。

提前加载 BSP microcode
----------------------

接下来：

.. code-block:: c

   load_ucode_bsp();

微码更新可能修复 CPU errata，改变某些 feature bits 的可靠性，或影响后续 mitigation 与拓扑判断。因此 BSP 微码需要在大规模 CPU 特性初始化前尽早加载。

这里仅处理 boot CPU。其他 AP 在后续 bring-up 时走各自的 microcode 路径。

把高半区 kernel mapping 交给 ``init_top_pgt``
--------------------------------------------

函数最后执行：

.. code-block:: c

   init_top_pgt[511] = early_top_pgt[511];

前面 ``init_top_pgt`` 已清零。现在把 ``early_top_pgt`` 最后一项，即正式高半区 kernel mapping，复制过去。

这为后续从 early page table 过渡到更完整的 ``init_top_pgt`` 保留最关键的内核映射。此时还没有建立完整物理内存 direct map，只复制了让内核自身代码和数据继续可达的顶层入口。

进入 ``x86_64_start_reservations()``
-----------------------------------

最后调用：

.. code-block:: c

   x86_64_start_reservations(real_mode_data);

该函数同样声明为 ``__noreturn``。``x86_64_start_kernel()`` 不会返回，它把控制权交给下一层 x86 架构入口。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``x86_64_start_reservations()``；
* CPU：BSP / Linux CPU 0；
* 模式：64 位 long mode；
* interrupts：关闭；
* 临时低地址 identity mapping：已从 ``early_top_pgt`` 清除；
* BSS 与 early brk：已清零；
* ``init_top_pgt``：已清空并复制 kernel high mapping；
* SME early flags：条件初始化完成；
* KASAN early shadow：条件初始化完成；
* early IDT：已升级；
* TDX early state：条件初始化完成；
* ``boot_params``：已复制到内核全局对象；
* kernel command line：已复制到 ``boot_command_line``；
* BSP microcode：已执行早期加载；
* initramfs：地址仍记录在 ``boot_params``，尚未展开；
* ``start_kernel()``：尚未调用。

下一段从 ``x86_64_start_reservations()`` 开始，执行最早的平台 quirks，然后调用通用 ``start_kernel()``。进入 ``start_kernel()`` 后，正文只追它在 ``setup_arch()`` 之前建立的最早通用内核状态。

资料
----

* `Linux 6.12.95 head64.c：x86_64_start_kernel、clear_bss、copy_bootdata 与 reservations 入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head64.c>`_
* `Linux 6.12.95 head_64.S：common_startup_64 到 x86_64_start_kernel 的调用 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head_64.S>`_
* `Linux 6.12.95 kasan init：早期 shadow mapping <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/kasan_init_64.c>`_
* `Linux 6.12.95 microcode core：BSP 早期 microcode 加载 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/microcode/core.c>`_
* `Linux 6.12.95 IDT：early handler 安装 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/idt.c>`_