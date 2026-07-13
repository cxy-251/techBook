第四十八章：Linux 怎样完成 ACPI、Local APIC、IOAPIC 与 possible CPU 拓扑？
============================================================================

第四十七章结束时，Linux 已经完成 early MADT pass、early PCI quirks 和 CPU 命令行上限，但它仍没有建立完整中断模型。

当前下一条调用是：

.. code-block:: c

   acpi_boot_init();

本章追踪到：

.. code-block:: c

   x86_init.hyper.guest_late_init();

返回。期间 Linux 会把固件表中的 FADT、MADT、HPET、SPCR 信息转成内核的启动期中断/定时器模型，执行 MP table fallback，确认 Local APIC 映射，最终确定 possible CPU 数量、CPU-to-node 关系和 IOAPIC MMIO 映射。

为什么 ``early_acpi_boot_init()`` 后还要再解析一次 ACPI
------------------------------------------------------

第四十五章中的 early pass 主要服务 NUMA：在 ``initmem_init()`` 之前尽早登记 processor APIC ID，使 SRAT processor affinity 可以关联到 CPU。

现在的 ``acpi_boot_init()`` 目标更完整：

.. code-block:: text

   FADT  → SCI、PM timer 与平台电源寄存器基础
   MADT  → Local APIC、IOAPIC、GSI 与 interrupt source override
   HPET  → 高精度事件定时器物理信息
   BGRT  → 可选启动图像信息
   SPCR  → 可选固件串口控制台描述
   PCI   → 是否把后续 PCI 初始化切换到 ACPI 路径

所以 early pass 和 full pass 不是重复浪费。前者先满足内存拓扑依赖，后者在 early quirks 已经修正 timer/APIC 异常后建立完整平台模型。

晚期 DMI ACPI quirk 为什么放在这里
---------------------------------

``acpi_boot_init()`` 首先执行：

.. code-block:: c

   dmi_check_system(acpi_dmi_table_late);

这张表中的修正必须等 ``early_quirks()`` 已经运行后才判断，例如某些机器需要忽略 BIOS 提供的 IRQ0 timer override。

如果在 chipset quirk 前决定，Linux 可能把一个原本可修正的 MADT override 当成最终事实。

当前 QEMU q35 不匹配这些旧实体主板 DMI 项，主线继续使用 SeaBIOS/QEMU 生成的 ACPI 表。

ACPI 被禁用时控制流怎样退化
---------------------------

若命令行有 ``acpi=off``，表校验失败，或平台 blacklist 禁用 ACPI：

.. code-block:: c

   if (acpi_disabled)
       return 1;

后面的 ``x86_init.mpparse.parse_smp_cfg()`` 会尝试从 Intel MP Specification table 获取 CPU、bus、IOAPIC 与 IRQ route。

这就是紧接着保留 MP table parser 的原因：x86 不能把启动完全押在 ACPI 单一路径上。

当前固定 q35 主线有有效 ACPI，因此以 ACPI 为主，MP table 只承担兼容 fallback。

FADT 首先建立哪些启动事实
------------------------

函数调用：

.. code-block:: c

   acpi_table_parse(ACPI_SIG_FADT, acpi_parse_fadt);

FADT 是 Fixed ACPI Description Table。它把平台的固定电源管理接口描述给操作系统，包括：

* SCI（System Control Interrupt）编号；
* PM timer I/O/MMIO 地址；
* PM1 event/control block；
* reset register；
* century register；
* hardware-reduced ACPI 标志；
* DSDT/FACS 地址等。

``acpi_parse_fadt()`` 在当前阶段重点把 Linux 后续必须使用的 SCI 和 PM timer 信息转成 x86 全局状态。

SCI 为什么不是普通设备 IRQ
-------------------------

SCI 是 ACPI 固件向操作系统报告电源管理事件的共享中断，例如：

* 电源按钮；
* sleep/wake；
* thermal event；
* ACPI GPE。

FADT 给出 SCI interrupt number，但其实际送达路径还依赖 MADT 中的 GSI 与 interrupt override。

因此 Linux 先读 FADT 得到“ACPI 使用哪个中断”，再读 MADT 确认“这个中断怎样经 IOAPIC 路由”。

PM timer 为什么现在只记录地址
----------------------------

FADT 也提供 ACPI PM timer。它是固定频率计数器，可用于校准或作为 clocksource 候选。

此时 Linux 只完成地址和平台能力登记，尚未进行完整 timekeeping/clocksource 选择。真正启用哪个时钟源要等 timer infrastructure 更后面初始化。

