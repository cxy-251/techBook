第四十九章：Linux 怎样登记 E820/I/O resources 并返回 start_kernel？
=====================================================================

第四十八章结束时，CPU0仍在 ``setup_arch``、IF=0；possible/present CPU topology已冻结，Local APIC与
IOAPIC MMIO可访问，但IOAPIC resource objects尚未插入resource tree。当前入口是：

.. code-block:: c

   e820__reserve_resources();

本章按fixed Linux 7.2-rc1追踪 ``setup_arch`` 最后一段直到返回。它把working E820与standard PC
I/O ports发布到两棵resource trees，登记hibernate nosave holes并选择PCI 32-bit gap；随后只保存/
初始化若干arch facts，最后从 ``setup_arch`` 正常return到 ``start_kernel`` 的
``mm_core_init_early()`` call前。

resource ownership与memblock allocation identity不同
-----------------------------------------------

memblock memory/reserved决定early physical allocator能否返回一段RAM； ``iomem_resource``/
``ioport_resource`` 则描述system address-space ownership，防止driver/BAR与已有range冲突并支撑
``/proc/iomem``、 ``/proc/ioports``。同一kernel RAM可以既在 ``memblock.reserved``，又作为
``System RAM`` 的Kernel code child；resource insertion不分配页、不建立PTE。

working E820每条entry先获得一个resource slot
--------------------------------------------

``e820__reserve_resources`` 用memblock按 ``e820_table->nr_entries`` 分配连续 ``struct resource``
array。对每条working entry计算inclusive end，超过 ``resource_size_t`` 表示范围能力时留空跳过；
其余设置name、start/end、flags与descriptor：RAM使用 ``IORESOURCE_SYSTEM_RAM``，ACPI/NVS/
unusable/reserved/soft-reserved/PRAM/PMEM使用 ``IORESOURCE_MEM`` 并带对应desc。

低于1 MiB的所有type与RAM/ACPI/NVS/unusable立即加 ``IORESOURCE_BUSY`` 并
``insert_resource(iomem_resource,...)``。此前042已插入的Kernel code/rodata/data/bss ranges可由新
System RAM parent按区间包含关系收养；不会重复映射kernel。

高地址device-like E820 ranges延后给PCI survey发布
-----------------------------------------------

``e820_device_region`` 只把1 MiB以上的RESERVED、SOFT_RESERVED、PRAM、PMEM判为device-like。它们
当前resource object已填好，但没有busy flag/parent，避免在PCI BAR survey前制造冲突。later
``pcibios_resource_survey → e820__reserve_resources_late`` 才把它们插入ordinary或soft-reserve tree。

这与048的IOAPIC resources相同地说明“对象已分配”不等于“已发布”：IOAPIC objects同样要到later
PCI survey的 ``ioapic_insert_resources`` 才进入tree。紧随其后的049 standard-I/O hook不会插入
IOAPIC memory resources。

kexec E820 snapshot进入firmware-map视图
--------------------------------------

函数最后遍历的是 ``e820_table_kexec``，不是继续变化的working table，也不是原始firmware table；
每条调用 ``firmware_map_add_early``。这是供firmware-map/sysfs与kexec语义使用的snapshot view，和
当前resource ownership仍是两份结构。

nosave holes只影响休眠镜像
--------------------------

``e820__register_nosave_regions(max_pfn)`` 遍历sorted working E820的RAM entries，从0开始把前一段
RAM end到下一段RAM start之间登记为PFN nosave，最后登记到 ``max_pfn``。它不改E820、不reserve
memblock，也不取消direct mapping；只告诉software suspend/hibernate不要把non-RAM holes当普通
page保存。

ACPI NVS另由core initcall ``e820__register_nvs_regions`` 交给 ``acpi_nvs_register``，保持固件跨
suspend状态；nosave hole与NVS special save/restore不能合并成“丢弃非RAM”。

ordinary resource hook只占用十组legacy I/O ports
------------------------------------------------

``x86_init.resources.reserve_resources`` 在ordinary x86-64指向 ``reserve_standard_io_resources``，
依次向 ``ioport_resource`` request DMA1、PIC1、PIT timer ranges、keyboard ports、DMA page registers、
PIC2、DMA2与legacy FPU的 ``0x00..0xff`` 子区间。它只声明busy I/O ownership，不编程PIC/PIT、读取
keyboard或初始化ISA DMA。

平台可替换该hook；fixed q35 ordinary path使用默认表。再次强调：该call没有调用
``ioapic_insert_resources``。

PCI gap是低4 GiB最大E820空洞的建议起点
---------------------------------------

``e820__setup_pci_gap`` 以4 MiB为minimum，扫描working E820 entries之间及最后entry到4 GiB的空洞，
选择size最大的gap并令 ``pci_mem_start=max_gap_start``。相同size用后出现gap，因为比较是 ``>=``。

x86-64若没有至少4 MiB候选，fallback为 ``(max_pfn<<PAGE_SHIFT)+1MiB`` 并警告unassigned 32-bit BARs
可能无法工作。这里不创建 ``pci_dev``、不读BAR size、不写BAR；只是给later PCI resource assignment
一个起点，actual host bridge windows与existing BARs仍在后面survey。

VGA screen registration保持build与EFI-memory条件
-----------------------------------------------

``CONFIG_VT && CONFIG_VGA_CONSOLE`` 时，BIOS路径因 ``!EFI_BOOT`` 满足guard，调用
``vgacon_register_screen`` 使用早先保存的 ``sysfb_primary_display.screen``；EFI路径还要求VGA
aperture不是conventional memory。它不加载DRM或重置显示硬件。fixed command line显式
``console=ttyS0``，也不排除build下同时存在VGA console candidate。

