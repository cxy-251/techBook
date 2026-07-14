第四十九章：Linux 怎样登记物理资源并完成 setup_arch？
====================================================

第四十八章结束时，Linux 已经完成 FADT、MADT、HPET、Local APIC、IOAPIC 和 possible CPU 拓扑的启动期解析。

当前下一条调用是：

.. code-block:: c

   e820__reserve_resources();

本章追踪 ``setup_arch()`` 的最后一段，直到它返回 ``start_kernel()``。这一段不再改变 CPU 模式，也不唤醒 AP。它把前面已经知道的地址范围登记到 Linux resource tree，选择后续 PCI MMIO 分配的候选窗口，保存若干硬件初始状态，并为机器检查、时间兜底和堆栈回溯建立最早基础。

本章结束后的真实下一条调用是：

.. code-block:: c

   mm_core_init_early();

资源登记和 memblock 保留不是一回事
--------------------------------

前面的章节已经多次调用：

.. code-block:: text

   memblock_add()
   memblock_reserve()
   memblock_phys_alloc()

memblock 解决的是启动期物理页能否分配：

.. code-block:: text

   memory   哪些物理范围属于可用 RAM
   reserved 哪些 RAM 暂时或永久不能再分配

现在建立的 ``resource tree`` 解决另一类问题：

.. code-block:: text

   这段物理地址在系统地址空间中代表什么？
   谁已经声明拥有它？
   新驱动的 MMIO/BAR 是否会与它冲突？
   /proc/iomem 和 /proc/ioports 应怎样展示？

因此，同一段内存可能同时存在于两套结构：

.. code-block:: text

   memblock.reserved
   → 防止启动期分配器覆盖

   iomem_resource child
   → 防止设备和驱动错误认领同一物理地址

两者不是重复数据结构，也不能互相替代。

``e820__reserve_resources()`` 为每个 E820 entry 建立 resource
----------------------------------------------------------

函数先按 E820 entry 数量通过 memblock 分配：

.. code-block:: c

   sizeof(struct resource) * e820_table->nr_entries

然后逐项转换：

.. code-block:: text

   E820_TYPE_RAM           → System RAM
   E820_TYPE_ACPI          → ACPI Tables
   E820_TYPE_NVS           → ACPI Non-volatile Storage
   E820_TYPE_UNUSABLE      → Unusable memory
   E820_TYPE_RESERVED      → Reserved
   E820_TYPE_SOFT_RESERVED → Soft Reserved
   E820_TYPE_PMEM          → Persistent Memory

每个 ``struct resource`` 至少获得：

* ``start``：首物理地址；
* ``end``：包含式末物理地址；
* ``name``：面向日志和 ``/proc/iomem`` 的名称；
* ``flags``：RAM 或普通 memory resource；
* ``desc``：ACPI、NVS、reserved、persistent memory 等更具体描述。

为什么 ``System RAM`` 有特殊 flag
--------------------------------

E820 RAM entry 使用：

.. code-block:: c

   IORESOURCE_SYSTEM_RAM

普通 reserved/ACPI/NVS 区通常使用：

.. code-block:: c

   IORESOURCE_MEM

这使后续代码能够区分：

.. code-block:: text

   物理地址空间中的普通 MMIO/保留区
   与
   真正由内核页管理器管理的 System RAM

例如，内核代码段、数据段、initramfs 和 crashkernel 都位于 System RAM 内部，但又可以作为更小的子 resource 插入其中。

为什么部分 E820 reserved 区暂时不标记 busy
----------------------------------------

``e820_device_region()`` 对 1 MiB 以上的一些类型执行特殊处理：

.. code-block:: text

   E820_TYPE_RESERVED
   E820_TYPE_SOFT_RESERVED
   E820_TYPE_PRAM
   E820_TYPE_PMEM

这些地址有时代表设备窗口或未来由专用驱动认领的区域。若启动时立刻作为 busy child 强行插入 ``iomem_resource``，后续 PCI BAR resource survey 可能与它发生虚假冲突。

所以 Linux 对这些“可能像设备地址”的范围延后发布。后面的：

