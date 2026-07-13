第五十章：Linux 怎样把 memblock 物理内存变成 node、zone 和 struct page？
====================================================================

第四十九章结束时，``setup_arch()`` 已经返回 ``start_kernel()``。当前下一条语句是：

.. code-block:: c

   mm_core_init_early();

此前 Linux 已经知道哪些物理地址是 RAM，并用 ``memblock`` 记录可用与保留区间；它也已经根据 SRAT 或 single-node fallback 给 RAM 标注 NUMA node。

但这仍不是普通内存分配器所理解的世界。

``memblock`` 描述的是少量大区间：

.. code-block:: text

   [start physical address, size, node]

后面的 buddy allocator 需要更细的对象：

.. code-block:: text

   node
   → zone
   → 每一个 page frame 对应的 struct page
   → pageblock / free_area / migratetype

本章追踪 ``mm_core_init_early()`` 返回，解释 Linux 如何先搭好这些结构，同时仍不把普通 RAM 释放给 buddy allocator。

``mm_core_init_early()`` 只有三条调用
----------------------------------

Linux 6.12.95 的实现很短：

.. code-block:: c

   void __init mm_core_init_early(void)
   {
       hugetlb_cma_reserve();
       hugetlb_bootmem_alloc();
       free_area_init();
   }

函数短不代表工作量小。真正的主体全部藏在这三个入口中。

为什么 HugeTLB 必须抢在 zone 初始化之前
-------------------------------------

首先调用：

.. code-block:: c

   hugetlb_cma_reserve();

HugeTLB 提供固定尺寸的大页池。x86-64 常见大页尺寸包括 2 MiB 和 1 GiB，其中 1 GiB 这种 gigantic page 的 order 通常大于 buddy allocator 可直接提供的最大 order。

当系统已经运行很久，物理页会被打散。即使空闲页总量远大于 1 GiB，也未必能找到一段连续、对齐的 1 GiB 区间。

因此内核支持启动参数：

.. code-block:: text

   hugetlb_cma=<size>
   hugetlb_cma=<node>:<size>,...
   hugetlb_cma_only=<bool>

如果没有请求 ``hugetlb_cma``，``hugetlb_cma_size`` 为零，函数立即返回。固定启动命令行没有该参数，所以主线不会自动预留 HugeTLB CMA 区。

这里依然必须解释完整路径，因为调用顺序揭示了一条原则：需要超大连续物理区的功能，必须在普通 page allocator 接管内存前完成保留。

HugeTLB CMA 怎样按 NUMA node 分配
--------------------------------

若用户请求 HugeTLB CMA，函数先调用 ``hugetlb_bootmem_set_nodes()``，从已经带 node 归属的 memblock ranges 中建立可用 node mask。

随后它确认：

* 当前架构是否支持 gigantic HugeTLB CMA；
* 请求大小是否是 gigantic page size 的整数倍；
* 指定 node 是否真实存在且有可用内存；
* 总大小或每 node 大小是否有效。

没有显式 node 划分时，总请求会按 online memory nodes 分摊，并按 gigantic page size 向上对齐。

最终通过：

.. code-block:: c

   cma_declare_contiguous_multi(..., nid)

在对应 node 的 memblock 中声明连续区。

这段内存以后仍由 CMA 框架管理，HugeTLB 可以从中取得被冻结的 compound folio。它不会在普通 buddy free list 中被随意拆散。

``hugetlb_bootmem_alloc()`` 处理启动时就要求存在的大页
-----------------------------------------------------

第二条调用：

.. code-block:: c

   hugetlb_bootmem_alloc();

它先建立 HugeTLB 可分配 node 集合，并初始化每个 node 的 ``huge_boot_pages`` 链表，然后正式解析 HugeTLB 参数组合：

.. code-block:: text

   default_hugepagesz=
   hugepagesz=
   hugepages=

这里需要区分两种大页。

