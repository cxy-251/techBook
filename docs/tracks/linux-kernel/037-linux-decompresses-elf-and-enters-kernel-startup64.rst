.. SPDX-License-Identifier: GPL-2.0

====================================================================
第三十七章：Linux 怎样解压 ELF 内核并进入正式 startup_64？
====================================================================

上一章结束时，compressed ``extract_kernel()`` 已经完成：

* ``boot_params`` 清洗；
* early console 与 RSDP 初始化；
* compressed boot heap 建立；
* 解压所需 ``needed_size`` 计算；
* 物理输出地址 ``output`` 选择；
* 虚拟运行地址 ``virt_addr`` 选择；
* 输出区的对齐和范围检查；
* 必要的 unaccepted memory 接受。

当前停在：

.. code-block:: c

   entry_offset = decompress_kernel(output, virt_addr, error);

本章从这条调用开始，追踪压缩流解码、ELF program header 搬运、运行时 relocation、compressed 环境清理，以及正式内核 ``arch/x86/kernel/head_64.S:startup_64`` 的第一轮页表修正。章节结束在控制权到达高半区 ``common_startup_64``。

``decompress_kernel()`` 是统一入口，不是固定某一种算法
------------------------------------------------------

Linux 可以在构建时选择多种 kernel compression format：

* gzip；
* bzip2；
* LZMA；
* XZ；
* LZO；
* LZ4；
* Zstd。

``arch/x86/boot/compressed/misc.c`` 根据 ``CONFIG_KERNEL_*`` 包含对应解压器源码，但它们向当前流程暴露统一接口：

.. code-block:: c

   __decompress(input_data, input_len,
                NULL, NULL,
                outbuf, output_len,
                NULL, error)

仓库固定了 Linux 版本和启动路径，但没有把一个具体 kernel compression config 当作跨机器不变事实。因此正文沿统一控制流解释；真正执行的 bitstream decoder 由该 ``bzImage`` 的构建配置决定。

输入、输出与运行区分别是什么
----------------------------

进入解压器时的主要变量是：

``input_data``
   compressed payload 在已经搬迁后的 compressed image 中的位置。

``input_len``
   压缩字节流长度。

``outbuf`` / ``output``
   上一章最终选择的物理解压目标。

``output_len``
   解压后文件数据与 relocation table 的总长度。

``kernel_total_size``
   正式内核 ``text + data + bss + brk`` 的运行时占用。

``virt_addr``
   正式内核预期采用的虚拟基址，用于 KASLR relocation 计算。

compressed image 已经被放在 ``output + init_size`` 附近的高端，所以解压结果从 ``output`` 向高地址增长时，不会在读取前覆盖压缩输入。

解压器自己的 malloc 从哪里来
----------------------------

``decompress_kernel()`` 先确认 compressed boot heap 已经建立：

.. code-block:: c

   if (!free_mem_ptr) {
       free_mem_ptr     = (unsigned long)boot_heap;
       free_mem_end_ptr = (unsigned long)boot_heap + sizeof(boot_heap);
   }

这里的 ``malloc()`` 只是解压算法使用的线性早期分配器。它不支持正式内核内存管理的完整语义，也不会成为后面的 slab allocator。

压缩字节流先被还原成临时 ELF 映像
--------------------------------

``__decompress()`` 把压缩数据写到 ``output``，长度上限为 ``output_len``。

这个输出尚不能直接视为“最终摆放好的运行中内核”。它首先是一份解压后的 ELF image，里面包含：

* ELF header；
* program header table；
* 各个 loadable segment 的文件内容；
* 附加在末尾的 relocation tables。

因此下一步不是立即跳到 ``output``，而是：

.. code-block:: c

   entry = parse_elf(outbuf);

先验证 ELF magic
----------------

``parse_elf()`` 把 ELF header 复制到局部变量，然后检查：

.. code-block:: text

   0x7f 'E' 'L' 'F'

如果 ``EI_MAG0..3`` 不匹配，compressed kernel 立即报错。一个成功解压但不是有效 ELF 的数据不能继续执行。

读取 program header table
-------------------------

函数根据：

.. code-block:: text

   e_phoff   program header table 在 ELF 中的偏移
   e_phnum   program header 数量

为 program headers 分配 compressed boot heap 内存，再把整张表复制出来。

