第四十三章：Linux 怎样把 E820 RAM 变成 memblock 并建立 early direct map？
=============================================================================

第四十二章结束时，CPU0仍在 ``setup_arch``、IF=0，active CR3是 ``early_top_pgt``；working
E820已经完成到本阶段的修整， ``memblock.reserved`` 保护kernel、initramfs与low firmware对象，
但 ``memblock.memory`` 尚未导入RAM。当前入口是：

.. code-block:: c

   early_alloc_pgt_buf();

本章按fixed Linux 7.2-rc1继续到 ``setup_log_buf(1)`` call前。期间early brk提供第一批page-table
storage，E820 RAM进入memblock，普通PC保留real-mode trampoline， ``init_mem_mapping`` 建立
direct map并激活 ``init_top_pgt/swapper_pg_dir``，最后把memblock allocation limit扩展到已映射
physical frontier。

第一批页表页必须来自已经可访问的brk
--------------------------------------

``early_alloc_pgt_buf`` 用：

.. code-block:: c

   base = __pa(extend_brk(INIT_PGT_BUF_SIZE, PAGE_SIZE));

在尚未封存的 ``[__brk_base,__brk_limit)`` 中取得page-aligned连续buffer，并记录：

.. code-block:: text

   pgt_buf_start = base PFN
   pgt_buf_end   = next unused PFN
   pgt_buf_top   = exclusive end PFN

``INIT_PGD_PAGE_TABLES=4`` 是估算一组early mapping所需的table数；未编入
``CONFIG_RANDOMIZE_MEMORY`` 时总buffer为8页，编入时为16页。后者为memory KASLR可能跨越更多
top-level boundary留余量，不等于本机必然消耗16页。

这批页位于formal kernel/brk high mapping内，当前CPU已经能够清零和填写。它解决了direct map的
自举问题：尚未映射广泛RAM时，不能先从那些RAM取一页再通过 ``__va`` 写page-table entry。

``reserve_brk`` 先保护已用range，再关闭allocator
-----------------------------------------------

下一条调用检查 ``_brk_end>_brk_start`` 后执行：

.. code-block:: c

   memblock_reserve_kern(__pa_symbol(_brk_start),
                         _brk_end - _brk_start);
   _brk_start = 0;

reservation覆盖刚取得的pgt buffer以及更早的brk users。 ``_brk_end`` 保留当前边界值供
``init_mm.brk`` 与high-map cleanup使用；清0的是start sentinel，从这里以后再调用
``extend_brk`` 会触发 ``BUG_ON(_brk_start==0)``。

fixed ``alloc_low_pages`` 的通用源码确实还有“pgt buffer不足时先尝试mapped memblock，必要时
``extend_brk``”分支，但当前 ``setup_arch`` 已先封存brk。因此本章mapping阶段不能把
``extend_brk`` 描述成可靠的第三后备；它只能使用仍有余量的pgt buffer，或已经纳入
``[min_pfn_mapped,max_pfn_mapped)`` 的memblock RAM。top-down/bottom-up分步算法必须保证在buffer
耗尽前扩大这个mapped allocation window，否则启动失败。

``cleanup_highmap`` 把共享kernel subtree收紧到当前brk
------------------------------------------------------

x86-64实现遍历 ``level2_kernel_pgt``，保留从 ``_text`` 到
``roundup(_brk_end,PMD_SIZE)-1`` 的PMDs，清掉其前后的present entry。native路径此时
``max_pfn_mapped`` 尚为0，所以scan上界仍是 ``KERNEL_IMAGE_SIZE``；Xen可提供不同上界。

``early_top_pgt`` 与 ``init_top_pgt`` 的kernel high entry都引用这套下级subtree，所以修改同时
收紧active early root与即将启用的long-term root。函数没有立即执行独立global TLB flush；后面
``load_cr3(swapper_pg_dir)`` 与 ``__flush_tlb_all`` 才形成明确translation回收边界。

working E820 RAM现在才进入 ``memblock.memory``
-----------------------------------------------