普通 hugetlb page 的 order 仍在 buddy allocator能力范围内，可以等 buddy 建立后再分配。

gigantic hugetlb page 超出普通 buddy 最大 order，必须现在直接从 memblock 或前面声明的 HugeTLB CMA 区取得连续物理内存。

所以 ``hugetlb_bootmem_alloc()`` 只为需要启动期处理的 hstate 调用 ``hugetlb_hstate_alloc_pages()``。

固定命令行没有 ``hugepages``、``hugepagesz`` 或 ``default_hugepagesz``，主线通常不会在这里建立预分配 HugeTLB 池。

它不是透明大页初始化
------------------

HugeTLB 和 Transparent Huge Pages（THP）是两套机制。

``hugetlb_bootmem_alloc()`` 处理的是显式 HugeTLB hstate 与预留池。THP 会在更后的匿名内存、文件映射和 khugepaged 路径中工作。

这里没有创建用户进程，也没有页表 fault，更不会出现匿名 THP 合并。

``free_area_init()`` 开始建立通用物理页模型
---------------------------------------

第三条调用才是本章主体：

.. code-block:: c

   free_area_init();

它的任务可以压缩成：

.. code-block:: text

   architecture PFN limits
   → sparse memory model
   → global zone boundaries
   → per-node PFN ranges
   → pg_data_t
   → per-node zones
   → struct page map
   → pageblock metadata

但每一步解决的问题不同。

PFN 是物理地址的页编号
--------------------

PFN（Page Frame Number）是物理地址除以 ``PAGE_SIZE`` 后得到的页编号：

.. code-block:: text

   pfn = physical_address >> PAGE_SHIFT

在典型 x86-64 4 KiB page 配置中：

.. code-block:: text

   PAGE_SHIFT = 12
   PFN 1 = physical [0x1000, 0x1fff]

内核此前计算的 ``max_pfn``、``max_low_pfn`` 和 memblock ranges 都可以转换成 PFN 区间。

``arch_zone_limits_init()`` 给出 x86 的 zone 上界
------------------------------------------------

``free_area_init()`` 首先调用：

.. code-block:: c

   arch_zone_limits_init(max_zone_pfn);

x86-64 的实现根据配置填写：

.. code-block:: c

   ZONE_DMA    → min(MAX_DMA_PFN, max_low_pfn)
   ZONE_DMA32  → min(MAX_DMA32_PFN, max_low_pfn)
   ZONE_NORMAL → max_low_pfn

若是支持 HIGHMEM 的 32 位配置，还会设置 ``ZONE_HIGHMEM → max_pfn``。当前固定路径是 x86-64，不使用传统 32 位 HIGHMEM 分区。

常见 x86-64 zone 含义是：

* ``ZONE_DMA``：满足旧 ISA DMA 低地址限制的页面；
* ``ZONE_DMA32``：物理地址低于 4 GiB、适合只能做 32 位 DMA 的设备；
* ``ZONE_NORMAL``：其余可由内核 direct map 正常访问的 RAM；
* ``ZONE_MOVABLE``：从普通 zone 切出、尽量只存可迁移页面的逻辑区域。

zone 不是 E820 类型
------------------

E820 的 ``RAM``、``RESERVED``、``ACPI NVS`` 描述物理地址用途。

zone 描述分配约束：某页是否满足特定 DMA 地址范围，或者是否被规划为 movable。

同一段 E820 RAM 会根据 PFN 位置进入 DMA、DMA32 或 NORMAL。E820 reserved 区不会因为落在 DMA32 地址范围内就变成可分配的 DMA32 页。

``sparse_init()`` 建立 PFN 到 ``struct page`` 的寻址骨架
-----------------------------------------------------

接下来：

.. code-block:: c

   sparse_init();

现代 x86-64 通常使用 SPARSEMEM 或 SPARSEMEM_VMEMMAP。

物理地址空间可能存在巨大空洞：

