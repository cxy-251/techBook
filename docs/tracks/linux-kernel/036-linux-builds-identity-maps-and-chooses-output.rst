.. SPDX-License-Identifier: GPL-2.0

================================================================
第三十六章：Linux 怎样建立解压映射并选择正式内核的位置？
================================================================

第035章结束在BSP / CPU0跳入 ``B`` 副本的 ``.Lrelocated``。CPU仍处于64-bit long mode，
IF与DF为0；``R15=Z``、``RBP=O0``、``RBX=B``，stack与GDTR也已经使用 ``B`` 地址域。代码和
已初始化data完成搬迁，但compressed BSS尚未清零，stage1 IDT还没有page-fault handler，
KASLR也尚未决定最终输出位置。

本章沿固定Linux 7.2-rc1的 ``.Lrelocated → initialize_identity_maps() →
extract_kernel()`` 继续，停在：

.. code-block:: c

   entry_offset = decompress_kernel(output, virt_addr, error);

调用即将发生而尚未发生的边界。为区分初步值与最终值，再定义：

::

   O0 = startup_64计算并通过RBP传入的初步解压物理基址
   O  = choose_random_location返回后的最终物理解压基址
   V  = 正式内核用于relocation的虚拟位置量
   D  = 解压与运行区都能容纳所需的对齐长度needed_size

固定commit没有build ``.config``，所以KASLR、compression、ACPI、early printk和confidential
computing的config分支仍须保留；legacy GRUB handoff与固定command line能够排除的runtime
分支则直接排除。

新副本先把整个compressed BSS清零
----------------------------------

``.Lrelocated`` 第一段固定汇编是：

.. code-block:: asm

   xorl %eax, %eax
   leaq _bss(%rip), %rdi
   leaq _ebss(%rip), %rcx
   subq %rdi, %rcx
   shrq $3, %rcx
   rep stosq

第035章只复制 ``[startup_32,_bss)``。现在CPU在 ``B`` 取指，RIP-relative地址自然落到新副本，
``rep stosq`` 精确清零 ``[_bss,_ebss)``。linker把 ``_ebss`` 按8-byte对齐，故计数不会留下
零散尾部。

这里清的是compressed启动环境自己的BSS，例如全局allocator状态、page-table bookkeeping和
临时数组；不是解压后正式内核的BSS。``.data`` 中需要跨搬迁保留的五级分页变量、
``trampoline_32bit`` 等不在清零范围；位于 ``_ebss`` 之后的 ``.pgtable`` NOBITS区也不在该
范围，第034—035章已经在其中建立并可能切换了页表。

stage2 IDT安装 ``#PF``、NMI与条件 ``#VC``
-------------------------------------------

BSS可用后，汇编调用 ``load_stage2_idt()``。固定实现重新把IDT descriptor指向 ``B`` 副本中的
``boot_idt``，然后无条件安装：

::

   #PF -> boot_page_fault
   NMI -> boot_nmi_trap

若build启用 ``CONFIG_AMD_MEM_ENCRYPT``，且 ``sev_status`` 表明相应guest需要第二阶段 ``#VC``，
还会安装 ``boot_stage2_vc``；否则该vector被清空。最后 ``lidt`` 发布新表。这个动作没有执行
``sti``，IF继续为0；NMI和同步page fault仍可进入各自trap gate。

``#PF`` handler为何是identity map的一部分
--------------------------------------------

``boot_page_fault`` 保存通用寄存器并调用 ``do_boot_page_fault(regs,error_code)``。C handler
读取CR2，把fault address向下按2 MiB对齐。若错误码表示present-page protection fault、user
fault或reserved-bit fault，或者地址命中未就绪的SEV GHCB page，它不会尝试掩盖错误，而是
打印诊断并停止。

只有“supervisor访问一个尚未present的普通地址”才进入恢复路径：

.. code-block:: c

   address &= PMD_MASK;
   end = address + PMD_SIZE;
   kernel_add_identity_map(address, end);

