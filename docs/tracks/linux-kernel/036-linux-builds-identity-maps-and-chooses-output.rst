.. SPDX-License-Identifier: GPL-2.0

================================================================
第三十六章：Linux 怎样建立解压映射并选择正式内核的位置？
================================================================

上一章结束时，compressed kernel 已经搬到安全高端位置，CPU 跳入新副本中的：

.. code-block:: asm

   arch/x86/boot/compressed/head_64.S:.Lrelocated

此时：

* ``R15`` 保存 ``boot_params`` 地址；
* ``RBP`` 保存初步计算出的解压输出物理地址；
* compressed kernel 的代码和已初始化数据已搬迁；
* 当前栈也位于搬迁后的 compressed image；
* ``.bss`` 尚未清零；
* 页表仍主要继承前面的初始映射；
* 最终输出位置尚可能被 KASLR 修改；
* 解压器尚未开始读取 compressed payload。

本章从 ``.Lrelocated`` 开始，追踪 BSS、第二阶段 IDT、按需 identity mapping、``boot_params`` 清洗、早期控制台和 KASLR 选址。章节停在 ``decompress_kernel()`` 调用之前。

搬迁后第一件事是清空新副本的 ``.bss``
---------------------------------------

``.Lrelocated`` 的第一段代码是：

.. code-block:: asm

   xorl %eax, %eax
   leaq _bss(%rip), %rdi
   leaq _ebss(%rip), %rcx
   subq %rdi, %rcx
   shrq $3, %rcx
   rep stosq

上一章只复制到 ``_bss`` 之前，因为 ELF/BSS 语义规定这一区域在文件中不保存实际零字节，只记录内存长度。现在代码在新运行位置把：

.. code-block:: text

   [_bss, _ebss)

逐个 8 字节写零。

这里会初始化 compressed 启动环境中的全局状态，例如：

* boot allocator 指针；
* 页表分配计数；
* KASLR 候选区数组；
* compressed 阶段使用的各种临时标志。

某些必须跨越这次 BSS 清零保存的变量会被明确放在 ``.data``，例如 5 级分页状态和低端 trampoline 指针。

第二阶段 IDT 为什么在这里建立
----------------------------

BSS 清零后调用：

.. code-block:: asm

   call load_stage2_idt

前一章的 stage1 IDT 主要保证模式转换和 confidential-computing 早期检测期间发生异常时仍有最小处理入口。搬迁完成、BSS 可用之后，Linux 可以建立第二阶段 compressed-boot IDT。

它仍不是正式内核运行时的 IDT。它服务于：

* compressed 阶段页故障；
* NMI；
* SEV-ES ``#VC``；
* KASLR 扫描和解压期间可能发生的早期异常。

正式内核在后面还会重新建立自己的描述符表和异常入口。

``initialize_identity_maps()`` 不只是保留低 4 GiB
--------------------------------------------------

接下来汇编把 ``R15`` 作为第一个 C 参数：

.. code-block:: asm

   movq %r15, %rdi
   call initialize_identity_maps

上一章之前的页表由 compressed ``startup_32`` 快速建立，只用 6 页表和 2048 个 2 MiB PDE identity-map 低 4 GiB。它足够完成模式切换，但不一定覆盖：

* compressed image 被搬迁后的完整范围；
* ``boot_params``；
* command line；
* ``setup_data`` 链；
* KASLR 最终选择的高物理输出位置；
* 64 位 bootloader 可能放到 4 GiB 以上的数据。

``initialize_identity_maps()`` 因此建立一套可继续扩展的按需映射环境。

先接管当前 ``CR3``
------------------

函数读取当前 top-level page table：

.. code-block:: c

   top_level_pgt = read_cr3_pa();

如果当前 ``CR3`` 的下一级正是 compressed image 中的 ``_pgtable``，说明路径来自 ``startup_32``。最初的 ``BOOT_INIT_PGT_SIZE`` 已经被使用，函数从后面的页表缓冲区继续分配：

.. code-block:: c

   pgt_data.pgt_buf = _pgtable + BOOT_INIT_PGT_SIZE;
   pgt_data.pgt_buf_size = BOOT_PGT_SIZE - BOOT_INIT_PGT_SIZE;

