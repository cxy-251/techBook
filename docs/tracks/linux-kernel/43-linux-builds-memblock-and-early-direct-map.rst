第四十三章：Linux 怎样把 E820 RAM 变成 memblock 并建立 early direct map？
=============================================================================

第四十二章结束时，Linux 已经修正 E820、登记 kernel resources，并计算出 ``max_pfn``。此时它“知道”哪些地址是 RAM，却仍不能随意从所有 RAM 中分配内存。

当前下一条调用是：

.. code-block:: c

   early_alloc_pgt_buf();

本章追踪到：

.. code-block:: c

   memblock_set_current_limit(get_max_mapped());

结束。到这个自然边界时，E820 RAM 已转换成 memblock，低端 real-mode trampoline 已预留，覆盖物理 RAM 的 early direct map 已建立，CPU 也已切到新的页表根。

先再次区分三种“这块内存能用”
----------------------------

同一个物理区间在启动过程中会经历三个不同层次：

.. code-block:: text

   E820_TYPE_RAM
       固件/内核内存图认为它是 RAM

   memblock.memory
       early allocator 可以把它当候选内存

   direct mapped
       CPU 已有页表，可通过内核线性地址访问它

一段 E820 RAM 可能尚未加入 memblock；一段 memblock RAM 也可能尚未被页表映射。Linux 必须按顺序逐步扩大能力，不能看到 E820 中写着 RAM 就立即访问任意高地址。

为 direct map 预留最早一批页表页
--------------------------------

``early_alloc_pgt_buf()`` 位于 ``arch/x86/mm/init.c``。它使用尚未封存的 brk 区域申请一块页对齐缓冲：

.. code-block:: c

   base = __pa(extend_brk(INIT_PGT_BUF_SIZE, PAGE_SIZE));

随后记录：

.. code-block:: text

   pgt_buf_start   缓冲起始 PFN
   pgt_buf_end     下一张可用页表页
   pgt_buf_top     缓冲末端 PFN

``INIT_PGT_BUF_SIZE`` 不是整个系统最终页表大小，只是一笔启动资本。

源码中基础需求按 4 组顶层映射页表估算：

.. code-block:: text

   未启用 CONFIG_RANDOMIZE_MEMORY   8 pages
   启用 CONFIG_RANDOMIZE_MEMORY     16 pages

memory KASLR 可能让映射跨越更多顶层边界，因此预留量翻倍。

为什么页表页必须来自已经映射的内存
--------------------------------

创建新 direct map 时，内核要先写入新的 PGD/P4D/PUD/PMD/PTE 页面。

问题是：

.. code-block:: text

   想映射更多 RAM
   → 需要分配页表页
   → 想清零和填写页表页
   → 页表页本身必须已经能被 CPU 访问

这是一个自举循环。

最早的 brk 页表缓冲已经位于 kernel image 附近，当前高半区映射可以访问它。Linux先用这批页表页扩展一段映射，映射扩大后，再从新映射的 memblock RAM 中分配更多页表页。

``alloc_low_pages()`` 的三级后备路径
-----------------------------------

早期页表分配器按条件选择：

.. code-block:: text

   1. pgt_buf 仍有页
      → 从 brk 页表缓冲取

   2. pgt_buf 不够，但某段 memblock RAM 已经 direct mapped
      → memblock_phys_alloc_range()

   3. memblock 暂时也找不到，而 brk 尚未封存
      → extend_brk()

若三条路径都失败，内核直接 panic，因为没有页表页就无法继续扩大可访问物理内存。

每个返回页都会先通过现有 direct map 转成虚拟地址并清零，避免旧数据被解释为 present page-table entries。

在 memblock 分配前封存 brk
-------------------------

``early_alloc_pgt_buf()`` 后，``setup_arch()`` 调用：

.. code-block:: c

   reserve_brk();

brk 是链接在 kernel BSS 后面的一段极早期线性 bump allocator。前面的页表、早期结构和临时数组可以通过 ``extend_brk()`` 向后推进 ``_brk_end``。

``reserve_brk()`` 做两件事：

.. code-block:: c

   memblock_reserve_kern(__pa_symbol(_brk_start),
                         _brk_end - _brk_start);
   _brk_start = 0;

