第四十五章：Linux 怎样从 MADT、MP table 和 SRAT 建立 CPU 拓扑与 NUMA node？
==========================================================================

第四十四章结束时，``setup_arch()`` 已经完成：

.. code-block:: text

   dynamic printk ring buffer（按需）
   initrd_start / initrd_end
   ACPI initial table list
   ACPI table physical reservations

当前下一条调用是：

.. code-block:: c

   vsmp_init();

本章继续到 ``initmem_init()`` 返回。这个阶段不会唤醒 AP，也不会建立完整中断系统。它先回答两类更基础的问题：

* 机器可能有哪些逻辑 CPU，它们的 APIC ID 是什么；
* 哪些物理 RAM 属于哪个 NUMA node。

为什么在 ACPI 前先检查 ScaleMP vSMP
----------------------------------

``vsmp_init()`` 是 ScaleMP vSMPowered 系统的专用兼容路径。

它通过早期 PCI config access 检查：

.. code-block:: text

   bus 0
   device 0x1f
   function 0
   vendor/device = ScaleMP vSMP controller

若没有匹配，函数立即返回。

当前固定平台是 QEMU q35，其 ``00:1f.0`` 是 ICH9 LPC bridge，不是 ScaleMP controller，因此主线不会进入 vSMP 控制寄存器映射、CPU 数量限制或 IRQ affinity 特殊处理。

保留这一步的意义是：在 CPU 拓扑尚未最终建立前，某些聚合式大机器平台需要先修正内核对硬件结构的假设。

I/O delay 不是普通睡眠
---------------------

下一条调用：

.. code-block:: c

   io_delay_init();

传统 x86 设备有时要求两个端口操作之间留出很短间隔。``inb_p()``、``outb_p()`` 等接口会通过 ``native_io_delay()`` 实现延迟。

Linux 支持四种策略：

.. code-block:: text

   outb to port 0x80
   outb to port 0xed
   udelay(2)
   no delay

默认策略由 Kconfig 决定，也可以通过：

.. code-block:: text

   io_delay=0x80
   io_delay=0xed
   io_delay=udelay
   io_delay=none

覆盖。

``io_delay_init()`` 本身不执行一轮设备延迟测试。它主要在没有命令行 override 时查询 DMI quirk table，避开那些向 ``0x80`` 写入会锁死的旧式 HP/Compaq 机器。

QEMU q35 不匹配这些 DMI 项，主线保持编译时默认策略。

``early_platform_quirks()`` 为什么必须早于 MADT/NUMA
--------------------------------------------------

随后：

.. code-block:: c

   early_platform_quirks();

这里处理的是必须在 PCI core、ACPI 中断和普通驱动出现前完成的芯片组修正。它可以通过 early PCI config 访问识别特定 northbridge/southbridge，修正 HPET、timer routing、IOMMU aperture 或其他平台状态。

这些 quirk 若改变定时器、APIC 或内存可见性，必须先于后面的 MADT、NUMA 与页表最终布局。

当前 q35 路径仍执行检测框架，但不会命中面向旧实体芯片组的大多数 workaround。

``early_acpi_boot_init()`` 不是完整 ACPICA namespace 初始化
---------------------------------------------------------

接下来进入：

.. code-block:: c

   early_acpi_boot_init();

第四十四章的 ``acpi_boot_table_init()`` 只定位并保留表。现在才把 table parser 推进到可读取关键内容的状态。

函数顺序是：

.. code-block:: text

   acpi_table_init_complete()
   → parse BOOT table
   → ACPI blacklist check
   → early_acpi_process_madt()
   → hardware-reduced ACPI conditional setup

仍然没有：

* 创建 ACPI namespace 中的 device object；
* 执行 DSDT/SSDT AML method；
* 加载 ACPI driver；
* 建立 ``/sys/firmware/acpi``；
* 处理电池、热区或电源按钮。

当前只提取启动必须的拓扑和中断控制器信息。

MADT 先回答“CPU 和 APIC 在哪里”
--------------------------------

MADT 是 Multiple APIC Description Table。SeaBIOS/QEMU 前面已经生成它，Linux 的 early pass 重点读取：

* Local APIC 或 x2APIC entry；
* 每个处理器的 ACPI processor UID；
* APIC ID；
* enabled / online-capable flags；
* Local APIC physical base；
* PCAT compatibility flag。

每个可用处理器 entry 通过拓扑登记路径写入早期 CPU/APIC 表，例如：

.. code-block:: text

   logical CPU candidate
   ↔ APIC ID
   ↔ ACPI processor UID
   ↔ enabled state

这里的“登记”不等于 CPU 已经运行 Linux。