这里先复制 header table，而不是直接在 ``output`` 中边遍历边搬 segment，是因为后续 ``memmove`` 可能让源区和目标区重叠，原地读取 program header 可能被自己覆盖。

只搬运 ``PT_LOAD`` segment
--------------------------

循环处理每个 program header：

.. code-block:: c

   switch (phdr->p_type) {
   case PT_LOAD:
       ...
       memmove(dest, output + phdr->p_offset, phdr->p_filesz);
       break;
   default:
       break;
   }

只有 ``PT_LOAD`` 描述真正需要出现在运行内存中的 segment。其他 ELF metadata 不会原样保留为正式内核运行区的一部分。

x86-64 还要求：

.. code-block:: text

   p_align % 2 MiB == 0

如果 load segment 的 alignment 不是 2 MiB 的整数倍，启动失败。这与早期 PMD 大页映射和内核物理对齐要求一致。

可重定位内核怎样计算每个 segment 目标
------------------------------------

对于 ``CONFIG_RELOCATABLE``：

.. code-block:: c

   dest = output + (phdr->p_paddr - LOAD_PHYSICAL_ADDR);

``p_paddr`` 是 ELF 链接时描述的物理布局；``LOAD_PHYSICAL_ADDR`` 是链接布局的基准。两者相减得到 segment 在内核物理映像中的 offset，再加本次实际 ``output``。

例如抽象表示：

.. code-block:: text

   linked segment p_paddr = LOAD_PHYSICAL_ADDR + 0x600000
   actual output          = 0x24000000

   dest = 0x24000000 + 0x600000

这样所有 segment 保持链接时的相对布局，整套映像可以整体移动到 KASLR 选中的物理位置。

``memmove`` 而不是 ``memcpy`` 的原因
-----------------------------------

segment 的源数据仍位于刚解压到 ``output`` 的临时 ELF buffer 内；目标也可能位于同一个 buffer 的另一处。两块范围可能重叠，所以必须使用 ``memmove``。

``p_filesz`` 表示文件实际携带的字节数。``p_memsz - p_filesz`` 对应的零初始化区域不会由这里复制文件数据；正式内核后续会按自己的 BSS 初始化路径处理。

ELF entry 先转换为相对 offset
-----------------------------

``parse_elf()`` 最终返回：

.. code-block:: c

   ehdr.e_entry - LOAD_PHYSICAL_ADDR

它没有直接返回链接期虚拟地址，也没有直接返回固定物理地址，而是返回入口相对 Linux 物理布局基准的 offset。

外层随后可以计算：

.. code-block:: text

   actual_entry = output + entry_offset

无论 ``output`` 是否经过物理 KASLR，入口都落在本次实际装入的正式内核映像内。

为什么 ELF 搬完还要处理 relocation
----------------------------------

物理 segment 布局正确并不代表内核中的所有绝对地址都正确。

正式内核代码和数据可能包含：

* 32 位绝对引用；
* inverse 32-bit relocation；
* 64 位绝对引用。

当物理基址或虚拟 KASLR offset 改变时，这些位置需要加减 delta。

compressed build 在解压 payload 末尾附加三组倒序 relocation table：

.. code-block:: text

   kernel data
   0
   64-bit relocation entries
   0
   inverse 32-bit relocation entries
   0
   32-bit relocation entries

``handle_relocations()`` 从 ``output + output_len`` 末端向前扫描。

物理 delta 与虚拟 delta
-----------------------

函数先计算物理装入变化：

.. code-block:: c

   delta = output - LOAD_PHYSICAL_ADDR;

又计算当前 self-map adjustment：

.. code-block:: c

   map = delta - __START_KERNEL_map;

对于 x86-64，真正应用到 64 位内核地址的 relocation delta 使用：

.. code-block:: c

   delta = virt_addr - LOAD_PHYSICAL_ADDR;

所以：

* ``output`` 决定正式映像放在哪个物理地址；
* ``virt_addr`` 决定链接期内核地址要偏移到哪个高半区虚拟位置；
* relocation table 指出哪些内存位置需要修改。

每个 relocation 目标都会检查是否落在正式内核允许的范围内。越界 relocation 被视为损坏映像或构建错误，启动立即停止。

``extract_kernel()`` 得到正式入口
---------------------------------

``decompress_kernel()`` 完成后返回 ``entry_offset``。``extract_kernel()`` 输出完成提示，然后撤销 compressed 阶段异常处理：