handler为CR2周围一个2 MiB范围追加identity map，``iretq`` 后重试原指令。NMI handler则只递增
``spurious_nmi_count``，直到解压结束前统一检查。由此，后续代码可以访问尚未被初始页表显式
覆盖的高物理地址，而不是要求第035章预先猜出KASLR会选择哪里。

``initialize_identity_maps()`` 接续而不是盲目重建当前页表
------------------------------------------------------------

汇编以 ``RDI=R15=Z`` 调用 ``initialize_identity_maps()``。函数先从 ``physical_mask`` 去掉
``sme_me_mask``，再初始化mapping参数：页表页由 ``alloc_pgt_page`` 从compressed ``.pgtable``
区取得，普通mapping使用 ``__PAGE_KERNEL_LARGE_EXEC | sme_me_mask``，中间table使用
``_KERNPG_TABLE``。

它读取当前CR3得到 ``top_level_pgt``，再检查：

.. code-block:: c

   p4d_offset((pgd_t *)top_level_pgt, 0) == (p4d_t *)_pgtable

当前确实来自第034章的 ``startup_32``：保持4-level时CR3本身就是 ``_pgtable``；切到5-level时
CR3是 ``top_pgtable``，但其第0项仍指向 ``_pgtable``。两种runtime结果都满足该条件。因此函数
保留已经承载低4 GiB mapping的前六页，只清零并从剩余空间继续分配：

::

   pgt_buf      = _pgtable + BOOT_INIT_PGT_SIZE
   pgt_buf_size = BOOT_PGT_SIZE - BOOT_INIT_PGT_SIZE
                = (32-6) * 4096

固定源码还支持由64位bootloader带着外部页表直接进入的情况；若检查不匹配，它会清零整个32页
buffer并在其中分配新的top-level table。那是同一函数的替代入口，不是当前32位GRUB路径。

显式identity-map四类交接对象
----------------------------

``kernel_add_identity_map(start,end)`` 先把范围向外扩到2 MiB PMD边界，再调用
``kernel_ident_mapping_init()``。``initialize_identity_maps()`` 主动添加：

#. 当前relocated compressed映像 ``[_head,_end)``，即 ``B`` 副本连同其运行空间；
#. ``Z`` 处一个完整 ``struct boot_params``；
#. ``get_cmd_line_ptr()`` 返回地址起的 ``COMMAND_LINE_SIZE=2048`` bytes；
#. ``boot_params.hdr.setup_data`` 链中每个header与 ``len`` bytes payload。

命令行实际字符串比2048 bytes短，但解压后的正式内核需要继续访问boot protocol规定的整个
buffer边界，所以这里显式映射2048 bytes，不只映射到第一个NUL。

setup_data遍历也解释了stage2 ``#PF`` 为什么必须先装好：链节点本身可能位于当前页表尚未覆盖
的区域，首次解引用可以先fault-in对应2 MiB范围，再由循环显式保证完整node payload的mapping。

函数随后调用条件性的 ``sev_prep_identity_maps(top_level_pgt)``，写CR3发布扩展后的table，并在
相应build/runtime下执行 ``snp_check_features()``。写CR3完成后，当前root仍可被后续
``kernel_add_identity_map`` 原地扩展。

这里没有预先显式映射initramfs或最终 ``O``
--------------------------------------------

固定函数的显式列表里没有 ``ramdisk_image/ramdisk_size``，也没有尚未产生的KASLR output。
这不是遗漏：initramfs由解压后的正式内核以后处理；compressed阶段选择或写入高地址 ``O`` 时，
stage2 non-present ``#PF`` handler可以按访问需要追加mapping。

因此本章结束时不能笼统写成“initramfs和所有候选输出区都已映射”。如果 ``O`` 仍在第034章
覆盖的低4 GiB，访问直接命中；如果KASLR把它选到当前未映射的更高RAM，下一章解压器首次写入
会触发 ``#PF``，添加一个2 MiB identity range并重试。显式交接mapping与按需fault-in是两条
不同机制。