.. code-block:: text

   RAM
   → PCI MMIO hole
   → RAM above 4 GiB
   → firmware reserved windows

内核不能简单按照“最大物理地址”分配一个完全连续的 ``struct page`` 数组，否则会为不存在的 PFN 浪费大量内存。

SPARSEMEM 把物理空间切成 memory section，只为存在或可能存在的 section 建立元数据。SPARSEMEM_VMEMMAP 再提供一个看起来连续的虚拟 ``vmemmap`` 区，使：

.. code-block:: c

   pfn_to_page(pfn)

可以通过固定算式定位对应 ``struct page``。

此时建立的是内存模型和元数据映射，普通页面尚未进入 free list。

全局 zone 边界怎样形成
---------------------

``free_area_init()`` 从：

.. code-block:: c

   memblock_start_of_DRAM()

取得最低 RAM PFN，然后按 zone 顺序填充：

.. code-block:: text

   arch_zone_lowest_possible_pfn[zone]
   arch_zone_highest_possible_pfn[zone]

前一个 zone 的终点成为后一个 zone 的起点。

如果某两个相邻 zone 的最大 PFN 相同，后一个 zone 为空。例如机器 RAM 全部低于 4 GiB 时，``ZONE_NORMAL`` 可能没有独立页范围；具体结果取决于内存大小和内核配置。

``ZONE_MOVABLE`` 为什么不直接使用固定地址上界
------------------------------------------

MOVABLE zone 不是硬件地址限制。它从每个 node 的普通内存中动态切出一段，目标是让其中绝大多数页可迁移，从而提高 memory hot-remove 和大块连续分配成功率。

因此源码跳过固定 ``max_zone_pfn[ZONE_MOVABLE]``，单独调用：

.. code-block:: c

   find_zone_movable_pfns_for_nodes();

它会结合 ``kernelcore=``、``movablecore=``、``movable_node`` 和 node 内存布局决定每个 node 的 movable 起始 PFN。

固定命令行没有这些参数，具体是否形成非空 MOVABLE zone还取决于构建配置和默认策略，正文不虚构固定容量。

为什么内核此时打印 Zone ranges
-----------------------------

源码打印每个 zone 的全局可能范围，以及每个 node 的 movable 起点和 early memory node ranges。

这些日志不是装饰。它们把三套数据对应起来：

.. code-block:: text

   architecture DMA limits
   memblock node ranges
   final zone PFN boundaries

启动异常时，开发者可以据此判断 RAM 是否被错误截断、NUMA node 是否缺失、DMA32 是否为空、MOVABLE 是否切得过大。

``sparse_init_subsection_map()`` 为更细粒度 hotplug 准备位图
---------------------------------------------------------

遍历每段 memblock PFN range 时，内核调用：

.. code-block:: c

   sparse_init_subsection_map(start_pfn, nr_pages);

memory section 通常仍很大。subsection map 进一步记录 section 内哪些小区间当前真正 online，便于以后 memory hotplug/hot-remove 以比整个 section 更细的粒度工作。

固定 q35 主线即使不做内存热插拔，也使用同一套通用内存模型。

每个 node 都需要 ``pg_data_t``
-----------------------------

完成全局边界后，内核依次调用：

.. code-block:: text

   mminit_verify_pageflags_layout()
   setup_nr_node_ids()
   set_pageblock_order()

然后遍历 possible nodes。

每个 node 的根对象是 ``pg_data_t``，通常通过 ``NODE_DATA(nid)`` 取得。它保存：

* node 起始 PFN；
* node 跨越与实际存在的 page 数量；
* node 内各个 ``struct zone``；
* node 级回收、LRU 和统计基础；
* 后续 kswapd 与 zonelist 所需状态。

第四十五章已为有效 NUMA node 分配 node data。若存在 memoryless/offline node 且尚无 ``NODE_DATA``，这里会补一个 offline node data，使统一接口仍可使用。