当前仍只有 BSP / Linux CPU 0 在线。其他 CPU 只是被列入 possible topology，真正的 INIT/SIPI 和 secondary startup 要等 ``smp_init()``。

为什么 QEMU 的 disabled CPU entry 也可能被计数
--------------------------------------------

ACPI 规范支持 hot-pluggable CPU。QEMU 可能在 MADT 中给出未启用但未来可上线的 CPU entry。

Linux 的 ``acpi_is_processor_usable()`` 会考虑：

* ``ACPI_MADT_ENABLED``；
* ACPI 6.3+ ``ONLINE_CAPABLE``；
* 虚拟化环境对 legacy disabled entry 的兼容语义。

这样 ``nr_cpu_ids`` 和 possible CPU mask 可以为后续 CPU hotplug 预留空间，而不是只统计开机时已经 enabled 的 CPU。

当前固定配置没有明确指定 CPU hotplug 拓扑，因此正文不假定额外 disabled CPU 的具体数量，只保留真实分支。

hardware-reduced ACPI 条件路径
------------------------------

若 FADT 声明 hardware-reduced ACPI，``acpi_reduced_hw_init()`` 会取消传统 PC timer/PIC 假设。

QEMU q35 + SeaBIOS 模拟的是普通 PC-compatible ACPI 平台，不走该分支。传统 PIC、RTC、HPET/APIC 等后续路径仍存在。

为什么还要检查 MP table
-----------------------

``early_acpi_boot_init()`` 返回后，``setup_arch()`` 调用：

.. code-block:: c

   x86_init.mpparse.early_parse_smp_cfg();

默认实现是早期 MP table parser。

MP Specification table 是 ACPI 普及前描述 processor、bus、I/O APIC 和 interrupt route 的机制。SeaBIOS 也可能提供 MP table，以兼容旧操作系统。

Linux 的策略不是无条件把 ACPI 与 MP table 两份结果混在一起，而是：

.. code-block:: text

   优先使用可用 ACPI/MADT
   → ACPI 不足、被禁用或需要 fallback 时再参考 MP table

当前 q35 主线已有有效 MADT，因此 MP table 不会取代 ACPI CPU 拓扑。

Device Tree 条件入口为何也在 x86
-------------------------------

下一步：

.. code-block:: c

   x86_flattree_get_config();

虽然传统 PC 主要使用 ACPI，Linux x86 也支持部分 Device Tree 启动环境。该函数在有 flattened device tree 时导入配置。

SeaBIOS + GRUB i386-pc 固定主线没有传入 DTB，因此当前调用退化为无操作。

这再次说明 ``setup_arch()`` 是多平台汇合点：同一个 x86 内核要兼容 BIOS/ACPI、EFI、Xen、特殊嵌入式平台和 Device Tree。

``initmem_init()`` 的名字为什么容易误导
--------------------------------------

接着调用：

.. code-block:: c

   initmem_init();

它没有重新建立第四十三章的 direct map，也没有初始化 buddy allocator。

在 x86-64 上，它的主体只有：

.. code-block:: c

   x86_numa_init();

它要把已经存在的 ``memblock.memory`` 从“没有 node 归属的物理区间”变成“属于某个 NUMA node 的物理区间”。

NUMA 要解决什么问题
-------------------

UMA 机器可以把所有 RAM 看成一个同等距离的池。

NUMA 机器上：

.. code-block:: text

   CPU package / socket A 访问 node A RAM 更近
   CPU package / socket A 访问 node B RAM 更远

内核需要知道：

* 每段物理 RAM 属于哪个 node；
* 每个 APIC ID/CPU 属于哪个 node；
* 哪些 node 有内存；
* 哪些 node 只有 CPU 或 generic initiator；
* 每个 node 的 PFN 范围。

这些信息会影响后面的 page allocator、scheduler、per-CPU allocation 和 zonelist。

``x86_numa_init()`` 的尝试顺序
-----------------------------

若没有 ``numa=off``，Linux依次尝试：

.. code-block:: text

   ACPI SRAT
   → AMD northbridge NUMA
   → Device Tree（特定条件）
   → dummy single node fallback

每种方法通过 ``numa_memblks_init()`` 建立 node memory block，然后验证这些 block 是否合理覆盖 memblock RAM。

ACPI SRAT 如何补充 MADT
----------------------

MADT 主要描述 CPU/APIC 与中断控制器，SRAT 是 System Resource Affinity Table，描述资源亲和性。

典型 SRAT entry 给出：

* Processor Local APIC/x2APIC Affinity：APIC ID 属于哪个 proximity domain；
* Memory Affinity：某段物理地址属于哪个 proximity domain；
* enabled、hot-pluggable、non-volatile 等标志。

Linux 把 proximity domain 转换为内部 node ID，并调用类似：

