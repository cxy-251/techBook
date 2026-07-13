第四十六章：Linux 怎样完成 x86-64 paging 收尾并建立 KASAN shadow？
====================================================================

第四十五章结束时，Linux 已经从 MADT/MP table 建立早期 CPU/APIC 拓扑，并通过 SRAT 或 single-node fallback 给 ``memblock.memory`` 标注 NUMA node。

当前下一条调用是：

.. code-block:: c

   dma_contiguous_reserve(max_pfn_mapped << PAGE_SHIFT);

本章追踪到：

.. code-block:: c

   sync_initial_page_table();

返回。这个阶段容易被函数名误导：第四十三章已经建立 direct map 并切换到 ``swapper_pg_dir``，现在不是再次从零构造全部物理映射，而是在 NUMA 已知后补齐连续 DMA、crashkernel、架构 paging hook 与条件 KASAN shadow。

为什么 CMA 必须在 page allocator 前预留
------------------------------------

``dma_contiguous_reserve()`` 为 Contiguous Memory Allocator（CMA）处理启动期保留。

某些设备或子系统需要一大片物理连续页，例如：

* 大型 DMA buffer；
* 摄像头、显示或多媒体设备；
* 不能使用 scatter-gather 的硬件；
* 可迁移普通页之后再回收连续区的场景。

普通 buddy allocator 一旦开始分散分配，想再找到大块连续物理内存会很困难。因此 CMA 在 memblock 阶段先圈出候选区域。

传入的上界是：

.. code-block:: c

   max_pfn_mapped << PAGE_SHIFT

表示 CMA early reservation 必须落在当前 direct map 能安全访问的物理范围内。

是否真正保留 CMA 区取决于：

* ``CONFIG_CMA``；
* 编译时默认大小；
* ``cma=`` 命令行；
* device tree 或平台预留；
* 可用 memblock 布局。

固定命令行没有 ``cma=``，因此不能凭本书主线断言一定存在一块具体大小的 CMA。函数仍按配置执行条件路径。

``crashkernel`` 为什么等 NUMA 后再处理
-------------------------------------

接着：

.. code-block:: c

   arch_reserve_crashkernel();

kdump 需要提前保留一段物理内存，用来装载崩溃捕获内核。主内核发生 panic 后，kexec 跳入这段预留内存中的第二个内核，避免依赖已经损坏的普通内存状态。

``arch_reserve_crashkernel()`` 解析：

.. code-block:: text

   crashkernel=
   crashkernel=,high
   crashkernel=,low
   crashkernel=,cma

它被放在 SRAT/NUMA 解析之后，是因为保留策略可能需要避开 hot-pluggable memory，或者选择适合 DMA/低端访问的 node 与地址范围。

当前固定命令行没有 ``crashkernel=``，因此主线不会创建 crash kernel reservation。

这与 initramfs 的保留性质不同：

.. code-block:: text

   initramfs     当前启动必须读取，后面可以释放原始归档页
   crashkernel   为未来 panic 准备，正常运行期间长期不可分配

早期 xHCI debug console 的最后机会
--------------------------------

随后：

.. code-block:: c

   if (!early_xdbc_setup_hardware())
       early_xdbc_register_console();

xDBC 是 USB 3 xHCI Debug Capability。若平台和配置支持，Linux 可以在普通 USB host controller driver、device model 和完整 console 子系统出现前，直接使用 xHCI debug capability 输出日志。

这里必须已经具备：

* direct map；
* memblock；
* 早期 PCI/MMIO 访问；
* 足够稳定的页表。

同时又必须早于普通 console/USB 初始化，才能用于调试更后面的启动故障。

固定 QEMU q35 是否提供可用 xDBC 取决于虚拟 xHCI 设备与启动配置；默认主线不假定存在，因此通常跳过注册。

``x86_init.paging.pagetable_init`` 是可替换的架构钩子
---------------------------------------------------

下一条：

.. code-block:: c

   x86_init.paging.pagetable_init();

``x86_init`` 是一组 x86 平台操作表。普通 PC 默认初始化为：

.. code-block:: c

   .paging = {
       .pagetable_init = native_pagetable_init,
   },

Xen 等平台可以在早期启动中替换这个函数指针，以执行自己的页表模型。

在 x86-64 上：

.. code-block:: c

   #define native_pagetable_init paging_init

因此固定普通 q35 路径最终调用 ``arch/x86/mm/init_64.c:paging_init()``。