汇编以 ``extract_kernel(Z,O0)`` 进入C环境
------------------------------------------

identity maps准备完成后，``.Lrelocated`` 执行：

.. code-block:: asm

   movq %r15, %rdi
   movq %rbp, %rsi
   call extract_kernel

x86-64 C ABI给出：

::

   rmode  = Z
   output = O0

参数名 ``rmode`` 是boot protocol历史名称，不表示CPU回到了real mode。CPU仍在BSP / CPU0的
64-bit long mode，使用compressed boot stack；没有task、scheduler或普通内核allocator。

先重建全局参数指针并撤销不可信KASLR状态
------------------------------------------

``extract_kernel()`` 首先令 ``boot_params_ptr=rmode``。第035章
``configure_5level_paging()`` 曾设置当前副本的同名全局，但该变量属于BSS，没有被倒序复制，且
刚在 ``B`` 中清零；所以这里必须重新发布 ``Z``。

随后按固定顺序：

.. code-block:: c

   boot_params_ptr->hdr.loadflags &= ~KASLR_FLAG;
   parse_mem_encrypt(&boot_params_ptr->hdr);
   sanitize_boot_params(boot_params_ptr);

KASLR bit只允许由本次compressed内核自己的选址结果设置，不能继承loader或旧内核残值。当前
command line没有 ``mem_encrypt=on/off``，所以 ``parse_mem_encrypt`` 不改变相应xloadflag；
``sanitize_boot_params`` 再次按sentinel与protocol规则清洗外部ABI数据。这是搬迁后第二次调用，
不是第一次。

early console先区分video、port-I/O与confidential guest
-------------------------------------------------------

函数根据 ``screen_info.orig_video_mode`` 选择monochrome ``0xb0000/0x3b4`` 或color
``0xb8000/0x3d4``，保存行列数，然后依次：

::

   init_default_io_ops()
   early_tdx_detect()
   early_sev_detect()
   console_init()

TDX检测必须先于console初始化，才能在相应guest中改用paravirtualized port I/O；SEV-ES/SNP
路径会禁止不受支持的视频MMIO输出。两者都依build和runtime guest类型，不因“QEMU q35”四字
自动成立。

``console_init()`` 本身只有 ``CONFIG_EARLY_PRINTK`` build才有实质实现。更重要的是，固定
compressed parser识别 ``earlyprintk=...`` 或 ``console=uart8250,io,...`` /
``console=uart,io,...``，并不把普通 ``console=ttyS0`` 当作本阶段serial初始化请求。本项目的
固定command line只有：

::

   BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0

所以即使build含 ``CONFIG_EARLY_PRINTK``，这里也不会仅凭 ``console=ttyS0`` 设置
``early_serial_base``。该参数主要供正式内核后续console选择；compressed debug输出是否可见还
受 ``CONFIG_X86_VERBOSE_BOOTUP``、video state和其他build条件控制。

RSDP查找在console准备之后发生
-------------------------------

源码接着写：

.. code-block:: c

   boot_params_ptr->acpi_rsdp_addr = get_rsdp_addr();

若build不含 ``CONFIG_ACPI``，inline helper直接返回0。若包含ACPI，fixed helper先保留
``boot_params`` 中已有的非零地址，否则尝试EFI config table，最后扫描EBDA与
``0xe0000..0xfffff`` 的legacy BIOS窗口。

当前i386-pc handoff没有EFI loader signature，GRUB路径也没有交付EFI config table，因此EFI
分支不能成功；在ACPI build中，现有字段若为0就落到SeaBIOS RSDP的legacy scan。把动作放到
``console_init`` 之后，只保证解析诊断有机会输出，不保证当前config一定打印任何文字。

compressed heap大小由compression build决定
--------------------------------------------

``boot_heap`` 是compressed映像内的静态数组。RSDP步骤后，函数设置：

.. code-block:: c

   free_mem_ptr     = boot_heap;
   free_mem_end_ptr = boot_heap + BOOT_HEAP_SIZE;