OEM banner与wallclock hook不读取当前日期
----------------------------------------

``x86_init.oem.banner`` default输出当前 ``pv_info.name``；QEMU accelerator/hypervisor detection未固定，
不能写死bare hardware或KVM。 ``x86_init.timers.wallclock_init`` default
``x86_wallclock_init`` 只在Device Tree含disabled ``motorola,mc146818`` node时，把future
get/set-wallclock替换为no-op。fixed ``initial_dtb=0``，所以不改default RTC backend；本次call没有从
CMOS读取年月日，也不设置timekeeping clock。

thermal LVT只保存支持CPU上的BSP firmware值
--------------------------------------------

``therm_lvt_init`` 编入Intel thermal支持且boot CPU同时有ACPI thermal/ACC features时读取
``APIC_LVTTHMR`` 到 ``lvtthmr_init``。后面 ``setup_local_APIC`` 会soft-disable/mask相关entry，AP又
会因INIT reset LVT，所以先保存BSP firmware mode供恢复。unsupported CPU/build是no-op；当前仍不
enable thermal vector或发送interrupt。

``mcheck_init`` 建MCE software dispatch，不重新探bank
---------------------------------------------------

fixed function注册early、uncorrected与default decode notifier chains， ``INIT_WORK(mce_work,...)``，
并初始化 ``mce_irq_work``。CPU bank/capability与CR4.MCE另有更早/后续CPU paths；work object初始化
也不表示worker已调度。

``register_refined_jiffies(CLOCK_TICK_RATE)`` 复制jiffies clocksource参数并按known cycles/sec计算
更精细mult/shift后注册candidate。它不打开timer IRQ、不推进jiffies，也不表示timekeeping已选择它。

BIOS跳过EFI memmap quirk，unwinder按build完成最后入口
-----------------------------------------------------

``efi_apply_memmap_quirks`` 只在 ``EFI_BOOT`` 执行，fixed SeaBIOS路径skip。最后
``unwind_init`` 在 ``CONFIG_UNWINDER_ORC`` 下验证build-time sorted ORC IP/entry table sizes并建立fast
lookup blocks；bad table会禁用，非ORC build是inline no-op。

此后 ``setup_arch`` 没有更多语句，普通C return回到同一CPU0/stack上的 ``start_kernel``。没有task
switch、mode switch或IRQ enable；下一条才是 ``mm_core_init_early``。

本章结束状态
------------

* current executor：CPU0上的 ``start_kernel``， ``setup_arch`` 已返回；
* precise next： ``mm_core_init_early()`` 尚未调用；
* CPU/mode：BSP/logical CPU0，x86-64 long mode，IF=0， ``early_boot_irqs_disabled=true``；
* working E820 resources：system ranges已busy插入，high device-like ranges留待PCI survey；
* firmware-map early view：由 ``e820_table_kexec`` 建立；
* hibernation nosave：non-RAM PFN holes已登记；
* standard I/O ports：ordinary fixed table已busy request；
* IOAPIC resources：仍未插入 ``iomem_resource``；
* ``pci_mem_start``：低4 GiB最大gap或fallback symbolic value；尚未分配BAR；
* VGA/OEM/wallclock/thermal/MCE：按上述build/runtime边界完成；
* refined-jiffies：候选已注册，timer/timekeeping未完成；
* EFI memmap quirk：fixed BIOS skip；unwinder按config完成或no-op；
* buddy/slab/per-CPU/scheduler/AP：均未初始化或启动；
* initramfs：仍未普通unpack。

关键边界
--------

#. memblock allocation identity、iomem/ioport resource ownership与PTE mapping是不同结构。
#. working E820生成current resources； ``e820_table_kexec`` 生成firmware-map early view。
#. high device-like E820与IOAPIC resources都延后到PCI survey插入，不属于049 standard-I/O hook。
#. nosave PFN registration不reserve/unmap memory；NVS有独立save/restore registration。
#. standard I/O request只声明ports，不初始化相应legacy devices。
#. ``pci_mem_start`` 是later allocation hint，不是一个已分配BAR/window。
#. wallclock init只可能禁用future backend，不读取RTC日期。
#. thermal LVT保存、MCE software work、clocksource candidate都不等于对应interrupt/runtime已启动。
#. EFI branch由 ``EFI_BOOT`` guard；ORC结果由build/table validation决定。
#. ``setup_arch`` return只是回到 ``start_kernel``，当前仍CPU0/IF=0/init_task。

下一入口
--------

第050章从：

.. code-block:: c

   mm_core_init_early();

开始。进入前memblock仍拥有RAM/reservations，zone/``struct page``/buddy containers尚未由generic MM
建立。

资料
----

* `Linux 7.2-rc1固定提交：setup_arch最后resource到unwind顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L1244-L1282>`_；
* `Linux 7.2-rc1固定提交：E820 current resources与kexec firmware map <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c#L1071-L1160>`_；
* `Linux 7.2-rc1固定提交：nosave holes与PCI gap <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/e820.c#L645-L803>`_；
* `Linux 7.2-rc1固定提交：standard PC I/O resources <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L630-L666>`_；
* `Linux 7.2-rc1固定提交：wallclock hook只检查disabled DT RTC <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/x86_init.c#L42-L62>`_；
* `Linux 7.2-rc1固定提交：thermal LVT保存 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/thermal/intel/therm_throt.c#L711-L724>`_；
* `Linux 7.2-rc1固定提交：MCE software dispatch初始化 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/mce/core.c#L2368-L2380>`_；
* `Linux 7.2-rc1固定提交：ORC validation与lookup init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/unwind_orc.c#L333-L384>`_。
