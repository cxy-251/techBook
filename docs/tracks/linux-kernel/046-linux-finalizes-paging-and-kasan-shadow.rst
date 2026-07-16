第四十六章：Linux 怎样完成 CMA、paging hook 与 KASAN shadow 收尾？
===================================================================

第四十五章结束时，CPU0仍在 ``setup_arch``、IF=0；early MADT只登记了LAPIC physical address，
尚未枚举processor entries。 ``initmem_init`` 已给 ``memblock.memory`` 建立NUMA node identity，
direct map与active ``init_top_pgt`` 则在第四十三章就已完成。当前入口是：

.. code-block:: c

   dma_contiguous_reserve(max_pfn_mapped << PAGE_SHIFT);

本章按fixed Linux 7.2-rc1继续到 ``sync_initial_page_table()`` 返回。它在buddy allocator接管前完成
条件CMA/crashkernel reservation与early xHCI DbC console setup，调用native paging hook；若编入
KASAN，再临时切换CR3重建正式shadow。它不会full-parse MADT，也不启动AP或普通IRQ。

global CMA size先由early option或build policy选择
-----------------------------------------------

未编入CMA时 ``dma_contiguous_reserve`` 是inline no-op。有效实现先从 ``cma=`` early option得到
size/base/limit；若没有该option，再按build在fixed MiB、physical-memory percentage、二者minimum
或maximum中选择 ``selected_size``。size为0或default area已经由reserved-memory路径建立时，不再
声明第二个global area。

fixed GRUB字符串没有 ``cma=``，但effective builtin command line与 ``.config`` 未固定，因此不能
断言“没有CMA”或制造具体MiB值。函数执行本身也不表示area存在；只有
``dma_contiguous_reserve_area``/``cma_declare_contiguous`` 成功后，才形成memblock reservation与
``dma_contiguous_default_area``。

``max_pfn_mapped`` 是default limit，不是不可覆盖的总规则
---------------------------------------------------------

``setup_arch`` 传入的limit是：

.. code-block:: c

   max_pfn_mapped << PAGE_SHIFT

没有user limit时，它约束global CMA search的exclusive physical end，使早期会访问的area落在已知
direct-map frontier内。但 ``cma=...@base-limit`` 提供的非0 ``limit_cmdline`` 会替换传入limit；
fixed source还会在global area后调用 ``dma_numa_cma_reserve``，按 ``numa_cma=``、 ``cma_pernuma=``
或per-node build policy分别声明node-local areas。

因此旧稿把传入值写成“所有CMA绝对不能超过的上界”过强。可靠结论是：它是global default search
limit；explicit early policy和per-NUMA path各有自己的参数。任何失败只记录/返回，不把一个未成功
声明的range当成reserved。

crashkernel在SRAT/NUMA之后选择，避免hotpluggable memory
---------------------------------------------------------

下一条 ``arch_reserve_crashkernel`` 首先检查 ``CONFIG_CRASH_RESERVE``。启用时，它用effective
``boot_command_line`` 与 ``memblock_phys_mem_size`` 解析 ``crashkernel=`` 的base/size、low、high与
CMA部分；parse失败或无option就返回，Xen PV domain还会明确忽略请求。

成功才依次调用：

.. code-block:: c

   reserve_crashkernel_generic(...);
   reserve_crashkernel_cma(cma_size);

这个位置在NUMA/SRAT之后，使generic reservation能够避开标成hotpluggable的memory。fixed GRUB原始
字符串没有 ``crashkernel=``，但builtin line未知，所以只能记录为条件路径，不能像旧稿那样把
“本次必然无crashkernel reservation”写成fixed事实。

它与initramfs/CMA是三种所有权：initramfs是当前boot输入，crashkernel为未来kdump长期保护，CMA
则保留给以后可迁移页支持的contiguous allocator；都可体现在memblock reserved，却不能互换。

xDBC只有先前early parameter已定位DbC时才能setup
--------------------------------------------------

源码随后执行：

.. code-block:: c

   if (!early_xdbc_setup_hardware())
       early_xdbc_register_console();

未编入 ``CONFIG_EARLY_PRINTK_USB_XDBC`` 时setup stub返回 ``-ENODEV``，register stub为空。即使编入，
先前也必须由early-printk parameter path找到xHCI controller、映射BAR并定位Debug Capability，使
``xdbc.xdbc_reg`` 非NULL；否则setup仍返回 ``-ENODEV``。

真实setup先做BIOS ownership handoff，初始化raw spinlock，再建立DbC event/in/out rings与DMA
buffers、等待host connection。失败会释放rings与memblock pages、unmap xHCI并返回error；只有返回
0才尝试register console。register又在已有其他 ``early_console`` 时返回，避免覆盖先选中的early
console。