固定源码的build分支是：

::

   CONFIG_KERNEL_BZIP2 : 0x400000
   CONFIG_KERNEL_ZSTD  : 0x30000
   other compressors   : 0x10000

仓库commit没有确定最终 ``CONFIG_KERNEL_*``，所以不能选定其中一个数字。这个heap只服务于
compressed解析、KASLR与解压算法；它不是memblock、buddy或slab。``decompress_kernel()``
稍后还会在指针为0时提供同一heap的fallback，但当前路径已经在这里初始化。

``D`` 同时覆盖解压文件长度和正式运行跨度
------------------------------------------

源码计算：

.. code-block:: c

   needed_size = max_t(unsigned long, output_len, kernel_total_size);
   needed_size = ALIGN(needed_size, MIN_KERNEL_ALIGN);

在x86-64固定源码中 ``MIN_KERNEL_ALIGN=PMD_SIZE=2 MiB``，所以：

::

   D = ALIGN_UP(max(output_len,kernel_total_size),2 MiB)

``output_len`` 是解压出的文件数据连同relocation table所需长度；``kernel_total_size`` 是正式
内核 ``text/data/bss/brk`` 的运行跨度。两者没有固定大小关系，选较大者才能既容纳解压写入，
又保证ELF搬运后的运行对象完整。2 MiB向上对齐还让KASLR验证整个PMD mapping覆盖的是可用RAM，
不会只检查真实尾字节而跨进reserved区。

KASLR关闭与开启是两套可验证结果
---------------------------------

进入选择前：

::

   output    = O0
   virt_addr = L
   KASLR_FLAG = 0

若build没有 ``CONFIG_RANDOMIZE_BASE``，``choose_random_location()`` 是空inline，结果保持：

::

   O = O0
   V = L

若build启用KASLR，函数先查 ``nokaslr``。固定command line没有该参数，所以它设置
``KASLR_FLAG``，建立物理avoid ranges并尝试物理与虚拟随机化。固定commit与命令行仍不足以
判断build选了哪套结果，故本章保留二者，不用“当前一定随机”替代缺失 ``.config``。

物理KASLR先固定不可覆盖的对象
--------------------------------

启用路径调用 ``mem_avoid_init(input_data,input_len,O0)``。固定实现记录：

* 从relocated compressed ``input_data`` 到 ``O0+I`` 的ZO解压运行区；
* ``R`` 起的 ``N`` 个initramfs有效bytes；
* command line实际NUL结束长度；
* ``Z`` 处完整 ``boot_params``；
* 最多四个 ``memmap=`` 声明的不可用range或由 ``mem=/memmap=`` 收紧的上限；
* 在候选overlap检查中动态遍历所有setup_data node及合法indirect payload。

当前command line没有 ``mem=``、``memmap=``、``nokaslr`` 或hugepage预留参数。initramfs虽然未被
identity-map，也必须作为物理选址avoid range保留；“KASLR不能覆盖它”和“compressed代码现在
不访问它”是两件不同的事。

当前是legacy BIOS handoff，没有EFI memory map；也没有KEXEC handover setup_data可提供KHO
scratch区域。因此物理slot扫描落到GRUB交付的E820 entries，只接受 ``E820_TYPE_RAM``。每段先
截到memory limit、扣除avoid overlap，再按 ``CONFIG_PHYSICAL_ALIGN`` 向上对齐，并且只有能
完整容纳 ``D`` 的range才贡献slot。

物理与虚拟随机选择彼此独立
----------------------------

物理搜索下界精确为：

::

   minimum = ALIGN_UP(min(O0,512 MiB),CONFIG_PHYSICAL_ALIGN)

候选slot以 ``CONFIG_PHYSICAL_ALIGN`` 为步长汇总，再由 ``kaslr_get_random_long("Physical")``
选一个。如果没有合法slot，函数只警告“Physical KASLR disabled”，``output`` 保持 ``O0``；它
不会因此清掉先前设置的KASLR flag，也不会跳过后面的虚拟选择。

