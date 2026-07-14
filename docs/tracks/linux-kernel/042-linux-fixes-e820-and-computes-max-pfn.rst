第四十二章：Linux 怎样修正 E820 并计算自己真正能管理的物理页？
================================================================

第四十一章结束时，``setup_arch()`` 已经完成两件基础工作：

* 把 GRUB 提供的命令行和 ``boot_params`` 转换成正式内核状态；
* 导入并整理基础 E820 与 ``setup_data`` 扩展。

当前下一条调用是：

.. code-block:: c

   setup_initial_init_mm(_text, _etext, _edata, (void *)_brk_end);

这一章继续追踪到 ``early_alloc_pgt_buf()`` 之前。期间 Linux 会把内核映像登记进资源树，处理 NX、early 参数、DMI、hypervisor 和固件 ROM，再根据 E820 与 MTRR 计算 ``max_pfn``。

需要先区分三套很容易混淆的结构：

.. code-block:: text

   E820 table       描述固件报告的物理地址类型
   iomem_resource   描述系统资源的父子占用关系
   memblock         启动早期真正用于内存分配和保留

本章主要处理前两者并计算边界。第三套 memblock 的 RAM 导入留到下一章。

``init_mm`` 不是第一个用户进程
----------------------------

``setup_initial_init_mm()`` 位于 ``mm/init-mm.c``。它把：

.. code-block:: c

   init_mm.start_code = _text;
   init_mm.end_code   = _etext;
   init_mm.end_data   = _edata;
   init_mm.brk        = _brk_end;

``init_mm`` 是内核地址空间的 ``mm_struct``，其页表根是 ``swapper_pg_dir``。

它不是 PID 1 的用户地址空间，也不表示内核此时已经能创建普通进程。它为：

* 内核线程共享的地址空间；
* 页表统计；
* ``/proc`` 与调试信息；
* 后续内存管理代码对 kernel text/data/brk 边界的查询；

提供统一对象。

``_text``、``_etext``、``_edata`` 与 ``_brk_end`` 都是虚拟地址。真正的物理保留在上一章已经用 ``__pa_symbol()`` 写入 memblock reserved。这里登记的是地址空间语义，不是再次保留物理页。

为什么 NX 必须在 early 参数前确定
--------------------------------

接下来：

.. code-block:: c

   x86_configure_nx();
   parse_early_param();

``x86_configure_nx()`` 根据 boot CPU 是否具有 ``X86_FEATURE_NX``，修改：

.. code-block:: c

   __supported_pte_mask

如果 CPU 支持 NX，则允许页表项使用 ``_PAGE_NX``；不支持则清除此位。

这一步必须发生在 ``parse_early_param()`` 之前，因为某些 early 参数会初始化 EHCI debug console、fixmap 或临时映射。页表构造代码必须在第一次创建这些映射前就知道硬件能否接受 NX bit，否则写入不支持的位可能触发保留位页故障。

``parse_early_param()`` 为什么会调用两次
--------------------------------------

``start_kernel()`` 在 ``setup_arch()`` 返回后还会再次调用 ``parse_early_param()``。这里提前执行不是重复错误。

原因是 x86 的后续架构初始化已经依赖 early 参数，例如：

* ``mem=``；
* ``memmap=``；
* ``noexec`` / NX 相关选项；
* APIC、ACPI、PCI 与 IOMMU 开关；
* KASLR 或内存布局相关选项；
* early console。

解析框架会记录已经处理的 early 参数，后续通用调用主要保证其他架构与通用入口拥有一致流程。

当前固定命令行只有：

.. code-block:: text

   root=/dev/sda1 ro console=ttyS0

其中 ``root`` 和 ``ro`` 不是这一阶段的 x86 early memory 参数；``console=ttyS0`` 也要等控制台初始化继续处理。因此当前主线不会因 ``mem=`` 或 ``memmap=`` 人为裁剪 E820。

SeaBIOS 主线跳过 EFI 保留路径
----------------------------

随后存在：

.. code-block:: c

   if (efi_enabled(EFI_BOOT))
       efi_memblock_x86_reserve_range();

当前入口来自 SeaBIOS + GRUB i386-pc，``EFI_BOOT`` 没有设置，因此不会导入 EFI memory map，也不会保留 EFI boot services 区域。

这说明同一个 x86-64 内核映像可以走两条固件主线：