``e820__memblock_setup`` 先在memory-hotplug build且 ``movable_node`` 开启时选择bottom-up
allocation；普通情况保持memblock默认方向。然后无条件设置：

.. code-block:: c

   memblock_set_current_limit(ISA_END_ADDRESS);
   memblock_allow_resize();

limit暂时是1 MiB，因为源码只保证该范围已经可访问；允许region arrays扩容也必须受这个limit和
041—042已建立的reserved ranges约束。

随后逐项遍历working ``e820_table``：

* ``E820_TYPE_SOFT_RESERVED`` 进入 ``memblock.reserved``，但不进入memory；
* ``E820_TYPE_RAM`` 通过 ``memblock_add`` 进入 ``memblock.memory``；
* ACPI、NVS、unusable、persistent或普通reserved types不作为normal memblock memory加入。

kernel、R/N等range仍可同时属于 ``memblock.memory`` 与 ``memblock.reserved``。前者表示physical
RAM候选，后者从候选中排除实际不可分配部分；direct mapping稍后仍会覆盖这类reserved-in-RAM
对象，使内核能够访问它们。

KHO scratch flag不等于cold boot开始使用KHO
--------------------------------------------

导入后源码调用：

.. code-block:: c

   memblock_mark_kho_scratch(0, SZ_1M);

Kexec Handover kernel可把allocator限制为scratch-only；low 1 MiB通常不会自然带KHO scratch flag，
所以这里临时标记它，允许real-mode trampoline等极早allocation在这种特殊入口继续工作。普通cold
boot没有设置scratch-only时，该flag不把low RAM变成一种新的独占allocator。

x86-64不执行32-bit ``max_pfn`` 以上memory remove。最后
``memblock_trim_memory(PAGE_SIZE)`` 把memory region start向上、end向下对齐，丢弃无法组成完整
4 KiB frame的边缘字节； ``memblock_dump_all`` 只输出状态，不改变所有权。

memory encryption与CoCo seed在memblock之后处理
-----------------------------------------------

``mem_encrypt_setup_arch`` 先取得 ``memblock_phys_mem_size``。host SEV-SNP路径可修RMP/E820状态；
guest memory-encryption路径按总内存调整SWIOTLB default size并要求virtio restricted memory access。
普通非加密q35路径在capability checks后返回；具体CoCo mode取决于未固定CPU/QEMU参数与build。

紧接着 ``cc_random_init`` 也只为encrypted guest执行。它必须从RDRAND收满256-bit seed，加入device
randomness后显式清stack buffer；任何一次完全取不到longs都会panic，因为CoCo threat model不能
信任host提供的entropy。非CoCo路径不创建这份seed。

四个EFI helper在当前BIOS入口逐项skip
------------------------------------

源码仍依次调用：

.. code-block:: c

   efi_find_mirror();
   efi_esrt_init();
   efi_mokvar_table_init();
   efi_reserve_boot_services();

前三项分别依赖EFI memmap/paravirt与相应table，最后一项遍历EFI boot-services descriptors并谨慎
reserve将来可释放的region。当前 ``EFI_BOOT/EFI_MEMMAP`` 未由SeaBIOS/GRUB i386-pc设置，所以
四次调用均在各自guard返回：没有mirrored-memory flag、ESRT/MOK table或EFI boot-services
reservation凭空产生。

MPC新buffer不是每次boot都预分配4 KiB
-------------------------------------

``e820__memblock_alloc_reserved_mpc_new`` 只有
``enable_update_mptable && alloc_mptable`` 同时成立时，才按 ``mpc_new_length`` 分配reserved
buffer。固定GRUB字符串没有 ``update_mptable`` 或 ``alloc_mptable``；built-in command line未固定，
因此当前结论是条件调用，不能像旧稿那样宣称无条件获得一页。