.. code-block:: text

   pcibios_resource_survey()
   → e820__reserve_resources_late()

会在已经掌握 PCI BAR 布局后再插入它们。

这不是忘记保留，也不是让普通页分配器使用。E820 类型和 memblock 状态仍然有效；这里只是延后 resource tree 的所有权表达。

低于 1 MiB 的 reserved 区为什么不延后
-----------------------------------

``e820_device_region()`` 对 ``start < 1 MiB`` 直接返回 false。

低端区域包含传统 PC 的：

* IVT/BDA；
* EBDA；
* VGA aperture；
* Option ROM/BIOS shadow；
* real-mode trampoline 周边；
* 传统固件数据。

这些范围不是现代 PCI BAR survey 应重新安排的普通设备窗口，因此应尽早作为系统地址区登记并锁定。

resource 插入采用包含关系，而不是平面列表
--------------------------------------

Linux 的 ``iomem_resource`` 是一棵区间树。

概念结构类似：

.. code-block:: text

   iomem_resource
   ├── System RAM [range A]
   │   ├── Kernel code
   │   ├── Kernel rodata
   │   ├── Kernel data
   │   └── Kernel bss
   ├── Reserved [range B]
   ├── ACPI Tables [range C]
   └── PCI/MMIO ranges ...

第四十二章中 ``setup_kernel_resources()`` 已经构造并尝试插入 kernel code/rodata/data/bss resource。现在父级 E820 System RAM ranges 加入后，resource manager 可以整理出完整的地址所有权层次。

这里没有分配或映射这些地址。resource tree 只登记范围与归属。

为什么还保存一份 firmware map
----------------------------

``e820__reserve_resources()`` 还遍历 ``e820_table_kexec``，调用：

.. code-block:: c

   firmware_map_add_early(...)

这为 firmware memory map 的 sysfs 表示和 kexec 相关逻辑保留原始/整理后的物理布局信息。

resource tree 偏向当前内核运行时的地址所有权；firmware map 则保留“固件怎样描述这台机器”的视角。

``e820__register_nosave_regions()`` 不会再次保留内存
--------------------------------------------------

下一条调用：

.. code-block:: c

   e820__register_nosave_regions(max_pfn);

它扫描相邻的 E820 RAM entry，把 RAM 之间的空洞登记为：

.. code-block:: text

   nosave region

这些空洞可能是：

* MMIO；
* ACPI/firmware 区；
* 未使用地址；
* 不存在的物理地址；
* reserved hole。

hibernate/suspend image 不应把这些非 RAM PFN 当作普通内存保存和恢复。

该函数的核心逻辑是：

.. code-block:: text

   previous RAM end
   → next RAM start
   → register_nosave_region(PFN range)

最后还登记最后一段 RAM 之后到 ``max_pfn`` 的空洞。

它不修改 E820，不调用 memblock reserve，也不创建页表。它只给休眠镜像代码标记“不应保存的 PFN”。

为什么 NVS 不能简单视作 nosave 后丢弃
-----------------------------------

ACPI NVS 用于固件在 suspend/resume 之间保持状态。它不是普通 System RAM，却可能必须原样保存。

因此后续还有独立的 ``e820__register_nvs_regions()`` core initcall，把 NVS ranges 交给 ACPI suspend/hibernate 逻辑。当前 ``nosave`` 标记和后续 NVS 特殊保存规则共同决定电源状态转换时如何处理这些页。

标准 PC I/O 端口也需要 resource tree
-----------------------------------

接下来：

.. code-block:: c

   x86_init.resources.reserve_resources();

普通 PC 默认函数是：

.. code-block:: c

   reserve_standard_io_resources();

它向全局 ``ioport_resource`` 登记传统端口：

.. code-block:: text

   0x00–0x1f   DMA1
   0x20–0x21   PIC1
   0x40–0x43   PIT timer0
   0x50–0x53   timer1 legacy range
   0x60         keyboard data
   0x64         keyboard status/command
   0x80–0x8f   DMA page registers
   0xa0–0xa1   PIC2
   0xc0–0xdf   DMA2
   0xf0–0xff   legacy FPU range