第一步把已经实际使用的 brk 物理范围加入 reserved；第二步把 ``_brk_start`` 清零，表示 brk allocator 正式关闭。

从这里以后，新的 early allocation 应该走 memblock。继续调用 ``extend_brk()`` 会触发 ``BUG_ON(_brk_start == 0)``，防止两种 allocator 同时扩张并相互覆盖。

``cleanup_highmap()`` 收紧早期高半区映射
--------------------------------------

在导入 memblock 前还会调用：

.. code-block:: c

   cleanup_highmap();

解压后的正式内核早期页表曾建立较宽的 PMD 映射，以保证 kernel image 能在高半区执行。映像实际结束位置通常不刚好落在大页边界。

``cleanup_highmap()`` 清除 kernel image 范围以外的多余高半区 present mappings，只保留启动仍需要的部分。

这和前面 ``__startup_64()`` 清理映像外 PMD 的目标一致：不能因为大页方便，就让内核虚拟地址无意映射到未验证的保留物理区。

E820 RAM 正式进入 ``memblock.memory``
-----------------------------------

随后调用：

.. code-block:: c

   e820__memblock_setup();

它先把 memblock 当前分配上限压到：

.. code-block:: c

   ISA_END_ADDRESS

也就是 1 MiB。

原因是此刻只有最低端和 kernel image 附近的映射绝对可靠。完整 direct map 尚未建立，memblock 即使知道高端 RAM 存在，也不能把某个高端物理页返回给需要立刻通过 ``__va()`` 写入的调用者。

允许 memblock region 数组扩容
----------------------------

memblock 初始 region 数组容量有限。EFI 或复杂 E820 可能提供超过静态容量的区间，因此执行：

.. code-block:: c

   memblock_allow_resize();

扩容本身也需要内存。它之所以到这里才安全，是因为：

* kernel、initramfs、setup_data、BIOS 等关键范围已经加入 reserved；
* 当前分配仍被限制在 1 MiB 以下的可访问区域；
* region metadata 不会踩到尚未登记的启动数据。

逐项转换 E820
-------------

``e820__memblock_setup()`` 遍历最终工作 E820 表。

遇到 ``E820_TYPE_SOFT_RESERVED``：

.. code-block:: c

   memblock_reserve(entry->addr, entry->size);

soft-reserved 表示该区间不是普通 allocator 可立即使用的 RAM，但未来可能交给特定驱动或 dax/device-memory 子系统处理。

遇到普通 ``E820_TYPE_RAM``：

.. code-block:: c

   memblock_add(entry->addr, entry->size);

其他类型不会加入 ``memblock.memory``，包括：

* ``E820_TYPE_RESERVED``；
* ACPI table / NVS；
* unusable memory；
* persistent memory 的其他专用类型。

因此 memblock 不是 E820 的完整复制。它只抽取“可作为普通物理内存候选”的区间，并叠加此前建立的 reserved 集合。

``memory`` 与 ``reserved`` 可以重叠
---------------------------------

例如 kernel image 所在区间仍属于 E820 RAM，所以它会被加入 ``memblock.memory``；同时上一章已经把它加入 ``memblock.reserved``。

这不是冲突。memblock 查询可用内存时实际计算：

.. code-block:: text

   usable = memory - reserved

同理，initramfs、setup_data、页表缓冲和低端 trampoline 都可以位于 RAM 内，却因 reserved 标记而不会被重新分配。

为什么要裁掉非完整页面
----------------------

E820 区间可以不是 4 KiB 对齐。普通页分配器只能管理完整 page frame，因此：

.. code-block:: c

   memblock_trim_memory(PAGE_SIZE);

会把区间起点向上对齐、终点向下对齐。

一个只有部分字节落在 RAM 描述内的物理页不能交给 allocator；同一页剩余部分可能属于固件或设备。

KHO scratch 条件路径
--------------------

``memblock_mark_kho_scratch(0, SZ_1M)`` 服务于 kexec handover 特殊路径。它暂时把低 1 MiB 标成可用于极早分配的 scratch 区域。

当前普通 cold boot 不依赖 KHO，但该标记稍后仍会在 real-mode trampoline 分配完成后清除，避免低端内存长期保留不准确的 scratch 语义。