x86-64随后在从 ``L`` 开始、能够容纳 ``D`` 且不越过 ``KERNEL_IMAGE_SIZE`` 的窗口中，按同一
build alignment选择独立 ``virt_addr``：

::

   V = L + n * CONFIG_PHYSICAL_ALIGN

因此启用KASLR时可能出现“物理仍为 ``O0``、虚拟offset已随机”的成功结果。``O`` 是ELF
segments实际写入的物理位置；``V`` 只进入后续64位relocation delta，不能把两者合并成一个
“内核地址”。

选址后的检查是硬失败边界
--------------------------

``choose_random_location()`` 返回后，``extract_kernel()`` 验证：

* ``O`` 按 ``MIN_KERNEL_ALIGN`` 对齐；
* ``V`` 按 ``MIN_KERNEL_ALIGN`` 对齐；
* compressed ``boot_heap`` 地址不高于 ``0x3fffffffffff``；
* ``V+D`` 不超过 ``KERNEL_IMAGE_SIZE``；
* non-relocatable build中 ``V`` 仍等于 ``L``。

任一条件失败都会进入 ``error()``，不是可以继续的warning。注意源码第三项实际检查局部
``heap`` 指针，虽然error文字写的是destination；正文按表达式记录，不把它改写成对 ``O`` 的
另一项上界检查。

legacy BIOS路径不会接受unaccepted memory
------------------------------------------

打印“Decompressing Linux”前，源码执行：

.. code-block:: c

   if (init_unaccepted_memory()) {
       accept_memory(__pa(output), needed_size);
   }

未启用 ``CONFIG_UNACCEPTED_MEMORY`` 时helper是恒false inline；即使build启用，固定实现也先
要求有效EFI loader type和EFI unaccepted-memory config table。当前i386-pc boot params没有EFI
loader signature，所以 ``efi_get_type()=EFI_TYPE_NONE``，函数返回false。本场景不会调用
``accept_memory``，这比“普通QEMU通常不会”更精确。

到此只确定输出，尚未写入输出
------------------------------

所有检查通过后，下一条源码是：

.. code-block:: c

   entry_offset = decompress_kernel(output, virt_addr, error);

本章停在调用前。此时 ``O`` 只是已验证的目标；compressed bitstream尚未被解码，ELF header
尚未解析，``O`` 处也不因选址本身自动出现正式内核对象。若 ``O`` 在现有页表之外，第一次
实际写入要到第037章，并由stage2 ``#PF`` 按2 MiB范围补map后重试。

本章结束状态
------------

* current executor：Linux 7.2-rc1 compressed ``extract_kernel()``；
* exact next action：调用 ``decompress_kernel(O,V,error)``，调用尚未执行；
* CPU：BSP / CPU0，无调度、无AP参与；
* CPU mode：64-bit long mode；IF=0，DF=0；
* current code/stack/GDT：均位于relocated ``B`` 副本；
* ``R15=Z``、``RBP=O0``、``RBX=B`` 由callee-saved ABI继续保留；
* compressed BSS：``[_bss,_ebss)`` 已清零；
* stage2 IDT：active，含 ``#PF``、NMI和条件 ``#VC``；
* early identity root：保留前六页并可从剩余26页继续分配；
* explicit identity maps：relocated compressed ``[_head,_end)``、``boot_params``、2048-byte
  command-line buffer与setup_data nodes；
* demand mapping：普通non-present supervisor fault可追加CR2周围2 MiB identity range；
* initramfs：``N`` bytes仍在 ``R``，未解析、未显式加入当前identity map；
* ``boot_params_ptr=Z``，KASLR flag先清零，再依build/command结果决定是否重设；
* compressed serial：固定 ``console=ttyS0`` 不触发本阶段early serial parser；
* ACPI RSDP：依ACPI build保留已有值或在legacy BIOS范围查找；
* boot heap：已按最终compression build选定大小并发布；
* ``D=ALIGN_UP(max(output_len,kernel_total_size),2 MiB)``；
* ``O/V``：已由non-KASLR固定路径或KASLR条件路径选定并通过硬检查；
* unaccepted memory：当前legacy BIOS路径未调用accept；
* compressed payload、ELF segments与正式内核BSS：尚未生成；
* initramfs unpack、正式内核page tables与 ``start_kernel()``：均未发生。

