第五十五章：Linux 怎样把 memblock 空闲页交给 buddy，并建立 slab 与 vmalloc？
=============================================================================

第五十四章结束时，GRUB 提供的命令行已经完成内核参数和 init 参数分发。

``start_kernel()`` 接下来执行：

.. code-block:: c

   random_init_early(command_line);
   setup_log_buf(0);
   vfs_caches_init_early();
   sort_main_extable();
   trap_init();
   mm_core_init();

本章追踪到 ``mm_core_init()`` 返回。

这是启动过程中的一个重要边界。

此前 Linux 主要依靠 memblock 在已知物理内存中做单向、不可回收的早期分配。第五十章虽然建立了 node、zone、``struct page`` 和 buddy 的数据结构，普通 RAM 仍未真正进入 buddy free list。

本章结束后：

* memblock 描述的可用普通页已经释放给 buddy；
* page allocator 可以提供按 order 分配的物理页；
* slab allocator 已完成早期正式初始化；
* vmalloc 地址空间管理已经建立；
* 许多依赖普通动态内存分配的子系统终于可以继续启动。

为什么先做 early random 初始化
----------------------------

第一条调用是：

.. code-block:: c

   random_init_early(command_line);

此时完整 timekeeping、interrupt 和普通 allocator 都尚未建立，随机子系统不能依赖后面的中断噪声、设备事件或常规动态分配。

该阶段收集架构能够早期提供的随机信息，并把启动命令行等当前可用状态混入早期随机池。

它的目标不是宣称系统熵已经充分，也不是向用户空间提供最终安全的随机输出，而是尽早避免所有启动都从完全相同的内部随机状态开始。

完整的：

.. code-block:: c

   random_init();

要等 timekeeping 建立后才会执行。

为什么释放 memblock 前还要做几次大分配
------------------------------------

源码在下列调用前写明：

.. code-block:: c

   /*
    * These use large bootmem allocations and must precede
    * initialization of page allocator
    */

   setup_log_buf(0);
   vfs_caches_init_early();

这些结构希望根据机器内存规模一次性建立较大的启动期 backing。

memblock 适合在物理地址图上寻找连续、对齐的区域，也能明确避开内核镜像、initramfs、ACPI 表、per-CPU first chunk 等 reserved ranges。

若等 buddy 和 slab 初始化后再做，分配路径、失败语义和早期对象布局都会更复杂。

``setup_log_buf(0)`` 做什么
--------------------------

x86 ``setup_arch()`` 期间已经尝试扩大过 printk ring buffer。

``start_kernel()`` 此处再次调用 ``setup_log_buf(0)``，确保命令行配置和当前内存条件要求的日志缓冲已经落实，并把必要的早期日志迁入最终 backing。

参数 ``0`` 表示这是通用启动阶段的设置调用，不是架构阶段强制执行的那次 early setup。

调用完成后，后续 buddy、slab、scheduler、IRQ 和设备初始化产生的大量日志有足够空间保存。

它没有初始化真正的 console 驱动。日志此时主要进入 printk ring buffer，正式 ``console_init()`` 还在更后面。

VFS 为什么在挂载文件系统前建立 cache 基础
--------------------------------------

``vfs_caches_init_early()`` 建立 VFS 最早的 inode/dentry cache 基础，包括按系统规模准备相应 hash table。

此时还没有：

* 根文件系统挂载；
* initramfs 解包；
* 磁盘文件系统读取；
* 用户进程打开文件。

VFS cache 仍必须提前存在，因为后续 pseudo filesystem、namespace、设备节点、initramfs 和根挂载路径都会依赖 inode 与 dentry 的全局索引结构。

这里建立的主要是底层表和早期 cache 条件，不代表完整 VFS 已经可供用户空间使用。

为什么异常表要排序
----------------

内核包含 ``__ex_table``，记录某些可能触发 fault 的指令地址，以及 fault 发生后应跳转的修复地址。

典型用途包括：