若编入 ``CONFIG_X86_CHECK_BIOS_CORRUPTION``， ``setup_bios_corruption_check`` 还会按early options/
default policy从低地址free mem ranges保留用于周期校验的areas；配置关闭时整段调用不存在，policy
关闭或size为0时helper返回。

ordinary x86-64为AP real-mode blob找low memory
---------------------------------------------

``x86_platform.realmode_reserve`` 在ordinary PC指向 ``reserve_real_mode``。当前x86-64 build的
real-mode blob size非0，helper在 ``realmode_limit=1MiB`` 以下page-align分配；成功时
``set_real_mode_mem`` 保存physical/virtual header位置。分配失败会记录“No memory below ...”，不
伪造trampoline address。

只要size非0，helper随后仍执行：

.. code-block:: c

   memblock_reserve(0, SZ_1M);
   memblock_clear_kho_scratch(0, SZ_1M);

所以成功ordinary路径的完整low 1 MiB都不再供normal allocation，刚才的临时KHO flag也被清除；
其中RAM仍保留在 ``memblock.memory`` 并将在direct map中可访问。reserved不等于unmapped。

此时只预留real-mode blob storage，尚未复制/relocate trampoline code，也没有发送INIT/SIPI；
``x86_platform.realmode_init`` 要到更后面才填内容。

``init_mem_mapping`` 先固定page-size与PCID能力
---------------------------------------------

入口依次调用 ``pti_check_boottime_disable``、 ``probe_page_size_mask`` 与 ``setup_pcid``。
``probe_page_size_mask`` 根据PSE、debug-pagealloc、PGE、1-GiB-page capability和build options选择
4 KiB/2 MiB/1 GiB leaf，并同步相关CR4/PTE masks。 ``setup_pcid`` 只有x86-64且CPU具备PCID时继续；
它还会因已知INVLPG microcode问题或不成立的PGE组合禁用PCID。

这些决定来自第041章识别的actual CPU与未固定config，正文不能保证一定使用1 GiB page或一定打开
PCIDE。

ISA range无条件映射，allocation身份保持reserved
-----------------------------------------------

x86-64 mapping end取 ``max_pfn<<PAGE_SHIFT``。源码先执行：

.. code-block:: c

   init_memory_mapping(0, ISA_END_ADDRESS, PAGE_KERNEL);

low 1 MiB即使含E820 holes也获得direct virtual mapping，供BIOS/trampoline等兼容访问；刚建立的
``memblock.reserved(0,1MiB)`` 仍阻止allocator使用。page-table presence与RAM/free identity没有
互相覆盖。

随后 ``init_trampoline`` 为以后AP启动保存top-level mapping entry。memory KASLR关闭时复制
direct-map首PGD entry；开启时只建立覆盖low 1 MiB的较窄PUD alias，以限制trampoline address-
space暴露。它不在此复制real-mode executable bytes。

其余direct map只遍历 ``memblock.memory``
------------------------------------------

``init_range_memory_mapping`` 使用 ``for_each_mem_pfn_range``，把请求大range与每段memblock RAM
求交，再调用 ``init_memory_mapping``。因此RAM两侧的PCI/MMIO holes不会被当作ordinary
``PAGE_KERNEL`` memory线性铺满；reserved-over-RAM对象仍被映射，因为它们仍属于memory集合。

``split_mem_range`` 按对齐、CPU page-size mask与周边RAM连续性把每段分为4 KiB、2 MiB或条件
1 GiB ranges； ``kernel_physical_mapping_init`` 再逐级建立/复用PGD/P4D/PUD/PMD/PTE。每次成功
调用 ``add_pfn_range_mapped`` 合并 ``pfn_mapped[]``，并推进 ``max_pfn_mapped`` 与4 GiB以下的
``max_low_pfn_mapped``。这些变量表示实际direct-map coverage，不是042的E820 end边界。

top-down与bottom-up都用小步扩大mapped allocation window
-------------------------------------------------------

默认top-down路径先尝试在目标range顶端取得一个2 MiB对齐block，立即free后把其end作为映射自举
锚点；从2 MiB step开始向下建图，累计映射足够后逐级放大step，最后补顶部余段。