.. code-block:: text

   BIOS/GRUB path  → E820 是主要物理内存来源
   EFI path        → EFI memory map 参与初始化并补充保留规则

本书固定路径继续使用 E820。

报告 NX 与准备 APIC 调用
-----------------------

``x86_report_nx()`` 根据最终 capability 输出 NX 是否 active。

随后：

.. code-block:: c

   apic_setup_apic_calls();

它根据当前 APIC driver 和 CPU 能力准备后续 local APIC 操作入口。

这里仍没有启用普通硬件中断。中断标志保持关闭，local APIC 的完整映射、时钟与 IRQ 初始化都在更后面。

``acpi_mps_check()`` 处理 ACPI 与 MP table 的冲突或禁用条件。若平台决定不使用 local APIC，内核会：

.. code-block:: c

   apic_is_disabled = true;
   setup_clear_cpu_cap(X86_FEATURE_APIC);

当前 q35 + SeaBIOS 提供 ACPI/MADT，主线不会因为缺少表而清除 APIC capability。

应用 E820 early 参数的最终结果
-----------------------------

``e820__finish_early_params()`` 在 early 参数解析后收尾 E820 修改。

用户若传入：

.. code-block:: text

   mem=
   memmap=

可能截断 RAM、增加保留区、创建精确映射或修改可用范围。Linux 必须在这些修改完成后，才把 E820 当作后续资源和页框数量计算的依据。

因此“固件原始 E820”与“Linux 最终工作 E820”并不相同：

.. code-block:: text

   firmware map
   → sanitize
   → setup_data extensions
   → command-line corrections
   → platform quirks
   → MTRR trim
   → final working map

启动 iBFT、DMI 与 hypervisor 识别
------------------------------

接下来的顺序是：

.. code-block:: c

   reserve_ibft_region();
   x86_init.resources.dmi_setup();
   init_hypervisor_platform();
   tsc_early_init();
   x86_init.resources.probe_roms();

``reserve_ibft_region()`` 处理 iSCSI Boot Firmware Table 条件路径。固定本地 AHCI 启动盘通常没有 iBFT，因此不会新增该保留区。

DMI/SMBIOS 信息来自 SeaBIOS/QEMU 前面建立的表。内核在这里识别系统厂商、产品、BIOS 版本与机型特征，后续大量硬件 quirk 依赖 DMI 匹配。

``init_hypervisor_platform()`` 检查 CPUID 与平台线索，识别 KVM、Xen、Hyper-V、VMware 等环境。固定 QEMU 若启用 KVM accelerator，Linux 会进入 KVM guest 特性；纯 TCG 则没有 KVM CPUID signature。两种路径仍共享本章的 E820 主线。

``tsc_early_init()`` 开始建立 TSC 的早期频率与可靠性判断。完整 clocksource 和 timekeeping 尚未初始化。

``probe_roms()`` 查找传统 BIOS ROM、video ROM 和 extension ROM 范围，供资源保留与后续兼容代码使用。它不会执行 Option ROM；SeaBIOS 阶段早已完成必要 ROM 执行。

把 kernel section 放进 ``iomem_resource``
----------------------------------------

``setup_kernel_resources()`` 为正式内核的主要 section 建立资源节点：

.. code-block:: text

   Kernel code      _text          → _etext - 1
   Kernel rodata    __start_rodata → __end_rodata - 1
   Kernel data      _sdata         → _edata - 1
   Kernel bss       __bss_start    → __bss_stop - 1

这些节点插入 ``iomem_resource`` 树。

资源树与 memblock reserved 的目的不同：

* memblock reserved 防止启动分配器覆盖物理内存；
* iomem resource 公开“这段物理地址属于谁”，以后能在 ``/proc/iomem`` 中显示，也能阻止驱动把 kernel text 当作设备 MMIO 申请。

同一段 kernel 物理区间因此会同时出现在两套系统中，这不是重复浪费，而是分配保护与资源归属两个维度。

确认 E820 把 kernel 所在位置标成 RAM
-----------------------------------

``e820_add_kernel_range()`` 计算：

.. code-block:: c

   start = __pa_symbol(_text);
   size  = __pa_symbol(_end) - start;

然后检查整个 ``text + data + bss`` 是否被 E820 标为 ``E820_TYPE_RAM``。

如果不是，内核会报警：

.. code-block:: text

   .text .data .bss are not marked as E820_TYPE_RAM!

并尝试删除冲突范围、重新加入 RAM。