memblock 建立后才初始化内存加密架构状态
------------------------------------

接下来：

.. code-block:: c

   mem_encrypt_setup_arch();
   cc_random_init();

SEV、SME、TDX 等 confidential-computing 路径需要知道物理内存规模和 reserved 区间，才能建立加密位、共享/私有内存和随机化相关状态。

固定普通 q35 主线若没有启用这些特性，调用会退化或只保留通用状态，但顺序不能移动到 memblock 之前。

预留 MP table 新副本
-------------------

``e820__memblock_alloc_reserved_mpc_new()`` 预分配一页，用于未来构造或复制 MP configuration table。

即使 q35 更主要依赖 ACPI MADT，传统 MP table 兼容代码仍需要安全的 reserved 存储，不能在稍后 allocator 已经活跃时随意占用低端区域。

为什么还要在 1 MiB 以下找 real-mode trampoline
---------------------------------------------

随后：

.. code-block:: c

   x86_platform.realmode_reserve();

普通 PC 默认进入 ``reserve_real_mode()``。

Linux 已经运行在 64 位 long mode，但唤醒 AP 时，硬件 INIT/SIPI 语义要求 secondary CPU 从实模式兼容入口开始。Linux 因此需要一段低地址 trampoline，把 AP 从 16 位状态逐步带回 long mode 和 ``secondary_startup_64``。

``reserve_real_mode()`` 计算 real-mode blob 所需大小，并在平台限制以下申请页对齐物理内存：

.. code-block:: c

   memblock_phys_alloc_range(size, PAGE_SIZE, 0, limit);

这一步只预留位置。trampoline 二进制复制、16 位 segment relocation、32 位 linear relocation 和执行权限设置会在后面的 ``init_real_mode()`` 完成。

为什么最终保留整个低 1 MiB
-------------------------

分配 trampoline 后，代码无条件执行：

.. code-block:: c

   memblock_reserve(0, SZ_1M);

前面只保留了低 64 KiB；现在扩展到完整 1 MiB。

原因包括：

* BIOS/EBDA/Option ROM 历史区域可能仍被固件破坏；
* AP trampoline 必须长期位于低端；
* 检测每一个“看起来安全”的低端小洞复杂且收益很低；
* Windows 等系统也采用类似整体保留策略；
* TDX host 等路径同样要求低 1 MiB 不进入普通 allocator。

这意味着 E820 可能把低端某些区间标为 RAM，memblock.memory 也已经导入它们，但 ``memblock.reserved`` 最终覆盖整个 ``0–1 MiB``，普通分配器不会使用。

建立 direct map 前探测可用页大小
------------------------------

``init_mem_mapping()`` 首先执行：

.. code-block:: c

   pti_check_boottime_disable();
   probe_page_size_mask();
   setup_pcid();

``probe_page_size_mask()`` 根据 CPU 与配置决定 direct map 可使用：

.. code-block:: text

   4 KiB PTE
   2 MiB PMD large page
   1 GiB PUD huge page

若 CPU 支持 PSE，内核在 CR4 中启用它，并允许 2 MiB 映射。若配置允许且 CPU 支持 ``X86_FEATURE_GBPAGES``，direct map 可以使用 1 GiB 页。

大页减少页表数量和 TLB 压力，但只有物理区间边界、缓存属性和对齐允许时才能使用。E820 hole 或 MTRR 边界附近通常需要退回 2 MiB 或 4 KiB。

``setup_pcid()`` 处理 Process-Context Identifier 条件能力。当前仍没有用户进程地址空间，但页表切换策略和 CR4 能力需要在正式 direct map 建立前确定。

ISA 范围无条件建立映射
---------------------

``init_mem_mapping()`` 先执行：

.. code-block:: c

   init_memory_mapping(0, ISA_END_ADDRESS, PAGE_KERNEL);

也就是先为 ``0–1 MiB`` 建立 direct mapping，即使其中存在 E820 hole。

这不是把低 1 MiB 重新变成可分配 RAM。页表映射与 allocator 可用性是两回事：

.. code-block:: text

   direct mapped     内核能够通过虚拟地址访问
   memblock reserved 普通分配器不能使用

内核后面仍需读取 BIOS、trampoline、EBDA 或其他低端兼容数据，所以保留但可访问是合理状态。