``free_area_init_node()`` 怎样计算 node 的真实范围
------------------------------------------------

对每个 node，函数通过：

.. code-block:: c

   get_pfn_range_for_nid(nid, &start_pfn, &end_pfn);

遍历带 node 标记的 memblock RAM，取得该 node 最低和最高 PFN。

然后写入：

.. code-block:: text

   pgdat->node_id
   pgdat->node_start_pfn
   pgdat->node_spanned_pages
   pgdat->node_present_pages

``spanned_pages`` 包括 node 起点到终点之间的地址跨度，可能包含空洞；``present_pages`` 只统计实际存在的 RAM page。

二者不能混为一谈。带 PCI hole 或 firmware hole 的 node 中，``spanned_pages`` 会大于 ``present_pages``。

``struct page`` 是每个物理页框的软件身份证
---------------------------------------

每个可管理 PFN 都需要一个 ``struct page``，用来保存：

* flags；
* 引用计数与 mapcount；
* 所属 zone/node；
* buddy order 或 LRU 链接；
* compound page/folio 元数据；
* slab、page cache、anonymous memory 等复用字段。

它不存放页面内容。4 KiB 物理页的数据仍位于该物理页本身；``struct page`` 是内核管理它的元数据。

在 FLATMEM 模型中 ``alloc_node_mem_map()`` 会显式为 node 分配连续 ``struct page`` 数组。SPARSEMEM_VMEMMAP 的主要 backing 在 ``sparse_init()`` 阶段按 section 建立，因此该 FLATMEM 分支为空。

``calculate_node_totalpages()`` 必须扣除 hole
------------------------------------------

zone 范围由 PFN 边界决定，但边界内部不一定全部是 RAM。

``calculate_node_totalpages()`` 对每个 node/zone 计算：

.. code-block:: text

   spanned pages
   - absent pages / holes
   = present pages

这让后续 allocator 不会把 PCI MMIO hole 或 firmware reserved hole 当作普通 page frame。

``free_area_init_core()`` 建立 zone 内部结构
-----------------------------------------

每个 node 的 zone 由 ``free_area_init_core(pgdat)`` 初始化。

它先建立 pgdat 内部锁、等待队列和统计基础，然后遍历所有 zone：

.. code-block:: c

   zone_init_internals(zone, zone_id, nid, present_pages);

关键事实是，此时：

.. code-block:: text

   zone->managed_pages = 0

原因是 memblock 仍然拥有全部 RAM。只有后面 ``memblock_free_all()`` 把未保留页面释放进 buddy system 时，``managed_pages`` 才会上升。

所以这一章建立了 allocator 的容器，没有向容器中放入可分配页。

``free_area`` 已存在，里面还没有普通空闲块
----------------------------------------

每个 zone 包含按 order 分类的 ``free_area[]``：

.. code-block:: text

   order 0  → 1 page
   order 1  → 2 contiguous pages
   order 2  → 4 contiguous pages
   ...

同时还按 migratetype 区分 movable、unmovable、reclaimable、CMA 等链表。

``init_currently_empty_zone()`` 会初始化这些链表、锁和 pageblock bitmap，但当前普通 RAM 仍标记为 reserved，没有被插入任何 buddy free list。

这正是 ``free_area_init`` 名字容易造成的误解：它初始化 free-area 数据结构，不等于系统已经拥有可用 free pages。

pageblock 是比单页更大的迁移策略单位
----------------------------------

``set_pageblock_order()`` 确定 pageblock 大小，通常与大页或最大连续分配粒度相关。

pageblock bitmap 保存一整块页面的 migratetype。compaction 和 buddy allocator 根据它尽量把相同迁移性质的页面聚在一起，减少不可移动内核对象把大块物理区永久切碎。

HugeTLB、CMA、THP 和 memory hotplug 都依赖 pageblock 粒度的布局策略。