这里的态度很明确：正在执行的 kernel image 必须位于可用物理内存。若固件或 ``memmap=exactmap`` 把它放在非 RAM 区，后面即使强行修正也可能崩溃；这一步先让内部表与现实保持最低限度一致。

为什么再次修剪低端 BIOS 范围
---------------------------

``trim_bios_range()`` 做两项修正。

第一项把 page 0 从 RAM 改为 reserved：

.. code-block:: c

   e820__range_update(0, PAGE_SIZE,
                      E820_TYPE_RAM,
                      E820_TYPE_RESERVED);

第二项删除 ``640 KiB–1 MiB`` 之间错误标成 RAM 的范围：

.. code-block:: c

   e820__range_remove(BIOS_BEGIN,
                      BIOS_END - BIOS_BEGIN,
                      E820_TYPE_RAM);

传统 PC 低端布局大致是：

.. code-block:: text

   0x00000–0x9ffff   conventional memory / BDA / EBDA 等
   0xa0000–0xbffff   VGA aperture
   0xc0000–0xeffff   Option ROM / firmware extension window
   0xf0000–0xfffff   system BIOS window

SeaBIOS 已经给出合理 E820，但 Linux 仍防御性修正，以兼容报告错误的真实 BIOS。

E820 修正完成后再次执行 ``e820__update_table()``，确保区间重新有序且无冲突。

x86-64 的 early GART 检查
------------------------

32 位路径可能处理 PPro RAM bug；当前 x86-64 进入：

.. code-block:: c

   early_gart_iommu_check();

某些 AMD/兼容平台会在内存顶端为 GART/IOMMU aperture 留出区域。如果固件没有正确标记，Linux 需要识别并从可用 RAM 中排除。

固定 q35 主线通常不命中 AMD GART 条件，但调用顺序仍重要：``max_pfn`` 必须在这类平台保留修正之后计算。

从 E820 计算 ``max_pfn``
-----------------------

接下来：

.. code-block:: c

   max_pfn = e820__end_of_ram_pfn();

PFN 是 Page Frame Number：

.. code-block:: text

   PFN = physical_address >> PAGE_SHIFT

x86 标准页大小为 4 KiB，``PAGE_SHIFT = 12``。所以：

.. code-block:: text

   physical 0x00100000 → PFN 0x100

``max_pfn`` 不是 RAM 页数量。它是 E820 RAM 最高结束地址向上折算出的“最大页框边界”。中间可以存在 PCI hole、ACPI 保留区和其他空洞。

例如：

.. code-block:: text

   RAM 0–3 GiB
   PCI hole 3–4 GiB
   RAM 4–5 GiB

``max_pfn`` 会指向 5 GiB 末端，但 Linux 不能因此把 3–4 GiB 当作 RAM。真正可分配范围仍由 E820/memblock 区间列表决定。

MTRR 为什么还能缩小 RAM
----------------------

随后：

.. code-block:: c

   cache_bp_init();
   if (mtrr_trim_uncached_memory(max_pfn))
       max_pfn = e820__end_of_ram_pfn();

``cache_bp_init()`` 建立 boot CPU 的 PAT/MTRR 缓存属性状态。

如果 E820 报告某段是 RAM，但 MTRR 明确把它放在不可缓存或不一致区域，Linux 可能从 E820 RAM 中裁掉该段。普通内存若被错误以 UC 访问，性能会极差；更严重时，固件报告和 CPU 缓存属性矛盾可能隐藏硬件保留区。

SeaBIOS 前面设置的 MTRR 因此并没有在 Linux 接管后失去意义。Linux 会重新识别并最终管理 MTRR，但启动最早期仍以继承状态判断哪些 RAM 区域安全。

保存 ``max_possible_pfn``
-------------------------

MTRR trim 后：

.. code-block:: c

   max_possible_pfn = max_pfn;

后续内存热插拔、sparsemem 与 page structure sizing 需要知道当前架构可能涉及的最高 PFN 上界。

这个值仍不是 ``max_low_pfn``，也不是已 direct-mapped 的 ``max_pfn_mapped``。这些变量名字接近，含义不同：

.. code-block:: text

   max_pfn            当前 RAM 图最高 PFN 边界
   max_possible_pfn   page model 需要考虑的可能最高边界
   max_low_pfn        当前低端/直接可处理边界语义
   max_pfn_mapped     页表已经建立 direct map 的最高 PFN

