第五十章：Linux 怎样从 memblock 建立 node、zone 与 struct page 骨架？
=====================================================================

第四十九章结束时，CPU0已从 ``setup_arch`` 返回 ``start_kernel``、IF=0；memblock仍持有working-E820
RAM与reserved ranges，generic zones和per-PFN metadata尚未建立。当前入口是：

.. code-block:: c

   mm_core_init_early();

fixed Linux 7.2-rc1函数只有三条call：

.. code-block:: c

   hugetlb_cma_reserve();
   hugetlb_bootmem_alloc();
   free_area_init();

本章追踪它返回。前两条只在HugeTLB policy要求时抢占gigantic contiguous memory；第三条把memblock
node ranges变成zone/``pg_data_t``/``struct page``/free-area containers。尚未执行
``memblock_free_all``，所以“free_area已初始化”不等于普通RAM已进入buddy free lists。

HugeTLB CMA与boot pages都由build/effective options选择
----------------------------------------------------

``hugetlb_cma_reserve`` 只在arch/build支持且 ``hugetlb_cma=``、per-node设置或相关policy给出非0
size时声明CMA areas。它依据045的memory-node identity选择nodes，检查gigantic page对齐/size，再
通过CMA early declaration保留continuous ranges。

``hugetlb_bootmem_alloc`` 随后处理boot-time hstates与 ``default_hugepagesz/hugepagesz/hugepages``
组合；超出normal buddy maximum order的gigantic pages必须在memblock/CMA阶段取得，普通可由later
buddy满足的hstate不需要在这里全部分配。

fixed GRUB原始line没有这些options，但builtin command line与 ``.config`` 未固定，故只能写
conditional。HugeTLB也不同于THP：本章没有anonymous fault、khugepaged或user mapping。

``free_area_init`` 先固定arch zone PFN上界
------------------------------------------

``arch_zone_limits_init(max_zone_pfn)`` 在x86-64按build给DMA、DMA32、NORMAL等zone提供maximum PFN；
典型含义分别是legacy DMA低地址、32-bit DMA低4 GiB及其余direct-mapped normal RAM。
``ZONE_MOVABLE`` 不是硬件address limit，后面按 ``kernelcore/movablecore/movable_node`` 与node layout
单独选择start PFN。effective options未固定，所以不制造zone容量。

zone身份与E820 type不同：只有E820/memblock RAM中的actual pages才可成为present zone pages；落在
DMA32 address范围的ACPI/MMIO/reserved hole不会因此变可分配。

``sparse_init`` 先建立PFN-to-page寻址骨架
----------------------------------------

physical address space有PCI/firmware holes，SPARSEMEM按section只给存在/可能存在的ranges准备
metadata；SPARSEMEM_VMEMMAP提供virtually contiguous ``vmemmap``，使 ``pfn_to_page`` 可固定计算而
不用给所有不存在PFN分配平面array。具体memory model由build决定，本章不假定一定VMEMMAP。

接着从 ``memblock_start_of_DRAM`` 起为非MOVABLE zones填写
``arch_zone_lowest/highest_possible_pfn``，相邻zone前一end成为后一start；equal bounds表示empty。
``find_zone_movable_pfns_for_nodes`` 再处理per-node MOVABLE starts。

early node ranges同时建立subsection presence map
-----------------------------------------------

源码打印global zone ranges与movable starts，并遍历每个 ``for_each_mem_pfn_range``：输出node的
physical range，同时调用 ``sparse_init_subsection_map(start,nr_pages)``。subsection bitmap允许later
memory hotplug以小于whole section的粒度扩展；它不把offline/hole PFN变成present RAM。

每个possible node获得完整或offline ``pg_data_t``
----------------------------------------------

在pageflags layout、 ``nr_node_ids`` 与pageblock order确定后， ``for_each_node`` 遍历possible nodes。
045已有memory node data；没有 ``NODE_DATA(nid)`` 的memoryless/offline node由
``alloc_offline_node_data`` 补最小root。

``free_area_init_node`` 从memblock nid ranges计算node start/end、spanned与present pages，并初始化
node内zones。 ``spanned_pages`` 包括start到end之间holes， ``present_pages`` 只计actual RAM；PCI
hole/firmware gap必须从present统计扣除。

有present pages的node才设置 ``N_MEMORY`` 并进一步检查normal/high memory state；随后每个
``N_MEMORY`` node执行 ``sparse_vmemmap_init_nid_late`` 的model-specific late work。