一个容易写错的事实：这里没有重建 direct map
------------------------------------------

x86-64 的 ``paging_init()`` 非常短：

.. code-block:: c

   void __init paging_init(void)
   {
       node_clear_state(0, N_MEMORY);
       node_clear_state(0, N_NORMAL_MEMORY);
   }

它先清理静态默认的 node 0 memory-state 标记，后续 zone 初始化会根据真实 NUMA/PFN 范围重新设置。

所以调用名虽然叫 ``pagetable_init``，在当前 x86-64 native 路径中并不会：

* 再次遍历全部 E820；
* 重新创建 direct map；
* 再次装载 CR3；
* 启动 buddy allocator。

真正的大规模 direct-map 构造已经在第四十三章的 ``init_mem_mapping()`` 完成。

这个钩子保留宽泛名称，是为了兼容 x86-32 和 paravirtualized 平台的不同实现。

为什么紧接着调用 ``kasan_init()``
---------------------------------

``setup_arch()`` 随后调用：

.. code-block:: c

   kasan_init();

KASAN（Kernel Address Sanitizer）通过 shadow memory 记录内核地址对应内存的可访问状态，用于检测：

* heap/stack/global 越界；
* use-after-free；
* 某些无效对象访问。

典型 software KASAN 把一段内核内存映射到更小的 shadow 地址范围。每个 shadow byte 表示一组原始内存字节的可访问情况。

若内核没有启用相应 ``CONFIG_KASAN``，该调用编译为空实现。本书固定 Linux 版本没有固定 ``.config``，因此正文必须把它视为条件路径，不能声称每次启动都分配 KASAN shadow。

``kasan_early_init()`` 与现在的 ``kasan_init()`` 有什么区别
---------------------------------------------------------

第三十九章之前，``x86_64_start_kernel()`` 已调用 ``kasan_early_init()``。

早期版本的目标只是让编译器插桩在正式内存管理出现前不会因 shadow 缺失立即 page fault。它把广阔 shadow range 指向少量共享的 early shadow page/table。

现在 memblock、NUMA 和 direct map 已建立，``kasan_init()`` 才能为真实映射范围分配独立 shadow pages。

两阶段关系是：

.. code-block:: text

   kasan_early_init()
   → 临时共享 shadow，保证最早 C 代码可运行

   kasan_init()
   → 按实际 RAM/内核虚拟区建立正式 shadow

临时切回 ``early_top_pgt`` 的原因
--------------------------------

``kasan_init()`` 首先复制：

.. code-block:: c

   memcpy(early_top_pgt, init_top_pgt, sizeof(early_top_pgt));

然后暂时：

.. code-block:: c

   load_cr3(early_top_pgt);
   __flush_tlb_all();

原因是它需要清除并重建 ``init_top_pgt`` 中 KASAN shadow 对应的顶层 entry。如果 CPU 正在使用同一张正在拆改的页表，修改过程可能让当前执行代码瞬间失去必要映射。

因此 Linux 使用复制出的 ``early_top_pgt`` 作为临时安全页表，修改正式 ``init_top_pgt`` 的 shadow 部分。

这次 ``early_top_pgt`` 与启动最初的临时页表作用不同：它是从当前正式页表复制出的施工用副本。

KASAN 只为实际映射的 RAM 建立真实 shadow
---------------------------------------

``kasan_init()`` 遍历第四十三章记录的：

.. code-block:: c

   pfn_mapped[]

对每个已 direct-mapped 的 PFN range：

#. 将原始 direct-map 地址转换成 KASAN shadow 地址；
#. 根据 NUMA node 选择 memblock allocation node；
#. 分配 PGD/P4D/PUD/PMD/PTE；
#. 在对齐和 CPU 能力允许时使用 1 GiB 或 2 MiB huge shadow mapping；
#. 否则分配 4 KiB shadow page。

分配函数使用：

.. code-block:: c

   memblock_alloc_try_nid(..., nid)

第四十五章提前建立 NUMA node 归属，因此 KASAN shadow page 可以尽量从对应 node 分配。

这解释了本章顺序：

.. code-block:: text

   SRAT / NUMA node
   → paging hook
   → KASAN shadow allocation by node

KASAN shadow 不只覆盖 direct map
-------------------------------

正式初始化还处理：

* direct-map RAM；
* kernel image ``_stext`` 到 ``_end``；
* vmalloc range；
* modules range；
* CPU entry area 的共享部分；
* 不对应真实 RAM 的地址洞。