关键边界
--------

#. ``rep stosq`` 只清compressed BSS；``.data`` 与 ``.pgtable`` 分别保留搬迁状态和early tables。
#. stage2 IDT先于 ``initialize_identity_maps``，因为建图过程本身可能需要non-present ``#PF``
   fault-in。
#. 当前startup_32来源无论最终4-level还是5-level，都保留 ``_pgtable`` 前六页并从后26页追加。
#. 显式mapping不含initramfs和未知的KASLR output；高地址输出依stage2 ``#PF`` 按需补map。
#. ``boot_params`` 在第035章为五级分页解析清洗过一次；搬迁后BSS清零，``extract_kernel`` 重新
   发布全局指针并再次清洗。
#. ``console=ttyS0`` 不是compressed early serial parser接受的
   ``earlyprintk``/``console=uart8250,io`` 形式。
#. ``CONFIG_RANDOMIZE_BASE`` 未由commit确定；无该config时 ``O=O0,V=L``，有该config且无
   ``nokaslr`` 时才进入物理/虚拟选择。
#. physical slot失败不取消virtual KASLR，也不自动清除KASLR flag。
#. KASLR avoid initramfs不等于当前页表映射initramfs。
#. 当前i386-pc handoff没有EFI type，因此unaccepted-memory接受分支精确不执行。
#. 本章只选择并验证 ``O/V``；真正写 ``O`` 从下一章的decompressor开始。

下一入口
--------

第037章从固定C调用开始：

.. code-block:: c

   entry_offset = decompress_kernel(output, virt_addr, error);

``decompress_kernel`` 将按build选择的统一 ``__decompress`` 接口把bitstream写到 ``O``，再验证
ELF、搬运 ``PT_LOAD`` segments并处理relocations；返回后 ``extract_kernel`` 清理compressed
异常环境，汇编最终以 ``RSI=Z`` 跳入解压后正式内核入口。第037章仍是pending历史稿，留给下一
批按相同fixed-source合同审查。

资料
----

* `Linux 7.2-rc1固定提交：.Lrelocated、identity-map与extract_kernel调用 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/head_64.S#L444-L476>`_；
* `Linux 7.2-rc1固定提交：stage2 IDT与cleanup边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/idt_64.c#L42-L92>`_；
* `Linux 7.2-rc1固定提交：identity-map初始化与按需page fault <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/ident_map_64.c#L37-L190>`_；
* `Linux 7.2-rc1固定提交：do_boot_page_fault的2 MiB补图 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/ident_map_64.c#L345-L388>`_；
* `Linux 7.2-rc1固定提交：extract_kernel顺序、硬检查与decompress入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/misc.c#L407-L536>`_；
* `Linux 7.2-rc1固定提交：KASLR avoid ranges、E820 slots与物理/虚拟选择 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/kaslr.c#L279-L398>`_；
* `Linux 7.2-rc1固定提交：KASLR slot扫描与choose_random_location <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/kaslr.c#L400-L909>`_；
* `Linux 7.2-rc1固定提交：early serial实际接受的command-line形式 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/early_serial_console.c#L46-L154>`_；
* `Linux 7.2-rc1固定提交：RSDP保留、EFI与legacy BIOS查找顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/acpi.c#L128-L169>`_；
* `Linux 7.2-rc1固定提交：legacy BIOS下unaccepted-memory返回false <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/mem.c#L48-L85>`_；
* `Linux 7.2-rc1固定提交：compressed linker的BSS与pgtable边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/boot/compressed/vmlinux.lds.S#L54-L81>`_。