若 ``movable_node`` 令memblock bottom-up，源码先映 ``[kernel_end,end)``，使page tables可从kernel
上方mapped RAM取得，再映 ``[1MiB,kernel_end)``。两种方向都依赖前面预留的pgt buffer启动，之后
只从已经记录的mapped PFN window取得新table pages。

``alloc_low_pages`` 返回页会经 ``__va`` 清零。由于本章已经 ``_brk_start=0``，buffer不足时的
current有效扩展路径是 ``memblock_phys_alloc_range``；不能依赖通用函数中仍存在、但此时会触发
brk sentinel的 ``extend_brk`` fallback。

active CR3到这里才切换为 ``init_top_pgt``
------------------------------------------

mapping遍历结束后，x86-64若 ``max_pfn>max_low_pfn`` 还把 ``max_low_pfn=max_pfn``；这是64-bit
memory management的后续边界，不等于 ``max_low_pfn_mapped`` 被改名。

然后：

.. code-block:: c

   load_cr3(swapper_pg_dir);
   __flush_tlb_all();

而x86-64 ``swapper_pg_dir`` 就是 ``init_top_pgt``。CPU0从 ``early_top_pgt`` 切到已建立direct map
的长期kernel root，并明确flush包括global translations在内的旧TLB状态。hypervisor hook随后可补
平台mapping；ordinary native q35默认no-op。

``early_memtest(0,max_pfn_mapped<<PAGE_SHIFT)`` 只在有效 ``memtest=`` policy要求时测试可访问
free ranges。GRUB原字符串没有该option，但builtin command line未知，所以保持条件；它发生在
buddy allocator接管前，不会把reserved kernel/initramfs当作测试scratch。

自举 ``#PF`` 被替换，但最终IDT仍未完成
---------------------------------------

回到 ``setup_arch`` 后， ``cpu_init_replace_early_idt`` 在FRED feature enabled时建立FRED exception
入口；否则只用 ``idt_setup_early_pf`` 把x86-64 ``#PF`` gate从039的
``early_idt_handler_array`` 换成真实 ``asm_exc_page_fault`` early gate。

这一步并未安装normal external IRQ gates或最终IST配置；IF仍为0。它只终止“page fault还能调用
``early_make_pgtable`` 自动补direct-map PMD”的自举语义。

随后 ``mmu_cr4_features=__read_cr4() & ~X86_CR4_PCIDE`` 保存AP以后可继承的CR4 features。PCIDE
被刻意排除，因为secondary CPU离开long mode/使用trampoline root时不能直接带该位。

解除1 MiB allocation limit完成自举闭环
--------------------------------------

源码执行：

.. code-block:: c

   memblock_set_current_limit(get_max_mapped());

``get_max_mapped`` 是 ``max_pfn_mapped<<PAGE_SHIFT``。从此memblock可在已经direct mapped的更广
physical范围分配，而不是仅在1 MiB以下返回立即要写的内存。

若编入early OHCI-1394 DMA support且early option已设置
``init_ohci1394_dma_early``，源码接着扫描并初始化相关controllers；固定GRUB字符串没有该option，
builtin line/config未知，所以保持条件。下一条无条件call才是 ``setup_log_buf(1)``，本章在它之前
停止。

本章结束状态
------------