* 安全访问用户地址；
* 探测可能不存在的硬件或映射；
* 在可恢复 fault 后返回错误码，而不是让整个内核崩溃。

``sort_main_extable()`` 对主内核异常表排序，使后续 exception fixup 可以按地址快速查找。

模块拥有各自的异常表，模块加载时另行处理。这里排序的是 vmlinux 自身链接进来的主表。

``trap_init()`` 不等于打开中断
---------------------------

``trap_init()`` 是架构 trap 基础的通用调用点。

x86 在更早的汇编与架构入口中已经建立最低限度的 IDT 和异常入口，否则页表、CPU 探测和早期 C 代码发生 fault 时无法处理。

此处完成架构希望放在正式内存初始化前的 trap 收尾。

它不会把 ``IF`` 置 1，也不会让外部设备 IRQ 开始到达。当前仍满足：

.. code-block:: text

   early_boot_irqs_disabled = true
   local IRQ disabled

真正的 ``init_IRQ()`` 和 ``local_irq_enable()`` 还在后面。

``mm_core_init()`` 与 ``mm_core_init_early()`` 的区别
--------------------------------------------------

第五十章执行的：

.. code-block:: c

   mm_core_init_early();

主要建立内存管理的描述结构：

.. code-block:: text

   node
   zone
   sparse memory sections
   struct page metadata
   free_area[] lists

本章的：

.. code-block:: c

   mm_core_init();

开始建立真正可供内核普遍使用的 allocator，并完成从 boot-time allocator 到 runtime allocator 的交接。

两个函数不能合并理解：

.. code-block:: text

   mm_core_init_early()
       建立地图、账本和空链表

   mm_core_init()
       把可用页放入账本并启动正式分配器

架构内存预初始化
--------------

``mm_core_init()`` 首先调用：

.. code-block:: c

   arch_mm_preinit();

固定 x86-64 实现进入：

.. code-block:: c

   pci_iommu_alloc();

它为 x86 PCI/IOMMU 相关内存管理准备必要资源。

这个调用必须早于普通 allocator 全面使用，又必须在前面的 CPU、NUMA 与内存图已经足够稳定后执行。

零页为什么需要正式 PFN
--------------------

随后执行：

.. code-block:: c

   init_zero_page_pfn();

x86 的 ``empty_zero_page`` 在 BSS 清零时已经全为零。

现在内核通过 ``virt_to_page()`` 和 ``page_to_pfn()`` 得到它对应的 ``struct page`` 与 PFN，并保存 ``zero_page_pfn``。

匿名只读零映射可以让许多尚未写入的虚拟页共享同一物理零页。发生写入时，再通过缺页异常分配独立页面。

在 ``struct page`` 和正式页模型建立前，仅知道有一块全零内存还不够；内存管理代码需要能把它纳入 PFN/page 体系。

zonelist 把 zone 变成分配搜索顺序
--------------------------------

第五十章已经建立每个 node 中的 zone。

``build_all_zonelists(NULL)`` 进一步为每个 node 构造分配 fallback 顺序。

一次 ``alloc_pages()`` 不只是查看“本 node 的 ZONE_NORMAL”。根据 GFP mask、NUMA policy 和内存压力，它可能依次考虑：

* 本地 node 的目标 zone；
* 本地其他兼容 zone；
* 距离较近的远端 node；
* 允许 fallback 的其他 zone。

zonelist 把这些规则预先组织好，使热路径不必每次重新计算完整 node/zone 顺序。

page allocator 注册 CPU hotplug 支持
----------------------------------

``page_alloc_init_cpuhp()`` 把 page allocator 的 per-CPU page list 生命周期接入 CPU hotplug 状态机。

后面每个 CPU 上线时，需要准备自己的 page allocator 本地缓存；下线时，需要把缓存页排回全局 zone，避免空闲页滞留在已经停止的 CPU 上。

此时 AP 尚未启动。这里建立 callback 关系和 CPU0 所需基础，不发送 INIT/SIPI。

内存调试与硬化为什么要在释放页面前决定
------------------------------------