.. code-block:: c

   cleanup_exception_handling();

这是重要的边界。compressed stage1/stage2 IDT 只用于解压环境；正式内核将建立自己的 exception tables。旧 handler 不能继续被误认为正式内核异常基础。

如果 compressed 阶段忽略过 spurious NMI，此时会输出数量。

最后返回：

.. code-block:: c

   return output + entry_offset;

返回值进入 ``RAX``，它是解压后正式内核的真实物理入口地址。

compressed 汇编完成最后一次跳转
-------------------------------

回到 ``.Lrelocated``：

.. code-block:: asm

   movq %r15, %rsi
   jmp *%rax

跳转前：

.. code-block:: text

   RSI = boot_params physical address
   RAX = decompressed kernel entry physical address

使用 ``jmp`` 而不是 ``call``，表示 compressed 环境不期待正式内核返回。控制权从 ``arch/x86/boot/compressed`` 永久转移到解压后的 ``arch/x86/kernel``。

同名的正式 ``startup_64`` 取得控制权
------------------------------------

新的入口是：

.. code-block:: asm

   arch/x86/kernel/head_64.S:startup_64

它与第三十五章的 compressed ``startup_64`` 同名，但位于完全不同的二进制区域：

.. code-block:: text

   compressed startup_64
       负责搬迁、解压、ELF 与 relocation

   kernel startup_64
       负责正式内核页表、CPU 基础状态和高半区入口

此时 CPU 已经是 64 位 long mode，解压器提供的页表仍包含 identity mapping，``RSI`` 仍指向 ``boot_params``。

正式入口先保存 ``boot_params`` 并换栈
------------------------------------

代码执行：

.. code-block:: asm

   mov %rsi, %r15
   leaq __top_init_kernel_stack(%rip), %rsp

再次把 ``boot_params`` 放到 callee-saved ``R15``，然后切换到正式内核的初始栈。compressed ``boot_stack`` 从这里开始不再承担主流程栈职责。

建立最早期 GS base
------------------

正式内核 C 代码可能使用 stack canary 和 per-CPU 访问，因此入口写入 ``MSR_GS_BASE``：

.. code-block:: asm

   movl $MSR_GS_BASE, %ecx
   leaq INIT_PER_CPU_VAR(fixed_percpu_data)(%rip), %rdx
   movl %edx, %eax
   shrq $32, %rdx
   wrmsr

这里还没有完整 percpu allocator。``fixed_percpu_data`` 是 boot CPU 早期使用的固定区域，使最早的 C 调用具备最低限度的 GS-relative 环境。

正式 GDT/IDT 与 ``CS``
---------------------

入口调用：

.. code-block:: asm

   call startup_64_setup_gdt_idt

随后通过 ``lretq`` 重新装载 ``__KERNEL_CS``。原因与 compressed 阶段类似：当前 ``CS`` 的 cached descriptor 可能来自解压器 GDT，正式内核必须切换到自己构造的描述符表，确保后面的 IRET、异常和 privilege transition 基于正式内核定义。

再验证一次 CPU
--------------

正式入口再次调用 ``verify_cpu``。

compressed 阶段的验证确保解压环境可以进入 long mode；正式内核再次 sanitize CPU configuration，尤其确保 NX/SSE 等正式运行所需状态没有在交接或虚拟化环境中出现不一致。

``__startup_64()`` 修正正式内核页表
-----------------------------------

汇编准备：

.. code-block:: asm

   leaq _text(%rip), %rdi
   movq %r15, %rsi
   call __startup_64

参数是：

.. code-block:: text

   RDI = 正式内核 _text 当前物理/identity-mapped 地址
   RSI = boot_params

``__startup_64()`` 首先判断当前是否已经启用 5 级分页，并同步：

* ``__pgtable_l5_enabled``；
* ``pgdir_shift``；
* ``ptrs_per_p4d``；
* direct map、vmalloc、vmemmap 基址。

然后计算：

.. code-block:: c

   load_delta = physaddr - (_text - __START_KERNEL_map);
   phys_base  = load_delta;

``_text - __START_KERNEL_map`` 是内核按链接布局推导的默认物理位置。实际 ``physaddr`` 可能被物理 KASLR 改变，两者之差就是正式内核的 physical relocation delta。

该 delta 必须 2 MiB 对齐，否则函数进入不可恢复循环。前面所有 ``kernel_alignment`` 和 KASLR slot 规则最终都在这里得到硬验证。