* current executor：CPU0上的 ``setup_arch``， ``setup_log_buf(1)`` 尚未调用；
* CPU/mode：BSP/logical CPU0，64-bit long mode，IF=0；无schedule、无AP bring-up；
* early brk：已reserve并封存， ``_brk_start=0``；
* early pgt buffer：位于reserved brk range，已参与direct-map自举；
* high kernel mapping：PMDs已收紧到 ``[_text,roundup(_brk_end,2MiB))``；
* ``memblock.memory``：由page-aligned working-E820 RAM ranges建立；
* ``memblock.reserved``：继承kernel/R/N/firmware，增加low 1MiB、real-mode storage及条件平台range；
* KHO low-memory scratch：ordinary successful realmode路径已清除；
* BIOS EFI helpers：因无EFI memmap全部skip；
* CoCo/MPC/BIOS corruption/OHCI：按build、effective options与runtime条件执行或no-op；
* direct map：覆盖ISA range及目标memblock RAM；holes不被当作ordinary RAM映射；
* active CR3： ``swapper_pg_dir=init_top_pgt``；旧root translations已flush；
* ``pfn_mapped[]/max_pfn_mapped/max_low_pfn_mapped``：已记录actual direct-map coverage；
* ``max_low_pfn``：x86-64映射后按源码可能提升到 ``max_pfn``，仍不同于mapped变量；
* early direct-map ``#PF``：已被FRED exception入口或真实early PF gate替换；
* memblock current limit： ``get_max_mapped()``；
* real-mode trampoline：storage已条件分配，内容尚未由realmode_init填入；
* initramfs：R/N继续reserved，尚未建立 ``initrd_start/end``，未unpack；
* printk dynamic buffer： ``setup_log_buf(1)`` 尚未执行。

关键边界
--------

#. pgt buffer先从开放brk取得； ``reserve_brk`` 后不能把 ``extend_brk`` 当成mapping阶段正常后备。
#. ``cleanup_highmap`` 清page-table entries，明确的旧global translation flush发生在后续CR3切换。
#. E820 RAM、memblock memory、memblock reserved与direct mapped仍是四个不同身份。
#. ``memblock_mark_kho_scratch`` 是兼容KHO scratch-only入口，不表示普通cold boot开始KHO。
#. fixed BIOS路径仍按顺序调用四个EFI helper，但各自因EFI memmap disabled返回。
#. MPC new buffer需要两个early flags，不是无条件4 KiB allocation。
#. realmode allocation失败不制造address；size非0路径仍reserve low 1 MiB并清scratch flag。
#. low 1 MiB同时reserved与direct mapped：可访问不等于可分配。
#. direct map遍历memblock RAM，不把 ``[0,max_pfn)`` 的所有hole线性当作WB RAM。
#. ``max_pfn``、 ``max_low_pfn``、 ``max_pfn_mapped``、 ``max_low_pfn_mapped`` 含义不能互换。
#. active CR3到 ``load_cr3(swapper_pg_dir)`` 才从early root切换。
#. ``cpu_init_replace_early_idt`` 只结束early-PF自举/FRED边界，不完成normal IRQ IDT。
#. memblock limit只扩大到actual mapped frontier，不盲目设为physical address maximum。
#. optional OHCI call属于043出口前；044从 ``setup_log_buf(1)`` 开始。

下一入口
--------

第044章从：

.. code-block:: c

   setup_log_buf(1);

开始。进入前 ``memblock.memory`` 与direct map已可用，active root是 ``init_top_pgt``，
``initrd_start/initrd_end`` 仍为0；当前BIOS路径还会跳过紧随其后的EFI secure-boot status switch。

资料
----

* `Linux 7.2-rc1固定提交：setup_arch memblock/direct-map调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L1063-L1157>`_；
* `Linux 7.2-rc1固定提交：E820 RAM转memblock与KHO low scratch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c#L1288-L1380>`_；
* `Linux 7.2-rc1固定提交：early pgt buffer与alloc_low_pages <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init.c#L109-L197>`_；
* `Linux 7.2-rc1固定提交：cleanup_highmap精确范围 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init_64.c#L431-L465>`_；
* `Linux 7.2-rc1固定提交：direct-map自举与CR3切换 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init.c#L501-L813>`_；
* `Linux 7.2-rc1固定提交：real-mode low-memory reserve <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/realmode/init.c#L47-L70>`_；
* `Linux 7.2-rc1固定提交：CoCo memory与RNG条件 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/coco/core.c#L214-L249>`_；
* `Linux 7.2-rc1固定提交：early PF替换或FRED入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/common.c#L2448-L2454>`_。