``mem_debugging_and_hardening_init()`` 根据构建配置和 early parameters 决定：

* page poisoning；
* debug page allocation；
* ``init_on_alloc``；
* ``init_on_free``；
* page sanity checking。

这些策略会改变页面第一次进入 allocator、被分配或释放时的处理方式。

必须在大量普通 RAM 进入 buddy 前确定，否则一部分页面会按旧规则进入 allocator，另一部分按新规则处理，启动后的安全和调试语义不一致。

函数还通过 static key 让关闭的调试功能在热路径上接近零开销。

在 buddy 出现前预留调试 backing
----------------------------

随后若配置启用，内核准备：

* page extension metadata；
* KFENCE pool 与 metadata；
* KMSAN shadow；
* stack depot early backing；
* KHO 相关内存。

这些设施有的需要较大连续区域，有的必须覆盖从 allocator 启动开始发生的最早分配。

所以它们在 ``memblock_free_all()`` 前完成预留和基础初始化。

真正的交接点：``memblock_free_all()``
------------------------------------

核心调用是：

.. code-block:: c

   memblock_free_all();

源码对它的定义非常直接：

.. code-block:: text

   release free pages to the buddy allocator

这才是普通 RAM 真正进入 buddy 的时刻。

此前 ``free_area[]`` 虽然已经存在，``nr_free_pages()`` 并不代表所有可用物理 RAM 都在 buddy 中。

释放前先处理未使用 memmap
------------------------

``free_unused_memmap()`` 回收不需要的 memory map backing，并避开 SPARSEMEM 中不存在的 section。

物理地址图可能包含洞：

.. code-block:: text

   RAM
   MMIO hole
   RAM

不存在的 PFN 不需要永久保留有效 ``struct page`` backing。回收这些区域可减少 metadata 浪费。

为什么重新清零 ``managed_pages``
-------------------------------

``reset_all_zones_managed_pages()`` 先把各 zone 的 ``managed_pages`` 归零。

随后每个真正释放给 buddy 的页面会重新计入 managed pages。

这种做法避免把：

* reserved 页面；
* 不存在的洞；
* NOMAP 区域；
* 内核镜像和启动数据；
* 尚不能管理的页面；

错误统计成 allocator 可管理 RAM。

reserved 页面先标记 ``PageReserved``
----------------------------------

``memmap_init_reserved_pages()`` 遍历 memblock reserved ranges，为对应 ``struct page`` 设置 node 信息，并标记 ``PageReserved``。

这些页面包括前面明确保留的内核镜像、页表、固件表、initramfs、per-CPU backing 等。

设置完成后，释放循环只处理 free mem ranges，不会把这些仍有用途的页加入 buddy。

free range 是 ``memory - reserved``
---------------------------------

``free_low_memory_core_early()`` 使用：

.. code-block:: c

   for_each_free_mem_range(...)

它遍历的是 memblock ``memory`` 中扣除 ``reserved`` 后的区间。

这正是早期 memblock 模型的核心：

.. code-block:: text

   discovered RAM
   - kernel image
   - page tables
   - initramfs
   - ACPI/firmware reserved
   - per-CPU first chunk
   - early allocator objects
   - other explicit reservations
   = pages that may enter buddy

不是所有 E820 RAM 都会被无条件释放。

为什么按最大对齐 order 释放
-------------------------

``__free_pages_memory()`` 不逐页固定以 order 0 释放。

它根据当前 PFN 对齐和剩余长度，选择尽可能大的合法 order：

.. code-block:: c

   order = min(MAX_PAGE_ORDER, __ffs(start));

然后在区间边界内调用：

.. code-block:: c

   memblock_free_pages(start, order);

例如一个对齐良好的大区间可以直接以较大块进入 buddy，而不是先插入数千个 order-0 页再不断合并。

这既减少启动时间，也让 buddy 从一开始就拥有合理的大块布局。

``totalram_pages`` 在这里获得真实值
--------------------------------

释放循环返回加入 buddy 的页数：