建立 AP trampoline 页表入口
--------------------------

``init_trampoline()`` 准备 AP 启动时使用的顶层页表入口。

未启用 memory KASLR 时，可以复制 direct map 的首个 PGD entry。启用 memory KASLR 时，只复制覆盖低 1 MiB 的 PUD 范围，避免把过宽的随机化 direct map alias 带入 trampoline page table。

这也是为什么 real-mode trampoline 的页表问题必须和 direct map 一起处理，而不能等到真正唤醒 AP 时临时创建。

只映射 memblock 中的 RAM 区间
---------------------------

``init_range_memory_mapping()`` 使用：

.. code-block:: c

   for_each_mem_pfn_range(...)

遍历 memblock memory，而不是简单从 ``0`` 连续映射到 ``max_pfn``。

这是关键安全边界。若物理地址图是：

.. code-block:: text

   RAM
   PCI MMIO hole
   RAM

Linux 只为两段 RAM 建立普通 ``PAGE_KERNEL`` direct map，不会把中间 PCI hole 当作普通缓存 RAM 映射。

区间边缘根据对齐和能力被拆成：

.. code-block:: text

   4 KiB head
   2 MiB aligned range
   1 GiB aligned range
   2 MiB aligned tail
   4 KiB tail

因此同一段物理 RAM 的 direct map 可以混合多级页大小。

页表如何自举扩大
----------------

当前普通路径的 memblock 分配方向通常是 top-down，于是调用：

.. code-block:: c

   memory_map_top_down(ISA_END_ADDRESS, end);

它不会一次映射全部 RAM。

首先寻找一个 2 MiB 对齐、可临时释放的高端 RAM 区间，确保最顶端附近先有一小段已映射内存。然后从高地址向低地址分步推进：

.. code-block:: text

   初始 step = 2 MiB
   → 建立这一段映射
   → 已映射 RAM 增加
   → memblock 可以从该范围提供更多页表页
   → 放大 step
   → 继续映射下一段

当累计映射量足够时，step 会按页表层级差扩大。这样少量 brk 页表缓冲就能撬动整张 direct map。

在 ``movable_node`` 等特殊配置中，memblock 可能采用 bottom-up。那时 Linux 先映射 kernel 以上区域，以便页表页尽量分配在 kernel 上方，再回头映射 ISA 末端到 kernel 之间。

固定普通 q35 主线通常使用 top-down，但两种路径最终都只映射 memblock RAM。

``kernel_physical_mapping_init()`` 真正填写页表
--------------------------------------------

每个拆分后的 range 最终进入体系结构页表构造器：

.. code-block:: c

   kernel_physical_mapping_init(start, end,
                                page_size_mask,
                                PAGE_KERNEL);

它逐级建立或复用：

.. code-block:: text

   PGD
   → P4D（5-level 条件存在）
   → PUD
   → PMD
   → PTE

能使用 1 GiB 或 2 MiB leaf 时直接写大页 entry；不满足条件时继续下钻到更低一级。

页表项包含：

* physical frame address；
* present/write/global 等权限；
* NX 条件位；
* SME encryption mask 条件位；
* PAT/MTRR 协调后的缓存属性。

每次完成范围后，``add_pfn_range_mapped()`` 记录：

.. code-block:: text

   pfn_mapped[]
   max_pfn_mapped
   max_low_pfn_mapped

这些变量描述“已经能通过 direct map 访问到哪里”，不同于 E820 的 ``max_pfn``。

切换到新页表根
--------------

所有目标 RAM 映射完成后：

.. code-block:: c

   load_cr3(swapper_pg_dir);
   __flush_tlb_all();

写 CR3 让 CPU 使用刚建立的正式早期页表根。随后全量刷新 TLB，清除旧 early mapping 和大页拆分前可能残留的 translation。

从这一刻起，内核高半区、direct map、fixmap 基础与 trampoline 入口都由新的页表体系承载。

hypervisor 仍有最后钩子：

.. code-block:: c

   x86_init.hyper.init_mem_mapping();

Xen 等平台可以在通用映射后补充自己的页表状态。普通 QEMU/KVM HVM 主线通常不需要重写整张 direct map。

为什么在这里执行 early memtest
-----------------------------