这些端口中的部分硬件可能稍后根本不会成为主要中断/定时器来源。q35 可以使用 IOAPIC、HPET、Local APIC timer，现代设备也大量使用 MMIO/MSI。

Linux 仍要声明传统端口已被平台占用，避免普通驱动错误申请同一端口。

登记端口不等于初始化设备
----------------------

此处没有：

* 重新编程 8259 PIC；
* 启动 PIT tick；
* 读取 PS/2 键盘；
* 配置 ISA DMA；
* 绑定字符设备驱动。

``request_resource()`` 只向区间树声明所有权。设备的真正初始化仍由对应 IRQ、timer、input 和 driver 路径完成。

为什么平台可以替换 ``reserve_resources``
---------------------------------------

调用经过 ``x86_init.resources`` 函数表。普通 PC 使用标准端口表，Xen、特殊虚拟机或非传统 x86 平台可以提前替换钩子。

这与前面的：

.. code-block:: text

   memory_setup
   pagetable_init
   guest_late_init

属于同一设计：``setup_arch()`` 保持共同时间线，平台差异通过函数表注入。

``e820__setup_pci_gap()`` 寻找什么
--------------------------------

随后：

.. code-block:: c

   e820__setup_pci_gap();

PCI 设备可能带有尚未分配的 32 位 MMIO BAR，PCI hotplug 也可能需要未来地址空间。Linux 要在低 4 GiB 物理地址空间中寻找一个较大的非 RAM gap，作为后续 PCI resource assignment 的起点。

函数要求候选 gap 至少：

.. code-block:: text

   4 MiB

并在 E820 ranges 之间搜索最大的可用空洞。找到后写入：

.. code-block:: c

   pci_mem_start = max_gap_start;

为什么优先考虑低 4 GiB
---------------------

32 位 PCI BAR 只能表达低于 ``0x1_0000_0000`` 的地址。即使 CPU 和内核是 64 位，设备本身也可能只有 32 位 BAR。

因此必须为这类设备保留低地址 MMIO aperture。64 位 BAR 可以放到更高地址，但不能解决所有设备需求。

找不到 gap 时怎样处理
--------------------

x86-64 上若低 4 GiB 中没有满足要求的 gap，Linux 把 fallback 起点设在：

.. code-block:: c

   (max_pfn << PAGE_SHIFT) + 1 MiB

并打印警告：未分配的 32 位 BAR 可能无法工作。

这不是立即导致 panic。已有固件分配且不冲突的 BAR 仍可能正常使用；风险主要落在未配置设备和后续 hotplug。

``pci_mem_start`` 不是本章分配出的 PCI BAR
----------------------------------------

本章只计算一个建议起点。它没有：

* 扫描 Linux PCI device model；
* 读取所有 BAR size mask；
* 创建 ``struct pci_dev``；
* 执行 driver probe；
* 重写 BAR register。

后面的 PCI subsystem 才会结合 host bridge windows、ACPI resources、现有固件分配和 resource tree 进行 survey/assignment。

VGA console 为什么在这里条件登记
------------------------------

若构建启用 ``CONFIG_VT`` 和 ``CONFIG_VGA_CONSOLE``，并且平台允许传统 VGA memory aperture，``setup_arch()`` 调用：

.. code-block:: c

   vgacon_register_screen(&sysfb_primary_display.screen);

``sysfb_primary_display.screen`` 来自早先复制的 ``boot_params.screen_info``，也就是 GRUB/BIOS 留下的显示模式信息。

这一步把传统 VGA text console 的 screen descriptor 交给系统 framebuffer/console 基础设施。

它不代表现代 DRM 驱动已经加载，也不代表内核重新初始化了显卡。固定命令行使用 ``console=ttyS0``，串口仍是明确指定的控制台；VGA console 是否同时可用取决于构建和设备配置。

OEM banner 实际输出什么
----------------------

下一条：

.. code-block:: c

   x86_init.oem.banner();

普通实现 ``default_banner()`` 输出：

.. code-block:: text

   Booting paravirtualized kernel on <pv_info.name>