.. code-block:: c

   pages = free_low_memory_core_early();
   totalram_pages_add(pages);

从这里开始，``totalram_pages()`` 反映正式 page allocator 管理的普通 RAM，而不是固件报告的原始物理 RAM 总量。

两者之间的差值包含 reserved、固件、内核和其他不可分配区域。

memblock 是否立刻消失
------------------

``memblock_free_all()`` 把 free RAM 的所有权交给 buddy，但不会在这一行把所有 memblock 描述结构立即抹除。

后续少量启动代码仍可能查询保留区或内存布局，最终再根据配置 discard 可丢弃的 memblock metadata。

正确理解是：

.. code-block:: text

   before memblock_free_all
       memblock owns ordinary free RAM

   after memblock_free_all
       buddy owns ordinary free RAM
       memblock records may still temporarily exist

x86 ``mem_init()`` 标记 bootmem 时代结束
-------------------------------------

接下来调用架构实现：

.. code-block:: c

   mem_init();

固定 x86-64 实现首先设置：

.. code-block:: c

   after_bootmem = 1;

这表示依赖 bootmem/memblock 特殊阶段的代码应切换到正式运行期语义。

它随后调用 hypervisor 的 ``init_after_bootmem()`` hook，让虚拟化平台在普通页面已经进入 freelist 后完成相关收尾。

注册 boot memory 页面信息
------------------------

``register_page_bootmem_info()`` 为需要保留的启动内存页面登记 metadata，特别是 NUMA 或 HugeTLB vmemmap 优化路径需要的信息。

源码强调它必须在 ``memblock_free_all()`` 后执行，因为 deferred ``struct page`` 可能直到前一步才得到完整初始化。

预分配 vmalloc 顶层页表
---------------------

x86 ``mem_init()`` 还执行：

.. code-block:: c

   preallocate_vmalloc_pages();

它遍历 ``VMALLOC_START`` 到 ``VMEMORY_END``，预分配所有进程页表之间必须同步的高层页表结构。

vmalloc 的低层映射以后按需建立，但顶层同步层不能在任意时刻缺失，否则新进程页表可能看不到后来创建的 kernel vmalloc mapping。

分配失败会 panic，因为继续运行会产生不一致的 kernel address space。

``kmem_cache_init()`` 建立 slab 基础
----------------------------------

buddy 能分配整页或 ``2^order`` 连续页，但内核大量对象远小于一页：

.. code-block:: text

   task_struct
   inode
   dentry
   file
   vm_area_struct
   kmalloc objects

``kmem_cache_init()`` 在 buddy 之上建立 slab allocator 的核心 cache 和 ``kmalloc-*`` 体系。

从这里开始，大量代码可以使用：

.. code-block:: c

   kmalloc()
   kzalloc()
   kmem_cache_alloc()

而不必为每个小对象消耗完整页面。

这仍不是 slab 的全部晚期收尾。``kmem_cache_init_late()`` 要在中断启用后继续执行，所以本章结束时应称为“slab 基础已经可用”，不能称为所有 slab 功能全部完成。

为什么 page owner 要等 buddy 和 slab
----------------------------------

page owner 等调试设施需要：

* 页面已经属于 buddy；
* 能使用 slab 分配 stack depot 或辅助对象。

因此 ``page_ext_init_flatmem_late()``、``kmemleak_init()`` 等放在 ``kmem_cache_init()`` 后。

这体现了启动顺序的真实依赖：调试 allocator 的工具本身也依赖 allocator。

页表锁和页表 cache
----------------

``ptlock_cache_init()`` 与 ``pgtable_cache_init()`` 建立页表相关的小对象 cache。

后续创建进程地址空间时，大量页表页和页表锁需要高频分配。现在 buddy 与 slab 都可用，才适合建立这些运行期 cache。

``vmalloc_init()`` 建立非连续物理页映射管理
---------------------------------------

buddy 适合物理连续页，slab 适合小对象。