``acpi_process_madt()`` 的完整 pass
---------------------------------

下一步：

.. code-block:: c

   acpi_process_madt();

MADT header 给出 Local APIC 基址和 PCAT compatibility。其 subtables 进一步描述：

* Processor Local APIC；
* Processor Local x2APIC；
* IOAPIC；
* Interrupt Source Override；
* NMI Source；
* Local APIC NMI；
* Local APIC Address Override。

第四十五章已经登记 processor entry；现在完整 pass 重点加入 interrupt-controller 和 route 信息。

Local APIC 与 IOAPIC 负责不同层次
--------------------------------

可以把两者分开理解：

.. code-block:: text

   Local APIC
   → 每个 CPU 自己的中断控制器
   → 接收 vector、IPI、local timer、LINT/NMI

   IOAPIC
   → 芯片组/平台的外部中断路由器
   → 把设备 GSI 送到目标 CPU 的 Local APIC vector

AHCI、网络、USB 等设备产生的 legacy INTx/GSI，最终要经过 IOAPIC 路由到某个 CPU 的 Local APIC。

MADT 的 IOAPIC entry 建立什么
----------------------------

每个 IOAPIC entry 提供：

* IOAPIC hardware ID；
* MMIO physical address；
* ``GSI base``。

Linux 通过注册路径建立内部 ``ioapics[]`` 数据，并读取硬件 version/register count，计算该 IOAPIC 管理的 GSI 范围。

在典型 q35 虚拟平台中，IOAPIC MMIO 通常位于 PC 兼容的高端固定区域；正文不把一个具体地址当成所有配置的必然值，实际值以 MADT entry 为准。

Interrupt Source Override 为什么重要
-----------------------------------

传统 ISA IRQ 号与 IOAPIC GSI 不总是一一相同。MADT override 可以描述：

.. code-block:: text

   source IRQ
   → target GSI
   → polarity
   → trigger mode

典型例子是：

* legacy IRQ0 timer 被改路由；
* SCI 使用 level-triggered / active-low；
* 某些 IRQ 不再落在同号 GSI。

Linux 把这些 override 写入 ISA IRQ→GSI 映射和中断 route 数据。后续驱动请求 IRQ 时看到的是内核整理后的中断域，而不是盲目相信“IRQ n 就是 pin n”。

NMI entry 为什么也在 MADT
------------------------

NMI 不走普通可屏蔽 IRQ 语义。MADT 可以描述：

* 哪个 GSI 是 NMI source；
* 某个或全部 processor 的 LINT0/LINT1 如何接 NMI；
* polarity 和 trigger mode。

这为 watchdog、平台错误和不可屏蔽事件建立基础。此时只登记拓扑，NMI handler 和完整 Local APIC 编程仍在后续阶段。

HPET 表建立候选定时器
---------------------

接着：

.. code-block:: c

   acpi_table_parse(ACPI_SIG_HPET, acpi_parse_hpet);

HPET table 提供：

* hardware ID；
* MMIO address；
* sequence number；
* minimum tick；
* page protection 属性。

Linux 记录 HPET 物理地址和可用性。early quirk 可能已经因硬件缺陷禁用它，所以这里必须在 ``early_quirks()`` 之后。

当前 q35 通常提供虚拟 HPET，但最终是否把它作为 clocksource/clockevent，还要看配置、命令行和后续校准结果。

BGRT 和 SPCR 为什么也是条件路径
------------------------------

``CONFIG_ACPI_BGRT`` 启用时，Linux 可以读取 BGRT，记录固件启动图像的位置和状态。

SPCR 描述固件选定的串口控制台，包括 UART 类型、地址、波特率和中断。Linux 可以据此建立 early console。

固定主线已经显式使用：

.. code-block:: text

   console=ttyS0

所以控制台目标来自命令行；SPCR 是否存在并不是主线必需条件。

为什么 ACPI 会替换 PCI 初始化钩子
------------------------------

若 ACPI IRQ 没有被禁用：

.. code-block:: c

   x86_init.pci.init = pci_acpi_init;

这并没有立即枚举 PCI 设备。它只是选择以后 PCI subsystem 初始化时使用 ACPI-aware 路径，以便处理：

* root bridge；
* PCI IRQ routing；
* ACPI host bridge resources；
* _OSC 等平台协商。

SeaBIOS 已经配置过 PCI BAR，不代表 Linux 可以跳过自己的 PCI enumeration。固件配置是启动初值，Linux 后续仍要建立设备模型和资源所有权。

MP table parser 怎样与 ACPI 共存
-------------------------------