``pv_info.name`` 可以是 ``bare hardware``，也可以由已识别的虚拟化环境替换。

QEMU 可以运行在 TCG、KVM 或其他 accelerator 下；固定主线没有限定 hypervisor detection 结果，所以正文不把 banner 文本写死为某个具体名字。

``wallclock_init()`` 在这里没有读取 RTC
------------------------------------

源码随后调用：

.. code-block:: c

   x86_init.timers.wallclock_init();

普通 x86 实现是 ``x86_wallclock_init()``。它只检查 Device Tree 中兼容：

.. code-block:: text

   motorola,mc146818

的 RTC node 是否被标记 disabled。

若明确 disabled，Linux 把：

.. code-block:: c

   x86_platform.get_wallclock
   x86_platform.set_wallclock

替换为 no-op。

当前 SeaBIOS/ACPI 主线没有传入 Device Tree RTC node，因此它通常什么也不改，保留默认的 CMOS RTC 读写函数。

这一步没有读取年月日，也没有设置内核实时时钟。真正从 persistent clock/RTC 初始化 timekeeping 会在后面的时间子系统路径发生。

为什么这一点容易被函数名误导
--------------------------

看到 ``wallclock_init`` 很容易写成：

.. code-block:: text

   Linux 从 CMOS 读取当前时间

固定源码并非如此。当前函数只决定“未来是否允许使用该 wallclock 后端”。

源码阅读必须跟进函数指针的实际默认实现，而不是根据调用名补全一个看似合理的故事。

``therm_lvt_init()`` 保存 BIOS 留下的 thermal LVT
----------------------------------------------

随后：

.. code-block:: c

   therm_lvt_init();

该函数只在 boot CPU 上执行。若 Intel CPU 支持 ACPI thermal control 和 thermal monitor，它读取：

.. code-block:: c

   APIC_LVTTHMR

并保存到：

.. code-block:: c

   lvtthmr_init

Local APIC 的 thermal LVT entry 决定 thermal event 以 fixed interrupt、SMI 或其他 delivery mode 送达。

为什么必须在更后面的 Local APIC setup 前保存
------------------------------------------

``setup_local_APIC()`` 会暂时 soft-disable Local APIC，并可能 mask thermal LVT。若 BIOS 原本把 thermal interrupt 配成 SMI，过早覆盖会破坏固件负责的 thermal handling，甚至造成 soft lockup。

因此 Linux 现在先保存 BSP 上的 BIOS 初值。后面 AP 通过 INIT/SIPI 启动时，APIC LVT registers 会被重置；AP 初始化可以根据 BSP 保存值恢复 BIOS 期望的 thermal delivery mode。

这里仍没有完整启用 thermal monitoring。真正的 MSR 配置、vector mask 和 thermal interrupt setup 位于后续 CPU thermal 初始化。

``mcheck_init()`` 不是 MCA bank 探测
---------------------------------

下一条：

.. code-block:: c

   mcheck_init();

Machine Check Architecture（MCA）允许 CPU 报告 cache、memory controller、interconnect 和内部硬件错误。

但 BSP 的 MCE capability 和 bank 初始化并不是现在才开始。更早的 CPU 初始化路径已执行类似：

.. code-block:: text

   mca_bsp_init()
   mcheck_cpu_init()

读取 ``MSR_IA32_MCG_CAP``、初始化 bank、建立 record pool，并在可用时设置 ``CR4.MCE``。

当前 ``mcheck_init()`` 做的是软件处理框架收尾：

#. 注册 early、uncorrected 和 default MCE decode notifier chain；
#. 初始化处理 MCE record pool 的 work item；
#. 初始化 MCE irq_work。

所以本章没有再次探测全部 bank，也没有在这里打开 ``CR4.MCE``。

为什么 workqueue 尚未运行也能初始化 work
--------------------------------------

``INIT_WORK()`` 和 ``init_irq_work()`` 只是初始化对象中的函数指针、链表和状态。

scheduler、workqueue worker 和普通中断尚未全面启动，但数据结构可以先准备好。等 MCE 事件和执行环境可用时，同一对象再被排队处理。