如果入口来自其他 64 位 bootloader，当前 top-level table 结构可能不同，函数会从整个 ``_pgtable`` 缓冲区重新分配自己的顶级表。

x86-64 compressed 启动阶段为早期页表预留：

.. code-block:: text

   BOOT_PGT_SIZE = 32 × 4096 bytes

其中前 6 页已经足够建立上一章的低 4 GiB 映射，其余页用于 KASLR、boot parameters、command line 和最终输出区等后续映射。

按 2 MiB 边界添加 identity map
------------------------------

``kernel_add_identity_map(start, end)`` 会先把范围扩展到 PMD 边界：

.. code-block:: text

   start = round_down(start, 2 MiB)
   end   = round_up(end, 2 MiB)

然后调用通用的 ``kernel_ident_mapping_init()`` 建立页表。

本阶段的映射 flags 包含可执行的大页内核属性：

.. code-block:: c

   __PAGE_KERNEL_LARGE_EXEC | sme_me_mask

这里仍以 2 MiB 大页为主，目的是用很少的页表覆盖启动期需要访问的物理范围。

明确映射四类关键数据
--------------------

``initialize_identity_maps()`` 主动加入：

#. compressed kernel 自身 ``[_head, _end)``；
#. 一个完整的 ``struct boot_params``；
#. command line 所在范围；
#. ``boot_params.hdr.setup_data`` 单链表中的每个节点及其 payload。

源码调用关系是：

.. code-block:: c

   kernel_add_identity_map((unsigned long)_head,
                           (unsigned long)_end);

   kernel_add_identity_map((unsigned long)boot_params_ptr,
                           (unsigned long)(boot_params_ptr + 1));

   kernel_add_identity_map(cmdline,
                           cmdline + COMMAND_LINE_SIZE);

Linux 不能只依赖“compressed 代码恰好访问到哪里，哪里就应该已经映射”。解压后的正式内核会继续读取 ``boot_params`` 和命令行，所以必须在交接前显式保证这些物理地址有 identity mapping。

遍历 ``setup_data`` 时，每个节点范围是：

.. code-block:: text

   [node, node + sizeof(struct setup_data) + node->len)

链表可以携带扩展 boot protocol 数据，例如 DTB、EFI、indirect setup data 或平台专用信息。

最后切换到扩展后的页表
----------------------

映射建立完成后执行：

.. code-block:: c

   write_cr3(top_level_pgt);

写 ``CR3`` 同时切换当前页表并刷新相关 TLB 状态。此后 compressed 启动环境使用的是可继续按需扩展的页表，而不再只是上一章那张固定低 4 GiB 快速映射。

对于 SEV-SNP，函数还会在切换后检查 guest/hypervisor feature compatibility。这属于条件路径。

进入 ``extract_kernel()``
-------------------------

汇编接着准备两个参数：

.. code-block:: asm

   movq %r15, %rdi
   movq %rbp, %rsi
   call extract_kernel

按照 x86-64 C ABI：

.. code-block:: text

   RDI = boot_params
   RSI = 初步解压输出地址

C 函数原型是：

.. code-block:: c

   void *extract_kernel(void *rmode, unsigned char *output)

``rmode`` 这个历史名称表示 real-mode data/zero page，并不意味着 CPU 回到了 real mode。当前 CPU 仍在 64 位 long mode。

把 ``boot_params`` 固定为 compressed 阶段全局入口
--------------------------------------------------

函数首先执行：

.. code-block:: c

   boot_params_ptr = rmode;

后面的 command-line parser、ACPI、KASLR、E820 和 early console 都通过这个指针访问 bootloader 提供的数据。

随后清除仅供内核内部使用的 ``KASLR_FLAG``：

.. code-block:: c

   boot_params_ptr->hdr.loadflags &= ~KASLR_FLAG;

这个 bit 不能无条件相信 bootloader。只有 compressed kernel 真正执行了自己的 KASLR 决策后，才会重新设置它。

清洗 bootloader 提供的参数
--------------------------

``sanitize_boot_params()`` 根据 setup header 中的 sentinel、协议版本和字段边界处理 ``boot_params``。

原因是 ``boot_params`` 是 bootloader 与内核之间的二进制 ABI：