fixed GRUB line只有 ``console=ttyS0``，没有 ``earlyprintk=xdbc``；builtin line/device CLI未知，故
当前通常是未setup路径，但保持条件。 ``console=ttyS0`` 也不会在本次DbC call中注册正式serial
console。

native x86-64 paging hook不重建direct map
-----------------------------------------

``x86_init.paging.pagetable_init`` 在ordinary PC初始化表中指向 ``native_pagetable_init``；x86-64
把这个名字macro到 ``paging_init``。Xen PV等平台可以换hook，但fixed QEMU q35不是Xen PV入口，
因此执行：

.. code-block:: c

   node_clear_state(0, N_MEMORY);
   node_clear_state(0, N_NORMAL_MEMORY);

它只清掉编译期默认node 0的两种memory-state bits，后续zone初始化会根据真实node/PFN ranges重新
设置。它不遍历E820、不建立PTE、不load CR3，也不启动buddy；direct map继续使用043建立的
``init_top_pgt``。

``kasan_init`` 在未启用build中完全为空
---------------------------------------

若没有 ``CONFIG_KASAN``，arch header提供inline no-op，控制流直接去
``sync_initial_page_table``。是否启用没有由fixed commit决定，因为最终 ``.config`` 未提供。

启用时，039的 ``kasan_early_init`` 已把 ``early_top_pgt`` 与 ``init_top_pgt`` 中整个shadow范围
临时指向共享early page-table/page，保证最早compiler instrumentation不会fault。现在memblock、
direct map和NUMA nid已可用，正式 ``kasan_init`` 才能为需要真实backing的shadow分配独立pages。

施工前先复制正式root并临时切回 ``early_top_pgt``
--------------------------------------------------

函数先执行：

.. code-block:: c

   memcpy(early_top_pgt, init_top_pgt, sizeof(early_top_pgt));

5-level paging时，KASAN shadow end与kernel/modules/EFI等共享最后一个PGD，源码还复制对应P4D到
``tmp_p4d_table``，让施工root保留shadow end之外的映射。随后CPU0执行：

.. code-block:: c

   load_cr3(early_top_pgt);
   __flush_tlb_all();

active root暂时变成正式root的安全副本，内核才能清 ``init_top_pgt`` 的KASAN shadow top entries而
不拆当前正在使用的页表。这里的 ``early_top_pgt`` 已不是039内容不变的旧root，而是刚复制的新
施工快照。

正式shadow按 ``pfn_mapped[]`` 而不只按free RAM建立
--------------------------------------------------

``clear_pgds`` 清出shadow range后，源码先给shadow起点到 ``PAGE_OFFSET`` 对应位置恢复共享early
shadow，然后遍历043记录的每个 ``pfn_mapped[]`` range。 ``map_range`` 把mapped PFN range换成
shadow virtual range，并用 ``early_pfn_to_nid(range->start)`` 选择allocation node。

这里的输入是actual direct-map coverage，不应缩写成“仅free RAM”：它包含memblock RAM，也包含
x86明确无条件映射的ISA compatibility range；reserved-over-RAM同样需要可访问性shadow。E820 hole
是否属于ordinary RAM仍由memblock决定，KASAN mapping不会改变physical ownership。

``early_alloc`` 从 ``__pa(MAX_DMA_ADDRESS)`` 以上、 ``MEMBLOCK_ALLOC_ACCESSIBLE`` 以下尝试按nid
分配。PUD/PMD完整对齐且CPU支持时可取得1 GiB/2 MiB continuous backing并建立huge shadow mapping；
失败就回退到lower-level page tables/4 KiB pages，必须的PAGE_SIZE allocation失败会panic。

地址空洞继续共享early shadow或只建浅层结构
---------------------------------------------

除了 ``pfn_mapped[]``，函数还处理direct-map end与vmalloc之间、CPU entry area、kernel
``_stext.._end`` 及shadow末端等边界。当前没有真实object backing的大区间继续映射共享early
shadow，避免为整个virtual hole分配独立shadow pages。

``CONFIG_KASAN_VMALLOC`` 启用时，vmalloc shadow不在boot时填满lower levels，只预建PGD/P4D，之后
随vmalloc allocation按需populate；关闭时则用early shared shadow覆盖该range。CPU entry area只给
共享前段建立正式shadow，随机放置的per-CPU areas以后逐CPU映射，避免预映整个512 GiB window。

正式shadow完成后切回 ``init_top_pgt`` 并只读化共享页
-------------------------------------------------------