``acpi_boot_init()`` 返回后：

.. code-block:: c

   x86_init.mpparse.parse_smp_cfg();

默认 MP parser 会检查 ``smp_found_config``、ACPI 成功状态和已有 topology，避免重复注册同一套有效配置。

其角色是：

.. code-block:: text

   ACPI 有效且完整
   → 保留 ACPI 结果

   ACPI 禁用/损坏/缺项
   → 使用 MP table 补足或回退

固定 q35 主线继续采用 ACPI 的 MADT/IOAPIC 数据。

``init_apic_mappings()`` 为什么叫“最后机会”
----------------------------------------

源码注释：

.. code-block:: c

   /* Last opportunity to detect and map the local APIC */
   init_apic_mappings();

若 x2APIC 已启用，Local APIC 通过 MSR 接口访问，不需要 MMIO fixmap，函数直接返回。

若不是 x2APIC，并且 ACPI/MP parser 已经找到 SMP configuration，Local APIC 地址应当已被登记并映射。

只有在：

.. code-block:: c

   !smp_found_config

时，函数才主动检测默认 Local APIC：

#. 检查 ``nolapic`` / APIC disabled；
#. 根据 CPU vendor/family/features 判断 Local APIC 能力；
#. 检查 ``MSR_IA32_APICBASE``；
#. 必要时在用户指定 ``lapic`` 的情况下尝试重新启用；
#. 验证默认 APIC physical base。

失败时 Linux 调用 ``apic_disable()``，退化到单处理器/PIC 路径。

当前 q35 + MADT 主线已有有效 APIC 配置，因此这一步主要确认现有结果，不走无固件配置的最后补救分支。

Local APIC MMIO 怎样进入 fixmap
-----------------------------

非 x2APIC 模式下，``register_lapic_address()`` 把 MADT 给出的物理地址保存到：

.. code-block:: c

   mp_lapic_addr

然后：

.. code-block:: c

   set_fixmap_nocache(FIX_APIC_BASE, mp_lapic_addr);

得到固定虚拟地址 ``APIC_BASE``。页属性必须是 uncached/device-like，不能让普通 CPU cache 缓存 APIC 寄存器访问。

``topology_init_possible_cpus()`` 最终决定什么
-------------------------------------------

到这里，firmware parser 已经登记所有接受的 APIC ID。现在 Linux 把临时统计转为最终 possible CPU 空间：

.. code-block:: c

   topology_init_possible_cpus();

它综合：

* 已登记并分配 logical ID 的 CPU；
* 固件描述但当前 disabled 的 CPU；
* ``nr_cpu_ids`` 命令行/编译上限；
* 是否找到 SMP config；
* Local APIC 是否禁用；
* package/die/core/thread topology bitmap。

若根本没有登记 boot APIC，它会伪造 APIC ID 0 的 boot CPU topology，使通用查询接口仍可工作。

为什么 disabled CPU 也可能属于 possible
--------------------------------------

possible CPU 表示内核为其保留 logical CPU 编号和相关数据结构的 CPU。它可能：

* 当前 present 且稍后会启动；
* firmware 描述为 disabled/online-capable，可供 CPU hotplug；
* 永远不会在本次运行出现，但受 ``possible_cpus=`` 预留。

``topology_init_possible_cpus()`` 会计算：

* ``total_cpus``；
* 最终 ``nr_cpu_ids``；
* logical packages；
* nodes per package；
* dies per package；
* threads per core；
* cores/threads per package。

这些是“可枚举拓扑上限”，不等于所有 CPU 已在线。

``init_cpu_to_node()`` 把 CPU 拓扑接回 NUMA
----------------------------------------

第四十五章已经从 SRAT 建立 APIC ID→node 映射。现在 logical CPU ID 已经确定，Linux 可以执行：

.. code-block:: c

   init_cpu_to_node();

对每个 possible CPU：

#. 查它的 APIC ID；
#. 从 ``__apicid_to_node[]`` 取得 NUMA node；
#. 必要时把 memoryless CPU node 标记 online；
#. 填写 early ``cpu_to_node`` 映射。

这一步把：

.. code-block:: text

   logical CPU number
   ↔ APIC ID
   ↔ NUMA node

三者连接起来。

``init_gi_nodes()`` 处理没有 CPU/内存的发起者
------------------------------------------

ACPI SRAT 还可以描述 Generic Initiator，例如某些 accelerator 或设备 initiator。一个 node 可能没有 CPU、没有普通 RAM，却有距离/亲和性意义。