* 新内核可能理解比旧 bootloader 更多的字段；
* 某些 bootloader 可能没有把全部扩展区域清零；
* 无效的旧数据不能直接当成可信指针或计数使用。

GRUB 前面已经把参数页清零并填写支持字段，但 Linux 仍要在自己的信任边界内再次检查。

建立 compressed 阶段控制台
---------------------------

``extract_kernel()`` 根据 ``screen_info`` 判断文本显存和 CRT controller 端口：

.. code-block:: text

   mono text mode : video memory 0xb0000, ports 0x3b4/0x3b5
   color text mode: video memory 0xb8000, ports 0x3d4/0x3d5

然后初始化默认 port-I/O 操作、检测 TDX 条件路径，并调用 ``console_init()``。

固定 GRUB 命令行包含：

.. code-block:: text

   console=ttyS0

这并不自动等同于 compressed 阶段一定输出完整日志；early serial 是否启用还取决于内核构建配置和 early console 解析。``console=ttyS0`` 主要供后续正式内核 console 选择使用。

重新确认 RSDP
------------

早期控制台可用后，compressed kernel 调用：

.. code-block:: c

   boot_params_ptr->acpi_rsdp_addr = get_rsdp_addr();

GRUB 可能已经传入 RSDP 地址，但 Linux compressed 阶段会根据自己的 ACPI 查找逻辑保存结果。把这个动作放在控制台初始化之后，是为了在 ACPI 解析出错时能够输出调试信息。

建立 boot heap
--------------

compressed 解压器使用静态数组：

.. code-block:: c

   static u8 boot_heap[BOOT_HEAP_SIZE];

并设置：

.. code-block:: c

   free_mem_ptr     = boot_heap;
   free_mem_end_ptr = boot_heap + BOOT_HEAP_SIZE;

``BOOT_HEAP_SIZE`` 随压缩算法而变化。例如 Zstd 需要更大的上下文，因此为其保留约 192 KiB；多数其他配置使用较小的 64 KiB heap。它不是正式内核的 slab、buddy allocator 或 ``memblock``。

计算输出区真正需要的长度
------------------------

内核计算：

.. code-block:: c

   needed_size = max(output_len, kernel_total_size);
   needed_size = ALIGN(needed_size, MIN_KERNEL_ALIGN);

``output_len``
   compressed payload 解压后的文件长度，其中还包括附加 relocation table。

``kernel_total_size``
   正式内核的 ``text + data + bss + brk`` 运行时总占用范围。

选择二者较大值，是因为某些构建中“文件解压长度”和“最终运行内存长度”没有固定大小关系。

x86-64 再把结果按 ``MIN_KERNEL_ALIGN`` 对齐；当前最小值是 2 MiB。

KASLR 必须避开哪些区域
----------------------

然后调用：

.. code-block:: c

   choose_random_location(input_data, input_len,
                          &output, needed_size,
                          &virt_addr);

如果内核没有启用 ``CONFIG_RANDOMIZE_BASE``，``misc.h`` 把它编译成空函数，``output`` 与 ``virt_addr`` 保持初始值。

如果构建启用 KASLR，并且命令行没有 ``nokaslr``，函数会重新设置：

.. code-block:: c

   boot_params_ptr->hdr.loadflags |= KASLR_FLAG;

当前固定命令行没有 ``nokaslr``。是否真正随机化仍由固定 ``bzImage`` 的构建配置和可用内存决定。

物理 KASLR 不能只随机挑一个看似空闲的地址。它至少要避开：

* 当前 compressed image 及其 ``init_size`` 运行区；
* initramfs；
* kernel command line；
* ``boot_params``；
* 每个 ``setup_data`` 节点；
* 命令行 ``mem=``、``memmap=`` 排除区域；
* 非 E820 RAM；
* 无法容纳完整 ``needed_size`` 的碎片区；
* 不满足 ``CONFIG_PHYSICAL_ALIGN`` 的地址。

固定路径是 legacy BIOS，因此 KASLR 主要扫描 GRUB 传入的 E820 RAM entries。EFI 路径会优先使用 EFI memory map。

候选地址不是按字节随机
----------------------