``early_memtest()`` 在 ``0`` 到 ``max_pfn_mapped`` 范围内按 ``memtest=`` 参数执行条件测试。

它必须等 direct map 建好后才能访问广泛物理 RAM，也必须早于普通 page allocator 接管，否则测试写入可能破坏已分配对象。

固定命令行没有 ``memtest=``，因此主线不会进行破坏性大范围测试。

替换 early page-fault IDT
------------------------

回到 ``setup_arch()``：

.. code-block:: c

   cpu_init_replace_early_idt();

``init_mem_mapping()`` 依赖 early IDT 的页故障处理，以便映射构造期间按需补页。direct map 完成后，Linux可以启用 FRED 条件路径，或把 IDT 中的 page-fault 入口替换为正式早期 handler。

继续保留临时 handler 会让后续异常走入只适用于页表自举的代码。

保存 AP 将继承的 CR4 能力
------------------------

随后读取当前 CR4：

.. code-block:: c

   mmu_cr4_features = __read_cr4() & ~X86_CR4_PCIDE;

当前 PAE、PSE、PGE、LA57 等状态需要保存，未来 AP trampoline 会据此建立 secondary CPU 的 CR4。

PCIDE 被清掉，因为 AP 离开 long mode 或使用 trampoline page table 时不能直接继承该位；PCID 要在符合 CR3 条件的正式环境中重新启用。

解除 memblock 的 1 MiB 分配上限
------------------------------

本章最后：

.. code-block:: c

   memblock_set_current_limit(get_max_mapped());

在 ``e820__memblock_setup()`` 时，current limit 被压到 1 MiB。现在 direct map 已覆盖所有已映射 RAM，``get_max_mapped()`` 给出当前可安全通过 direct map 访问的最高物理边界。

memblock 从此可以在更广泛 RAM 中分配：

.. code-block:: text

   之前  候选 RAM 很多，但只允许从低 1 MiB 以内返回立即可访问内存
   现在  direct map 已建立，可把分配上限扩大到最高映射边界

这标志着 x86 启动内存自举的核心闭环完成：

.. code-block:: text

   E820 描述 RAM
   → memblock 管理 RAM
   → brk 页表缓冲建立第一批映射
   → 已映射 RAM 提供更多页表页
   → direct map 覆盖全部目标 RAM
   → memblock 解除低端限制

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* early brk allocator：已封存；
* early page-table buffer：已预留并参与自举；
* E820 RAM：已转换为 ``memblock.memory``；
* kernel/initramfs/setup_data/BIOS/trampoline：位于 ``memblock.reserved``；
* 低 1 MiB：全部保留，但保持 direct mapped；
* real-mode trampoline：物理位置已预留，内容尚未最终初始化；
* direct map：已覆盖目标 memblock RAM；
* 4 KiB / 2 MiB / 1 GiB 页：按能力、对齐与空洞混合使用；
* CR3：已加载 ``swapper_pg_dir``；
* TLB：已刷新；
* early page-fault IDT：已被正式早期入口替换；
* ``max_pfn_mapped``：已更新；
* memblock current limit：已扩展到 ``get_max_mapped()``；
* initramfs：仍未展开，下一阶段将确认是否需要重定位；
* ``setup_arch()``：仍未返回。

下一条控制流从：

.. code-block:: c

   setup_log_buf(1);

附近继续，随后执行 ``reserve_initrd()``、ACPI table 保留、NUMA 与完整架构页表初始化。

资料
----

* `Linux 6.12.95 setup.c：early_alloc_pgt_buf、reserve_brk、e820__memblock_setup 与 init_mem_mapping 调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 e820.c：把 E820 RAM 转换成 memblock <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c>`_
* `Linux 6.12.95 mm/init.c：页表缓冲、direct-map range 拆分、自举映射与 CR3 切换 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init.c>`_
* `Linux 6.12.95 mm/init_64.c：x86-64 PGD/PUD/PMD/PTE 与大页映射构造 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init_64.c>`_
* `Linux 6.12.95 realmode/init.c：低端 AP trampoline 的预留与后续初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/realmode/init.c>`_
* `Linux 6.12.95 memblock.c：memory、reserved、current limit 与 early allocation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memblock.c>`_