对当前尚无真实 backing 的大范围，Linux 可以继续映射只读 early shadow page，或者只预建 PGD/P4D 以便以后按需填充。

``CONFIG_KASAN_VMALLOC`` 开启时，vmalloc shadow 下层页表按实际 vmalloc allocation 动态建立，启动时只浅层预分配顶级结构，避免为整个巨大 vmalloc 空间立即消耗大量页表页。

切回 ``init_top_pgt``
--------------------

正式 shadow 建立后：

.. code-block:: c

   load_cr3(init_top_pgt);
   __flush_tlb_all();

CPU 回到包含新 KASAN shadow 的正式页表。

随后 Linux：

#. 清零共享 early shadow page；
#. 把 early shadow PTE 改成只读；
#. 再次刷新 TLB；
#. 清除 ``init_task.kasan_depth``；
#. 调用通用 ``kasan_init_generic()``。

把共享 early shadow 设为只读，可以发现后续代码错误地向“空洞地址对应的占位 shadow”写入，而不是静默破坏一页被大量地址共享的数据。

为什么 ``sync_initial_page_table()`` 在 x86-64 是空操作
----------------------------------------------------

KASAN 之后源码调用：

.. code-block:: c

   sync_initial_page_table();

注释写着“Sync back kernel address range”，容易让人以为这里复制整张页表。

但 x86-64 头文件定义：

.. code-block:: c

   static inline void sync_initial_page_table(void) { }

原因是 x86-64 中：

.. code-block:: c

   #define swapper_pg_dir init_top_pgt

当前正式内核页表本来就是 ``init_top_pgt``，不存在 x86-32 那种需要把正式 kernel range 同步回另一张 initial page table 的步骤。

所以固定主线执行到这里时，函数调用存在于公共顺序中，实际不生成代码。

这类“名字很重、当前架构为空”的入口必须在源码阅读中展开，否则容易虚构一次不存在的页表复制。

本章结束时页表处于什么状态
--------------------------

若 KASAN 未启用：

.. code-block:: text

   direct map / kernel map / fixmap 继续由 init_top_pgt 承载
   paging_init 只清理 node memory state
   sync_initial_page_table 为空

若 KASAN 启用：

.. code-block:: text

   init_top_pgt 新增正式 KASAN shadow mappings
   CR3 曾临时切到 early_top_pgt 施工副本
   最终重新加载 init_top_pgt
   TLB 已刷新

两种配置最终都停在同一个控制流位置。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* memblock RAM：已带 NUMA node 归属；
* CMA：已按配置完成条件预留；
* crashkernel：固定命令行未请求；
* early xDBC console：已完成条件探测；
* native paging hook：已执行，x86-64 对应 ``paging_init()``；
* direct map：沿用第四十三章建立的映射，没有在本章重建；
* KASAN：若配置启用，正式 shadow 已建立并由 ``init_top_pgt`` 承载；
* ``sync_initial_page_table()``：x86-64 为空操作；
* zone/buddy allocator：仍未完成；
* ACPI 完整 MADT/FADT/HPET 解析：仍在后面；
* ``setup_arch()``：仍未返回。

下一条控制流从：

.. code-block:: c

   tboot_probe();

继续，随后映射 vsyscall、完成 ACPI/SMP/APIC/IOAPIC 拓扑、注册 E820 资源、初始化 wall clock/MCE/unwind，并最终从 ``setup_arch()`` 返回。

资料
----

* `Linux 6.12.95 setup.c：CMA、crashkernel、paging hook、KASAN 与同步调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 x86_init.c：普通 PC 的 pagetable_init 默认函数指针 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/x86_init.c>`_
* `Linux 6.12.95 pgtable_types.h：x86-64 native_pagetable_init 映射为 paging_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/pgtable_types.h>`_
* `Linux 6.12.95 init_64.c：paging_init 的 x86-64 实现 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init_64.c>`_
* `Linux 6.12.95 KASAN init：shadow page-table 建立与 CR3 切换 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/kasan_init_64.c>`_
* `Linux 6.12.95 pgtable_64.h：swapper_pg_dir 与空的 sync_initial_page_table <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/pgtable_64.h>`_
* `Linux CMA 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/admin-guide/mm/cma_debugfs.rst>`_
* `Linux kdump 文档 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/admin-guide/kdump/kdump.rst>`_