修正高半区页表中的物理指针
--------------------------

正式内核静态页表在链接时含有默认物理地址。``__startup_64()`` 给以下结构中的物理 table pointer 加上 ``load_delta``：

* ``early_top_pgt``；
* 5 级分页时的 ``level4_kernel_pgt``；
* ``level3_kernel_pgt``；
* ``level2_fixmap_pgt``；
* ``level2_kernel_pgt`` 中实际覆盖 kernel image 的 PMD entries。

同时：

* 建立从当前物理地址执行到高虚拟地址切换所需的临时 identity mapping；
* 清除 kernel image 之前和之后无效的 PMD present bit；
* 只保留已被 firmware memory map 验证为内核映像占用的范围；
* 在 SME 条件路径中加入 memory-encryption mask。

为什么要清掉映像外的映射
------------------------

静态页表布局可能产生覆盖 kernel image 周围区域的宽泛 PMD entries。保留这些 present mapping 会允许 CPU speculative access 到 reserved physical region。

某些平台把对保留区的 speculative access 也视为硬件错误。因此 ``__startup_64()``：

.. code-block:: text

   映像之前  → clear present
   映像内部  → add load_delta
   映像之后  → clear present

这不是单纯“节约页表”，而是在正式内核运行前收紧可访问物理范围。

切换到 ``early_top_pgt``
------------------------

``__startup_64()`` 返回 SME modifier，汇编把它加入 ``early_top_pgt`` 的实际物理地址：

.. code-block:: asm

   leaq early_top_pgt(%rip), %rcx
   addq %rcx, %rax
   movq %rax, %cr3

此时 CPU 切换到正式内核修正后的 early page tables。identity mapping 仍暂时存在，以保证当前物理地址上的指令能够完成最后一次跳转。

第一次跳入内核高半区虚拟地址
----------------------------

入口最后执行间接跳转：

.. code-block:: asm

   jmp *0f(%rip)

   0:
       .quad common_startup_64

``common_startup_64`` 被链接成正式内核高半区虚拟地址。写入新的 ``CR3`` 后，这个虚拟地址已经可解析到刚解压的物理 kernel image。

这个跳转带来的变化是：

.. code-block:: text

   之前：在 identity mapping 下，用物理地址执行正式内核 startup_64
   之后：在正式 kernel mapping 下，用高半区虚拟地址执行 common_startup_64

这是真正从“解压器提供的临时地址空间”进入“正式内核虚拟地址空间”的控制权交接。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/head_64.S:common_startup_64``；
* CPU：BSP；
* 模式：64 位 long mode；
* interrupts：关闭；
* compressed payload：已解压；
* ELF magic 与 program headers：已验证；
* ``PT_LOAD`` segments：已搬到正式物理布局；
* KASLR relocation：已按实际物理/虚拟 delta 处理；
* compressed stage IDT：已撤销；
* ``RSI`` / ``R15``：继续携带 ``boot_params``；
* stack：已切到 ``__top_init_kernel_stack``；
* GS base：已指向 boot CPU 的 early fixed percpu data；
* 正式 GDT/IDT：已建立初始版本；
* ``phys_base``：已记录实际物理 relocation delta；
* ``CR3``：已切到修正后的 ``early_top_pgt``；
* 当前 RIP：已经是正式内核高半区虚拟地址；
* initramfs：仍只是 ``boot_params`` 指向的一段内存，尚未展开；
* ``start_kernel()``：尚未调用。

下一段从 ``common_startup_64`` 开始，继续建立 boot CPU 的 early percpu、清理 identity mapping、准备 ``initial_code``，并最终进入 ``x86_64_start_kernel()``。

资料
----

* `Linux 6.12.95 misc.c：decompress_kernel、parse_elf、handle_relocations 与 extract_kernel <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/misc.c>`_
* `Linux 6.12.95 compressed head_64.S：从 extract_kernel 返回值跳入正式内核 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/head_64.S>`_
* `Linux 6.12.95 kernel head_64.S：正式 startup_64 与 common_startup_64 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head_64.S>`_
* `Linux 6.12.95 head64.c：__startup_64 页表修正 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/head64.c>`_
* `Linux/x86 32-bit Boot Protocol：正式内核入口寄存器与分页要求 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/arch/x86/boot.rst>`_