``register_refined_jiffies()`` 建立一个时间兜底
---------------------------------------------

随后：

.. code-block:: c

   register_refined_jiffies(CLOCK_TICK_RATE);

基础 ``clocksource_jiffies`` 以 jiffies 为读数来源，精度和 rating 较低。函数复制它，命名为：

.. code-block:: text

   refined-jiffies

然后根据传入的 ``CLOCK_TICK_RATE`` 计算：

* 每个 tick 对应多少 source cycles；
* 每 tick 的纳秒数；
* clocksource multiplier；
* 比普通 jiffies 略高的 rating。

最后通过 ``__clocksource_register()`` 登记这个候选 clocksource。

登记 refined-jiffies 不等于 timer interrupt 已启动
-----------------------------------------------

此时：

* 全局 interrupt flag 仍关闭；
* PIT/HPET/Local APIC timer 尚未完成最终 clockevent setup；
* timekeeping 尚未选择最终 clocksource；
* jiffies 还没有通过正常 periodic tick 持续推进。

``refined-jiffies`` 只是提供一个按已知硬件 tick 频率更准确换算的后备 clocksource 描述。

为什么系统仍需要这种低精度后备
----------------------------

TSC、HPET、ACPI PM timer 等更优时钟源可能因为：

* CPU/虚拟机不支持；
* 校准失败；
* 被命令行禁用；
* 平台 quirk 判定不可靠；
* suspend/resume 后失效；

而不能使用。

一个简单但可靠的 jiffies-based fallback 可以让时间子系统至少维持基本功能。

EFI memory-map quirk 在固定主线中跳过
-----------------------------------

源码随后检查：

.. code-block:: c

   if (efi_enabled(EFI_BOOT))
       efi_apply_memmap_quirks();

固定主线由 SeaBIOS 和 GRUB i386-pc 启动，不是 EFI boot，因此 ``EFI_BOOT`` 未设置，这个分支跳过。

EFI 启动路径会在这里根据平台和 firmware 问题修正 EFI memory map 属性。本书不把该分支混入固定 BIOS 控制流。

``unwind_init()`` 为最早的可靠调用栈做准备
---------------------------------------

``setup_arch()`` 的最后一条调用是：

.. code-block:: c

   unwind_init();

如果内核启用 ``CONFIG_UNWINDER_ORC``，构建工具已经为函数生成：

.. code-block:: text

   .orc_unwind_ip
   .orc_unwind

前者把 instruction pointer 区间关联到 ORC record，后者描述在该位置如何恢复上一个 stack pointer、base pointer、instruction pointer 或 register frame。

``unwind_init()`` 首先校验：

* 两张表是否存在；
* entry 数量是否一致；
* section size 是否满足结构对齐；
* build-time 排序结果是否可用。

然后建立快速 lookup table，使后续 warning、oops、NMI、MCE 和 stack trace 不必每次在完整 ORC 表上做全范围搜索。

ORC 未启用时会发生什么
---------------------

``arch/x86/include/asm/unwind.h`` 定义：

.. code-block:: c

   #ifdef CONFIG_UNWINDER_ORC
   void unwind_init(void);
   #else
   static inline void unwind_init(void) {}
   #endif

使用 frame-pointer 或其他 unwinder 配置时，该调用在这里可能直接编译为空操作。

所以本章可以确定“执行了架构 unwind 初始化入口”，不能在没有固定 ``.config`` 的情况下断言一定建立 ORC lookup table。

为什么把 unwind 放到 ``setup_arch()`` 最后一项
-------------------------------------------

此时页表、内核虚拟地址、CPU entry 基础、resource ranges 和 early exception 环境已经稳定。ORC 表位于内核映像中，可以安全校验和建立 lookup。

后续内存管理、security、per-CPU、trap、scheduler 和中断初始化越来越复杂，发生 warning/oops 时需要可靠 stack trace。现在完成 unwinder，能覆盖这些更高层初始化阶段。

``setup_arch()`` 返回时，架构初始化完成到了什么程度
------------------------------------------------

函数返回不表示“x86 已经初始化完成”。它表示 ``start_kernel()`` 所需的最早架构事实已经具备：