zone/free-area containers此时仍没有普通managed RAM
---------------------------------------------------

每个zone初始化locks、wait tables、watermark/stat skeleton、按order与migratetype划分的
``free_area[]`` 以及pageblock metadata。zone start/end确定不代表range内每个PFN有效；holes由present
calculation和memmap rules排除。

关键边界是：zone ``managed_pages`` 初始不把memblock仍占有的普通RAM计入，buddy lists也没有收到
这些pages。later ``memblock_free_all`` 才跳过reserved ranges，把其余pages按order释放给buddy并
增加managed counts。本章只建allocator containers。

``memmap_init`` 初始化per-PFN软件身份
------------------------------------

``calc_nr_kernel_pages`` 后， ``memmap_init`` 为可管理ranges的 ``struct page`` 建初始flags、refcount/
mapcount、zone/nid与reserved state。 ``struct page`` 是physical frame metadata，不保存page data。
若启用deferred struct-page init，大内存的部分metadata可留给later parallel work；这也不提前释放
相应physical pages。

pageblock order把更大range标成movable/unmovable/reclaimable/CMA等migration unit，供buddy
coalescing、compaction、THP/CMA与hot-remove以后使用。

最后只修hash policy与 ``high_memory`` boundary
-----------------------------------------------

``fixup_hashdist`` 在single-node等场景消除不需要的跨node hash distribution。 ``set_high_memory``
若arch尚未设置，就以 ``memblock_end_of_DRAM`` 建linear-map RAM end的virtual boundary；x86-64这里的
``high_memory`` 是历史名称，不表示32-bit HIGHMEM zone。

``mm_core_init_early`` 随即返回，下一条是generic ``jump_label_init``。slab、zonelists、page allocator
CPU-hotplug state与RAM free-to-buddy都属于later ``mm_core_init``/mem init阶段。

本章结束状态
------------

* current executor：CPU0上的 ``start_kernel``，下一条是 ``jump_label_init()``；
* CPU/mode：logical CPU0，x86-64 long mode，IF=0，无schedule/AP bring-up；
* HugeTLB CMA/boot pages：按build/effective hstate options reserve/allocate或no-op；
* memblock：仍拥有RAM与reserved ranges；
* zone PFN bounds/MOVABLE starts：已按arch、node与policy建立；具体值未固定；
* sparse memory/subsection：按configured memory model初始化；
* ``pg_data_t``：possible nodes有memory或offline node data；
* node present/spanned与 ``N_MEMORY`` state：已计算/设置；
* zones/pageblocks/``free_area[]``：containers已初始化；
* ``struct page``：按model完成required early init或保留deferred部分；
* buddy managed/free pages：普通RAM尚未由 ``memblock_free_all`` 交付；
* slab/per-CPU/scheduler：尚未初始化；
* ``high_memory``：linear-map RAM end boundary已条件设置。

关键边界
--------

#. HugeTLB CMA、HugeTLB boot pool与THP是不同机制。
#. zone是allocation constraint，不是E820 memory type。
#. possible PFN span、present RAM pages与managed buddy pages是三个计数。
#. SPARSEMEM/VMEMMAP由build决定，memory holes不会因virtual memmap存在而成为RAM。
#. ``pg_data_t`` 可为memoryless/offline node存在； ``N_MEMORY`` 只给present node设置。
#. ``free_area_init`` 建containers，不执行 ``memblock_free_all``。
#. ``struct page`` 是frame metadata；deferred init不表示physical page已可分配。
#. ``high_memory`` 在x86-64不是传统HIGHMEM pool。
#. 050出口仍不能把普通RAM描述成已进入buddy或slab可用。

下一入口
--------

第051章从generic：

.. code-block:: c

   jump_label_init();

开始，随后是 ``static_call_init``、 ``early_security_init``、bootconfig与command-line copies；
``setup_nr_cpu_ids`` 留到052。

资料
----

* `Linux 7.2-rc1固定提交：mm_core_init_early三条调用 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mm_init.c#L2688-L2696>`_；
* `Linux 7.2-rc1固定提交：free_area_init zone/node/sparse/memmap顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mm_init.c#L1809-L1920>`_；
* `Linux 7.2-rc1固定提交：x86 zone PFN limits <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init.c>`_；
* `Linux 7.2-rc1固定提交：HugeTLB CMA early reservation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/hugetlb_cma.c>`_；
* `Linux 7.2-rc1固定提交：HugeTLB bootmem allocation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/hugetlb.c>`_。