内核还需要“虚拟地址连续、物理页可以分散”的大块空间，这由 vmalloc 提供：

.. code-block:: text

   contiguous kernel virtual range
       → page A
       → page F
       → page C
       → ...

``vmalloc_init()`` 建立 vmalloc/vmap 区域的管理结构，使后续 ``vmalloc()``、``vmap()``、ioremap 辅助路径等能够分配和追踪 kernel virtual areas。

x86 ``mem_init()`` 先预分配必要高层页表，通用 ``vmalloc_init()`` 再建立区域 allocator，两步共同完成运行基础。

espfix 与 PTI 为什么在这里收尾
----------------------------

``init_espfix_bsp()`` 为 boot CPU 建立 x86-64 espfix 相关映射，处理某些从 16 位栈段返回时的历史硬件语义。

随后 ``pti_init()`` 在 espfix 已准备后完成 Page Table Isolation 相关初始化。

这些机制需要正式页分配和 vmalloc 基础，又必须在第一个非 init thread 创建前完成，因此位于 ``mm_core_init()`` 尾部。

最后的内存 cache 与 executable memory
-----------------------------------

``mm_cache_init()`` 建立 ``mm_struct`` 等内存管理对象的 cache。

``execmem_init()`` 建立内核可执行内存分配基础，供后续模块、BPF、trampoline 或架构动态代码路径使用。

具体可执行内存策略受架构和构建配置影响，但它依赖前面正式 virtual memory allocator 已经存在。

本章结束后的 allocator 层次
-------------------------

此时可以把内存分配层次画成：

.. code-block:: text

   physical RAM
       ↓
   memblock discovered/reserved map
       ↓ memblock_free_all()
   buddy page allocator
       ├─ order-0 pages
       ├─ higher-order physically contiguous blocks
       ↓
   slab / kmalloc caches
       └─ small kernel objects

   scattered physical pages
       ↓ page-table mappings
   vmalloc / vmap virtual ranges

memblock 的主导阶段结束，正式运行期 allocator 已接管。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``mm_core_init()`` 已返回，``maple_tree_init()`` 尚未调用；
* CPU：仍只有 CPU0 online；
* mode：64 位 long mode；
* current task：``init_task``；
* interrupts：仍关闭；
* GRUB 命令行：已完成内核参数与 init 参数分发；
* node/zone/``struct page``：已建立；
* memblock free RAM：已释放给 buddy；
* buddy allocator：已拥有普通可分配页；
* ``totalram_pages``：已按真正释放的页数更新；
* x86 bootmem 阶段：``after_bootmem = 1``；
* slab：``kmem_cache_init()`` 已完成，基础分配可用，late 阶段尚未执行；
* vmalloc：管理结构已建立；
* page-table、``mm_struct`` 与 executable-memory cache：已建立基础；
* scheduler：尚未初始化；
* external IRQ：尚未启用；
* AP：尚未收到 INIT/SIPI；
* console：正式初始化尚未执行；
* initramfs：尚未解包；
* PID 1：尚未创建。

下一条控制流是：

.. code-block:: c

   maple_tree_init();

随后 ``start_kernel()`` 将继续 poking、ftrace、early trace，并进入 ``sched_init()``。

资料
----

* `Linux 6.12.95 init/main.c：random、bootmem 分配与 mm_core_init 调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 mm/mm_init.c：mm_core_init 完整初始化顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mm_init.c>`_
* `Linux 6.12.95 mm/memblock.c：memblock_free_all 与 free_low_memory_core_early <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memblock.c>`_
* `Linux 6.12.95 arch/x86/mm/init_64.c：x86 mem_init 与 vmalloc 页表预分配 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init_64.c>`_
* `Linux 6.12.95 mm/slub.c：SLUB/kmem_cache_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/slub.c>`_
* `Linux 6.12.95 mm/vmalloc.c：vmalloc_init 与 vmap area 管理 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/vmalloc.c>`_
* `Linux 6.12.95 fs/dcache.c：VFS early cache 初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/fs/dcache.c>`_