``init_gi_nodes()`` 把这类 node 临时标记 online，使后续 node data 和 zonelist 建立前不会丢失它们。

固定普通 q35 配置通常没有 Generic Initiator node，此函数成为条件空路径。

``io_apic_init_mappings()`` 怎样映射 IOAPIC
-----------------------------------------

随后：

.. code-block:: c

   io_apic_init_mappings();

函数先为每个已登记 IOAPIC 分配一个 ``struct resource``，名称类似：

.. code-block:: text

   IOAPIC 0
   IOAPIC 1

然后从 MADT/MP data 取得每个 IOAPIC physical address，把它映射到连续 fixmap 槽位：

.. code-block:: text

   FIX_IO_APIC_BASE_0 + index

映射属性是 ``FIXMAP_PAGE_NOCACHE``。在内存加密 guest 中，还会根据该 MMIO 是 private 还是 shared 调整 encryption pgprot。

为什么这里只映射，尚未编程 redirection table
------------------------------------------

本阶段的目标是让内核能够访问 IOAPIC register window，并保存其物理资源。

真正的：

* mask/unmask pin；
* 建立 IRQ domain；
* 分配 vector；
* 写 redirection table；
* 选择目标 CPU；
* 启用设备中断；

会在 IRQ/APIC 初始化更后面发生。

所以“IOAPIC 已映射”不等于“外部设备中断已经打开”。当前 CPU 的全局 interrupt flag 仍关闭。

``guest_late_init()`` 是最后的平台插槽
-------------------------------------

本章最后执行：

.. code-block:: c

   x86_init.hyper.guest_late_init();

普通 native 默认实现是空函数。某些 hypervisor guest 可以在 CPU/APIC/NUMA 拓扑已完成后执行最后修正。

QEMU 是否由 KVM、TCG 或其他 accelerator 驱动没有在固定主线中限定，因此正文不假定某个 hypervisor-specific late hook 一定运行。

本章结束时建立了什么
--------------------

本章完成了从固件描述到 Linux 内部启动拓扑的转换：

.. code-block:: text

   FADT
   → SCI / PM timer 基础

   MADT
   → Local APIC / IOAPIC / GSI override / NMI

   firmware CPU entries
   → logical possible CPU IDs
   → package/die/core/thread topology
   → CPU-to-NUMA node

   IOAPIC physical windows
   → fixed uncached kernel virtual mappings

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* interrupts：全局关闭；
* ACPI FADT：SCI 和 PM timer 等启动信息已解析；
* MADT：processor、Local APIC、IOAPIC、GSI override 与 NMI 信息已处理；
* HPET/SPCR/BGRT：已完成条件解析；
* PCI 初始化钩子：正常 ACPI 路径已选择 ``pci_acpi_init``；
* MP table：已完成 fallback 检查；
* Local APIC：已确认，非 x2APIC 模式下已有 fixmap；
* possible CPU 数量与拓扑：已最终确定；
* CPU-to-node：已建立；
* IOAPIC：MMIO 已映射，redirection table 尚未正式启用；
* AP：尚未唤醒；
* 普通设备 IRQ：尚未开放；
* ``setup_arch()``：尚未返回。

下一条控制流从：

.. code-block:: c

   e820__reserve_resources();

开始，把 E820、IOAPIC、内核和标准 PC I/O 范围注册进 resource tree，然后完成 wall clock、thermal LVT、machine check 和 unwind 初始化，最终离开 ``setup_arch()``。

资料
----

* `Linux 6.12.95 setup.c：完整 ACPI、APIC、topology 与 IOAPIC 调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c>`_
* `Linux 6.12.95 ACPI boot.c：acpi_boot_init、FADT、MADT、HPET 与 PCI hook <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/acpi/boot.c>`_
* `Linux 6.12.95 APIC apic.c：Local APIC 探测、fixmap 与 init_apic_mappings <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/apic.c>`_
* `Linux 6.12.95 topology.c：possible CPU 与 package/die/core/thread 统计 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/topology.c>`_
* `Linux 6.12.95 numa.c：init_cpu_to_node 与 Generic Initiator node <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/numa.c>`_
* `Linux 6.12.95 io_apic.c：IOAPIC resource、fixmap 与 GSI 范围 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/io_apic.c>`_
* `ACPI 6.5：FADT、MADT、HPET 与 SPCR <https://uefi.org/specs/ACPI/6.5/>`_
* `Intel MultiProcessor Specification 1.4 <https://www.intel.com/content/dam/support/us/en/documents/motherboards/desktop/sb/multiprocessorspec.pdf>`_