此刻最后一个仍然只反映早期映射，不等于 ``max_pfn``。

随机化内核虚拟内存区域
---------------------

``kernel_randomize_memory()`` 在 ``max_pfn`` 已知后，为 direct map、vmalloc 和 vmemmap 等大型虚拟区域选择随机基址。

这与解压阶段的 KASLR 有联系，却不是同一件事：

.. code-block:: text

   physical KASLR       决定 kernel ELF 放在哪段物理 RAM
   kernel text KASLR    决定 kernel image 对应的高半区虚拟偏移
   memory KASLR         决定 direct map / vmalloc / vmemmap 等区域基址

内存区域随机化必须知道最高物理内存规模，才能保证各虚拟区间不会互相重叠。

确定 ``max_low_pfn``
--------------------

在 x86-64 上：

.. code-block:: c

   if (max_pfn > (1UL << (32 - PAGE_SHIFT)))
       max_low_pfn = e820__end_of_low_ram_pfn();
   else
       max_low_pfn = max_pfn;

4 GiB 以下和以上的 RAM 在早期映射、设备 DMA 与兼容接口中意义不同。

如果最高 RAM 没超过 4 GiB，``max_low_pfn`` 可以直接等于 ``max_pfn``。若超过，则单独计算低 4 GiB 内 RAM 的末端。

这里的 ``low`` 不是 32 位 HIGHMEM 的完整概念，而是 x86 启动代码仍需区分 32 位可寻址低端区域和更高物理地址。

在页表分配前寻找 MP table
-------------------------

最后：

.. code-block:: c

   x86_init.mpparse.find_mptable();

Linux 在传统低端内存/BIOS 区域寻找 Intel MP Floating Pointer Structure。

q35 主线主要依赖 ACPI MADT 描述 CPU 和 APIC，但 MP table 是兼容回退路径。查找必须发生在低端 BIOS 区域被后续大规模内存初始化和重用之前。

本章停在 ``early_alloc_pgt_buf()``
---------------------------------

下一条调用是：

.. code-block:: c

   early_alloc_pgt_buf();

到这里，Linux 已经知道：

* 哪些物理区间被 E820 视为 RAM；
* 哪些低端区间必须从 RAM 中剔除；
* kernel sections 在资源树中的归属；
* CPU 是否支持 NX；
* MTRR 是否要求裁掉某些 RAM；
* 最高 PFN 边界；
* direct map 等虚拟区域的随机基址。

但它还没有：

* 为新 direct map 预留页表页；
* 把 E820 RAM 加入 ``memblock.memory``；
* 关闭早期 brk allocator；
* 建立覆盖所有可用 RAM 的 direct map；
* 切到最终早期 ``swapper_pg_dir``。

这些动作构成下一章。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* 当前停点：即将调用 ``early_alloc_pgt_buf()``；
* CPU：BSP / Linux CPU 0；
* interrupts：关闭；
* ``init_mm``：已登记 kernel code/data/brk 边界；
* NX capability：已写入 ``__supported_pte_mask``；
* early 参数：已解析；
* DMI/hypervisor/TSC/ROM：已执行早期识别；
* kernel code/rodata/data/bss：已加入 ``iomem_resource``；
* E820 kernel range：已校验；
* page 0 与 ``640 KiB–1 MiB`` BIOS 区：已从 RAM 语义中修正；
* MTRR trim：已执行；
* ``max_pfn`` / ``max_possible_pfn`` / ``max_low_pfn``：已确定；
* memory layout randomization：已决定；
* MP table：已执行早期查找；
* ``memblock.memory``：尚未建立；
* 完整 direct map：尚未建立；
* initramfs：仍只被物理保留。

资料
----

* `Linux 6.12.95 setup.c：setup_initial_init_mm 之后的 NX、资源与 max_pfn 主流程 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 init-mm.c：init_mm 与 setup_initial_init_mm <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/init-mm.c>`_
* `Linux 6.12.95 e820.c：E820 查询、修改与 end_of_ram_pfn <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c>`_
* `Linux 6.12.95 MTRR cleanup：mtrr_trim_uncached_memory <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/mtrr/cleanup.c>`_
* `Linux 6.12.95 kaslr.c：kernel_randomize_memory 的虚拟区域随机化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/kaslr.c>`_
* `Linux 6.12.95 resource.c：iomem_resource 资源树基础 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/resource.c>`_