.. code-block:: text

   firmware/bootloader 参数已接管
   physical memory map 已整理
   memblock 与 early direct map 已建立
   initramfs 地址已确认
   ACPI/APIC/IOAPIC/NUMA/possible CPU 拓扑已建立
   resource tree 基础已登记
   PCI 32-bit MMIO gap 候选已选择
   thermal LVT 初值已保存
   MCE software handlers 已准备
   fallback clocksource 已登记
   unwinder 已按配置初始化

仍未完成的关键事项包括：

* buddy page allocator；
* slab allocator；
* 完整 VFS cache；
* per-CPU area；
* scheduler；
* IDT/trap 最终初始化；
* IRQ domain 和设备中断启用；
* AP 启动；
* initcall；
* PCI/Linux driver model 枚举；
* initramfs 解包；
* 挂载 root filesystem；
* 执行 ``/init``。

控制权回到 ``start_kernel()``
----------------------------

``setup_arch(&command_line)`` 返回后，CPU 没有跳转到新程序，也没有切换线程。调用栈正常返回：

.. code-block:: text

   setup_arch()
   → ret
   → start_kernel()

当前仍由 BSP / Linux CPU 0 在 ``init_task`` 的启动栈上执行，中断保持关闭。

``start_kernel()`` 的真实下一条语句是：

.. code-block:: c

   mm_core_init_early();

它会开始通用内存管理的早期核心初始化。之后才依次进入 static key/static call、early security、boot config、正式命令行保存、CPU 数量、per-CPU area 等步骤。

不能从 ``setup_arch()`` 直接跳到：

.. code-block:: text

   sched_init()
   smp_init()
   populate_rootfs()
   kernel_init()

源码中间还有一长段必须按顺序建立的通用内核基础。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``setup_arch(&command_line)`` 已返回，``mm_core_init_early()`` 尚未调用；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* current task：``init_task``；
* interrupts：关闭，``early_boot_irqs_disabled = true``；
* E820 ranges：已转换成 resource 描述并登记系统范围；
* hibernation nosave holes：已登记；
* 标准 PC I/O ports：已在 ``ioport_resource`` 声明占用；
* PCI MMIO gap：已选出并写入 ``pci_mem_start``；
* VGA console：已完成条件 screen registration；
* wallclock backend：已完成条件选择，尚未在这里读取 RTC；
* thermal LVT：BSP firmware 初值已条件保存；
* MCE：decode/work software framework 已初始化；
* refined-jiffies：已作为候选 fallback clocksource 登记；
* EFI memmap quirk：SeaBIOS 固定主线跳过；
* unwinder：已按配置初始化；
* ``setup_arch()``：已完成并返回；
* buddy allocator：尚未建立；
* per-CPU area：尚未建立；
* scheduler：尚未初始化；
* AP：尚未唤醒；
* initramfs：仍是内存中的归档，尚未解包。

下一条控制流是：

.. code-block:: c

   mm_core_init_early();

资料
----

* `Linux 6.12.95 setup.c：setup_arch 最后一段与返回顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 e820.c：E820 resource、nosave regions 与 PCI gap <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c>`_
* `Linux 6.12.95 setup.c：standard_io_resources 与 reserve_standard_io_resources <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 x86_init.c：native resource、wallclock 和 OEM hooks <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/x86_init.c>`_
* `Linux 6.12.95 therm_throt.c：therm_lvt_init 保存 BSP thermal LVT <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/thermal/intel/therm_throt.c>`_
* `Linux 6.12.95 MCE core.c：mcheck_init 的 notifier、work 与 irq_work <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/mce/core.c>`_
* `Linux 6.12.95 jiffies.c：refined-jiffies multiplier 与 clocksource registration <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/time/jiffies.c>`_
* `Linux 6.12.95 unwind_orc.c：ORC table 校验和 fast lookup 初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/unwind_orc.c>`_
* `Linux 6.12.95 unwind.h：ORC 条件入口和非 ORC 空实现 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/unwind.h>`_
* `Linux 6.12.95 init/main.c：setup_arch 返回后的 mm_core_init_early 入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_