``memmap_init()`` 开始初始化每个 ``struct page``
---------------------------------------------

所有 node/zone 基础完成后：

.. code-block:: c

   calc_nr_kernel_pages();
   memmap_init();

``memmap_init()`` 为实际物理范围中的 ``struct page`` 写入初始状态，包括 PFN、zone id、node id 和 reserved 状态。

启用 deferred struct page init 时，超大内存机器可以只初始化启动必需部分，把其余 ``struct page`` 延迟到后续线程并行完成，缩短启动串行阶段。

无论是否 deferred，尚未交给 buddy 的页都不会被当成普通可分配页。

单 node 机器关闭 hash distribution
--------------------------------

``fixup_hashdist()`` 会在单 node 场景关闭不必要的 hash-based 跨 node 分布策略。

固定 QEMU 未配置 ``-numa`` 时通常只有 node 0，这条路径避免为不存在的远端 node 做分散分配。

``set_high_memory()`` 记录 direct-map RAM 末端
-------------------------------------------

最后：

.. code-block:: c

   set_high_memory();

它依据：

.. code-block:: c

   memblock_end_of_DRAM()

设置 ``high_memory``，表示内核线性映射普通 RAM 的末端虚拟地址。

在 x86-64 上名字中的 ``high`` 不代表 32 位 HIGHMEM。它是历史接口，当前表示 direct-map 可寻址 RAM 的边界。

本章建立了什么，仍缺什么
----------------------

现在 Linux 已经拥有：

.. code-block:: text

   memblock RAM ranges
   → NUMA node
   → pg_data_t
   → zone
   → PFN
   → struct page
   → pageblock / free_area metadata

仍然缺少：

.. code-block:: text

   memblock_free_all()
   → 把未保留 RAM 释放给 buddy

因此此时调用普通 ``alloc_pages()`` 的完整运行环境仍未准备好，slab allocator 也尚未建立。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``mm_core_init_early()`` 已返回，``jump_label_init()`` 尚未调用；
* CPU：BSP / Linux CPU 0；
* interrupts：关闭；
* memblock：仍持有并管理启动期 RAM 与 reservation；
* HugeTLB CMA：只在命令行/配置请求时预留，固定主线未请求；
* gigantic HugeTLB boot pages：只在启动参数请求时分配；
* NUMA ``pg_data_t``：已建立；
* zones：DMA/DMA32/NORMAL/MOVABLE 已按配置与 PFN 范围建立；
* sparse memory / vmemmap：已初始化；
* ``struct page``：已为可管理物理页建立和初始化；
* zone ``free_area[]``：结构已存在；
* zone ``managed_pages``：普通 RAM 尚未由 memblock 释放，仍接近初始零状态；
* buddy allocator：结构基础存在，尚未接收全部可分配页；
* slab allocator：尚未建立；
* per-CPU area：尚未建立；
* AP：尚未唤醒；
* initramfs：尚未解包。

下一条控制流是：

.. code-block:: c

   jump_label_init();

资料
----

* `Linux 6.12.95 mm_init.c：mm_core_init_early 与 free_area_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mm_init.c>`_
* `Linux 6.12.95 hugetlb_cma.c：HugeTLB CMA 启动期保留 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/hugetlb_cma.c>`_
* `Linux 6.12.95 hugetlb.c：hugetlb_bootmem_alloc 与 gigantic page 预分配 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/hugetlb.c>`_
* `Linux 6.12.95 x86 init.c：arch_zone_limits_init 的 DMA、DMA32 与 NORMAL 边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init.c>`_
* `Linux 6.12.95 mmzone.h：pg_data_t、zone 与 free_area 数据结构 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/mmzone.h>`_
* `Linux 6.12.95 sparse.c：SPARSEMEM 与 vmemmap 初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/sparse.c>`_
* `Linux 6.12.95 init/main.c：mm_core_init_early 后的 jump_label_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_