函数执行：

.. code-block:: c

   load_cr3(init_top_pgt);
   __flush_tlb_all();

随后清零 ``kasan_early_shadow_page``，把所有共享early-shadow PTE改为kernel read-only/encrypted
appropriate protection，再flush一次。这样意外写入代表空洞的共享shadow会fault，而不是静默污染
所有共享地址。最后令 ``init_task.kasan_depth=0`` 并进入 ``kasan_init_generic``。

无论是否启用KASAN，本章出口active root都回到 ``init_top_pgt``。

``sync_initial_page_table`` 在x86-64是compile-time no-op
-------------------------------------------------------

公共 ``setup_arch`` 注释要求“sync back kernel address range”，但x86-64定义：

.. code-block:: c

   #define swapper_pg_dir init_top_pgt
   static inline void sync_initial_page_table(void) { }

因此当前架构不会复制另一张initial table。该工作只对x86-32等实现有意义；调用名存在不等于fixed
x86-64执行了一次页表同步。

本章结束状态
------------

* current executor：CPU0上的 ``setup_arch``，下一条是 ``tboot_probe()``；
* CPU/mode：BSP/logical CPU0，x86-64 long mode，IF=0，无schedule/AP bring-up；
* NUMA：memory-node identity保留，full MADT processor enumeration尚未发生；
* CMA：按build/effective global/per-node policy成功reserve或no-op/fail；具体areas未固定；
* crashkernel：按effective ``crashkernel=`` 条件reserve；GRUB原始line本身未请求；
* xDBC early console：仅在DbC已定位、hardware setup成功且没有existing early console时注册；
* native paging hook：只清node 0 memory-state defaults；direct map未重建；
* KASAN disabled path： ``kasan_init`` no-op；
* KASAN enabled path：正式shadow已加入 ``init_top_pgt``，共享early shadow已清零并只读；
* active CR3：最终为 ``init_top_pgt``；KASAN path中曾临时使用复制后的 ``early_top_pgt``；
* ``sync_initial_page_table``：x86-64 no-op；
* zones/buddy：仍未初始化；
* ACPI full MADT/IOAPIC：尚未在本章执行。

关键边界
--------

#. ``max_pfn_mapped`` 是global CMA default limit；explicit ``cma=`` limit与per-node CMA另有路径。
#. CMA call成功返回不等于一定有area；size=0、已有default、declare失败都是不同no-area边界。
#. crashkernel必须在NUMA后reserve，但是否存在取决于build与effective command line。
#. xDBC setup返回0才register；未编入支持的stub返回 ``-ENODEV``，不会注册console。
#. ``console=ttyS0`` 与early xDBC console是不同入口。
#. native x86-64 ``paging_init`` 只清node-state bits，不再建direct map或切CR3。
#. KASAN shadow按 ``pfn_mapped[]`` coverage建立，不能缩写成只覆盖free RAM。
#. KASAN临时CR3使用刚从 ``init_top_pgt`` 复制的施工root，不是恢复039旧页表状态。
#. KASAN VMALLOC只浅层预建与全range shared-shadow是build-time两条路径。
#. enabled KASAN最终切回 ``init_top_pgt`` 并把共享early shadow只读化。
#. x86-64 ``sync_initial_page_table`` 为空，不制造一次不存在的table copy。
#. 046出口仍未枚举MADT processor entries；047从tboot/vsyscall/early quirks继续。

下一入口
--------

第047章从：

.. code-block:: c

   tboot_probe();

开始。进入前active root是 ``init_top_pgt``，possible CPU space还只有early command-line limit前的
上限，full ACPI/MP firmware enumeration尚未执行。

资料
----

* `Linux 7.2-rc1固定提交：CMA到initial-page-table sync调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L1192-L1215>`_；
* `Linux 7.2-rc1固定提交：global与per-NUMA CMA reservation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/dma/contiguous.c#L139-L322>`_；
* `Linux 7.2-rc1固定提交：x86 crashkernel effective-line解析 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L608-L628>`_；
* `Linux 7.2-rc1固定提交：xHCI DbC setup与失败回滚 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/usb/early/xhci-dbc.c#L657-L687>`_；
* `Linux 7.2-rc1固定提交：x86-64 native paging hook只清node state <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init_64.c#L823-L843>`_；
* `Linux 7.2-rc1固定提交：x86-64 KASAN shadow与临时CR3 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/kasan_init_64.c#L341-L425>`_；
* `Linux 7.2-rc1固定提交：x86-64 initial table sync为空 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/pgtable_64.h#L22-L31>`_。