.. code-block:: text

   memblock_set_node(physical range, node id)

因此 E820 与 SRAT 扮演不同角色：

.. code-block:: text

   E820  回答这段地址是不是 RAM、reserved、ACPI 等
   SRAT  回答这段 RAM 更接近哪个 CPU/node

只有两者结合，物理 RAM 才同时拥有“可用性类型”和“拓扑归属”。

默认 q35 主线可能只有一个 node
------------------------------

固定主线没有规定 QEMU ``-numa`` 参数。

若 QEMU 未提供有效 SRAT，``x86_acpi_numa_init()`` 不能建立多 node 拓扑，Linux 最终进入 ``dummy_numa_init()``：

.. code-block:: text

   node 0
   memory range = 0 .. max_pfn

随后把实际 memblock RAM ranges 归入 node 0。

这不是关闭 NUMA 代码，而是用 NUMA 框架表达一台单 node 机器。以后通用内存管理无需为 UMA/NUMA 使用两套完全不同的数据结构。

若运行时给 q35 配置 ``-numa`` 并生成 SRAT，本章同一源码会建立多个 node；正文固定控制流不编造具体 node 数量。

``numa_register_nodes()`` 怎样把 node 变成内核对象
------------------------------------------------

NUMA memory block 验证成功后，Linux 遍历 ``node_possible_map``。

对每个拥有有效 PFN 范围的 node：

#. 根据 ``memblock_set_node()`` 后的区间计算 start/end PFN；
#. 分配 node data（``pg_data_t``）；
#. 把 node 标记 online；
#. 保留 CPU-to-node 和 APIC-to-node 的早期映射。

``pg_data_t`` 将成为后面 zone、free_area、watermark、zonelist 等内存管理对象的根。

此刻只是创建 node 基础，不代表 zone 和 buddy allocator 已经完成。

无归属 CPU 怎样处理
------------------

部分固件只描述 memory node，没有为所有 possible CPU 给出完整 affinity。

``numa_init_array()`` 会把尚无 node 的 CPU 按现有 online node 轮转分配一个早期归属，避免 ``cpu_to_node`` 长期保持 ``NUMA_NO_NODE``。

这是一种启动期兜底。若 ACPI 提供准确映射，正常 CPU 使用固件给出的 node。

本章结束时建立了什么
--------------------

本章把两条独立信息链接起来：

.. code-block:: text

   MADT / MP table
   → possible CPU 与 APIC ID

   SRAT / fallback
   → physical RAM 与 NUMA node

CPU 还没有上线，page allocator 也没有启动，但后续代码已经可以问：

.. code-block:: text

   这个 CPU 属于哪个 node？
   这段 memblock RAM 属于哪个 node？
   系统有哪些 possible/online memory nodes？

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* interrupts：关闭；
* ScaleMP vSMP：q35 主线未检测到；
* I/O delay strategy：已完成配置/quirk 检查；
* ACPI initial tables：已完成 early parser；
* MADT：已进行早期 Local APIC/x2APIC CPU 拓扑处理；
* MP table：已完成 fallback 条件检查；
* AP：尚未唤醒；
* Device Tree：固定主线未提供；
* NUMA：已尝试 SRAT/平台方法并保证至少建立 node 0；
* ``memblock.memory``：已带 node 归属；
* node data：已为有效 node 分配并标记 online；
* zone、buddy allocator：尚未建立；
* ``setup_arch()``：仍未返回。

下一条控制流从：

.. code-block:: c

   dma_contiguous_reserve(max_pfn_mapped << PAGE_SHIFT);

继续，随后处理 crashkernel、early xHCI debug、``x86_init.paging.pagetable_init()``、KASAN shadow 和 initial page-table 同步。

资料
----

* `Linux 6.12.95 setup.c：vsmp、I/O delay、early ACPI、MP table 与 initmem_init 调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 vsmp_64.c：ScaleMP vSMP 检测和控制 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/vsmp_64.c>`_
* `Linux 6.12.95 io_delay.c：0x80、0xed、udelay 与 none 策略 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/io_delay.c>`_
* `Linux 6.12.95 quirks.c：early platform quirks <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/quirks.c>`_
* `Linux 6.12.95 ACPI boot.c：early_acpi_boot_init、MADT 与后续 acpi_boot_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/acpi/boot.c>`_
* `Linux 6.12.95 NUMA numa.c：SRAT/AMD/DT 尝试与 dummy node fallback <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/numa.c>`_
* `Linux 6.12.95 init_64.c：initmem_init 到 x86_numa_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init_64.c>`_
* `ACPI 6.5：MADT 与 SRAT 定义 <https://uefi.org/specs/ACPI/6.5/>`_