每个可用 region 被切成以 ``CONFIG_PHYSICAL_ALIGN`` 为步长的 slot：

.. code-block:: text

   slot_count = 1 + (region_size - needed_size) / CONFIG_PHYSICAL_ALIGN

所有候选 slot 汇总后，用启动熵选择其中一个。熵来源会混合构建字符串、``boot_params``、架构随机源等；具体来源取决于 CPU 和构建配置。

物理随机化的最低搜索地址是：

.. code-block:: text

   min_addr = ALIGN(min(initial_output, 512 MiB), CONFIG_PHYSICAL_ALIGN)

选中后：

.. code-block:: text

   output = random physical slot

x86-64 还独立选择虚拟 KASLR offset：

.. code-block:: text

   virt_addr = LOAD_PHYSICAL_ADDR + N × CONFIG_PHYSICAL_ALIGN

并要求 ``virt_addr + needed_size`` 不越过 ``KERNEL_IMAGE_SIZE`` 规定的内核映射窗口。

物理位置与虚拟位置为什么可以不同
--------------------------------

``output`` 是解压后 ELF segments 实际落入的物理地址。

``virt_addr`` 参与 relocation adjustment，决定正式内核链接地址对应的运行时虚拟偏移。

所以 KASLR 可以同时随机化：

* 物理加载位置；
* 内核高半区虚拟基址。

后面的 ``handle_relocations()`` 会使用两者之间的 delta 修正内核内嵌地址。

选择后必须再次做硬检查
----------------------

``extract_kernel()`` 检查：

* ``output`` 按 ``MIN_KERNEL_ALIGN`` 对齐；
* ``virt_addr`` 按 ``MIN_KERNEL_ALIGN`` 对齐；
* 输出范围没有超过内核映射窗口；
* non-relocatable kernel 的虚拟地址没有被改变；
* compressed boot heap 地址处于架构允许范围。

这些检查不是调试提示，而是失败就停止启动的硬约束。错误输出位置会导致页表无法覆盖、ELF segment 错位或 relocation 写到错误地址。

unaccepted memory 条件路径
--------------------------

某些 confidential-computing 平台会把一部分 RAM 标为 unaccepted。compressed kernel 在真正写入输出区前调用：

.. code-block:: c

   if (init_unaccepted_memory())
       accept_memory(__pa(output), needed_size);

普通 QEMU q35 路径通常不会进入该分支。它被保留在控制流中，因为输出区是否“属于 RAM”与 CPU 是否允许立即访问并不是同一件事。

当前机器状态
------------

本章结束在：

.. code-block:: c

   entry_offset = decompress_kernel(output, virt_addr, error);

调用尚未执行。

此刻：

* 当前执行者：Linux compressed ``extract_kernel()``；
* CPU：BSP；
* 模式：64 位 long mode；
* paging：开启；
* compressed ``.bss``：已清零；
* stage2 IDT：已建立；
* compressed image、``boot_params``、command line 与 ``setup_data``：已建立 identity mapping；
* ``CR3``：已切换到可扩展 early identity tables；
* ``boot_params``：已清洗；
* early console：已初始化到构建和平台允许的程度；
* RSDP：已重新查找并保存；
* boot heap：已建立；
* ``needed_size``：已计算并按 2 MiB 对齐；
* ``output`` / ``virt_addr``：已通过固定地址或 KASLR 路径确定；
* initramfs：仍原样保留，未解析；
* compressed payload：尚未解压；
* ELF program headers：尚未解析；
* 正式内核入口：尚未得到。

下一章从 ``decompress_kernel()`` 开始。

资料
----

* `Linux 6.12.95 head_64.S：.Lrelocated、initialize_identity_maps 与 extract_kernel 调用 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/head_64.S>`_
* `Linux 6.12.95 ident_map_64.c：compressed 阶段按需 identity mapping <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/ident_map_64.c>`_
* `Linux 6.12.95 misc.c：extract_kernel 前半段 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/misc.c>`_
* `Linux 6.12.95 kaslr.c：物理与虚拟 KASLR 候选选择 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/kaslr.c>`_
* `Linux 6.12.95 misc.h：CONFIG_RANDOMIZE_BASE 关闭时的空实现 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/misc.h>`_
