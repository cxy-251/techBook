第四十八章：Linux 怎样 full-parse MADT 并建立 possible CPU 与 IOAPIC 映射？
============================================================================

第四十七章结束时，CPU0仍在 ``setup_arch``、IF=0；early PCI quirks与CPU capacity limits已经生效。
045只从MADT header登记了Local APIC physical address，没有枚举processor或IOAPIC entries。当前
入口是：

.. code-block:: c

   acpi_boot_init();

本章按fixed Linux 7.2-rc1继续到 ``x86_init.hyper.guest_late_init()`` 返回。成功ACPI路径在这里才
首次把QEMU生成的MADT Local APIC/x2APIC processor records送入topology registry，再登记IOAPIC、
interrupt overrides与NMI；MP parser随后只在ACPI缺失/部分成功时补足。最后Linux冻结possible/
present CPU集合、接回NUMA affinity并建立IOAPIC fixmaps，但仍不唤醒AP或打开普通device IRQ。

late ACPI DMI quirks必须在early PCI quirks之后
----------------------------------------------

``acpi_boot_init`` 先执行 ``dmi_check_system(acpi_dmi_table_late)``。这组machine-specific policy包含
例如ignore timer override之类必须在047 chipset scan后决定的修正。fixed QEMU/SeaBIOS DMI不匹配
这些旧实体机条目，ordinary路径保持table原义；正文仍按actual DMI match保留branch。

若此前config/effective ``acpi=off``、blacklist或table locate failure已令 ``acpi_disabled`` 为真，
函数立即返回1，不执行本章ACPI handlers。后面的full MP parser仍可使用042找到并reserved的MPS
tables；但是否编入MPS及表是否有效仍是条件。

BOOT table被再次解析，FADT handler只落实x86当前所需字段
-------------------------------------------------------

enabled路径先再次解析optional BOOT table的simple-boot flag，再把ACPICA已经规范化的FADT交给
``acpi_parse_fadt``。fixed x86 handler根据FADT boot flags更新：

* legacy devices/PNPBIOS是否存在；
* i8042是否由firmware声明缺席；
* RTC与VGA probe是否允许；
* ``CONFIG_X86_PM_TIMER`` 下的ACPI PM timer I/O port。

SCI number等canonical FADT内容已经位于 ``acpi_gbl_FADT``，稍后的MADT IOAPIC parser会读取
``sci_interrupt`` 来建立/补SCI route。此时只登记platform facts与timer address，不选择最终
clocksource、不创建ACPI namespace device，也不执行AML methods。

full MADT pass现在才枚举Local APIC/x2APIC processor entries
---------------------------------------------------------

``acpi_process_madt`` 先再次解析MADT header，取得default LAPIC address与PCAT compatibility。045已
完成可选64-bit LAPIC Address Override scan并调用 ``register_lapic_address``；本次full helper的
新增工作从 ``acpi_parse_madt_lapic_entries`` 开始。

它先尝试Local SAPIC entries；普通q35没有时，先检查Local APIC records是否包含usable processor，
再用一个combined processor array按MADT出现顺序同时扫描：

.. code-block:: text

   ACPI_MADT_TYPE_LOCAL_APIC
   ACPI_MADT_TYPE_LOCAL_X2APIC

handler验证record，忽略invalid APIC ID与不可online processor，把usable entry交给
``topology_register_apic(apic_id, acpi_uid, enabled)``。disabled但online-capable的entry也可登记，
以便CPU hotplug/possible mask只为firmware实际描述的capacity分配，而非机械使用全部 ``NR_CPUS``。

fixed QEMU q35 MADT builder按 ``possible_cpu_arch_ids`` 写Local APIC或x2APIC processor records；具体
CPU数、APIC ID宽度与disabled hotplug slots取决于未固定QEMU SMP/CPU CLI，所以本章不制造数字。
但与045不同，成功路径到这里确实第一次拥有firmware processor registry。

Local APIC NMI与processor enumeration同一helper完成
----------------------------------------------------

至少有一个Local APIC/x2APIC processor entry后，源码继续解析Local x2APIC NMI与Local APIC NMI
records，验证LINT通常连接到1。它登记firmware NMI wiring facts，但尚未安装每CPU NMI runtime
state或启动AP。

若processor entry parse成功， ``acpi_lapic=1``；若MADT malformed返回 ``-EINVAL``，fixed error
path会禁用ACPI。没有MADT时还有更特殊的边界：ACPI enabled却找不到APIC table会把先前
``smp_found_config`` 清0，并提示必须用 ``acpi=off`` 才允许MPS接管，而不是无条件把两套firmware
描述混合。

IOAPIC parse受ACPI IRQ、APIC feature与 ``noapic`` 三重guard
----------------------------------------------------------

Local processor pass成功后， ``acpi_parse_madt_ioapic_entries`` 只有在以下条件全部满足时继续：

.. code-block:: text

   ACPI enabled and acpi_noirq false
   boot CPU has APIC feature
   ioapic_is_disabled false

它先解析 ``ACPI_MADT_TYPE_IO_APIC``，由每条record登记IOAPIC ID、physical MMIO base与GSI base；没有
entry或parse error时返回失败。fixed QEMU q35 MADT builder提供至少一个PC IOAPIC entry，ordinary
successful path继续。

source override、SCI、legacy identity与NMI source顺序不能颠倒
----------------------------------------------------------

IOAPIC存在后，源码按顺序：

#. 解析 ``INTERRUPT_OVERRIDE``，把legacy source IRQ改到指定GSI，并记录polarity/trigger；
#. 若FADT SCI尚无override且不是hardware-reduced ACPI，用FADT ``sci_interrupt`` 合成SCI setup；
#. 为未被override占用的legacy IRQ补identity route；
#. 解析MADT ``NMI_SOURCE`` entries。

这些步骤建立的是early ``mp_irqs``/GSI route model。成功后 ``acpi_set_irq_model_ioapic`` 选择
``ACPI_IRQ_MODEL_IOAPIC``、安装GSI register/unregister callbacks并设置 ``acpi_ioapic=1``；随后
``smp_found_config=1``。可选 ``CONFIG_ACPI_MADT_WAKEUP`` 还解析一个multiprocessor wakeup mailbox。

外部interrupt仍未enable：没有为设备分配runtime vector、写最终redirection affinity或打开CPU
IF。这里是configuration discovery，不是IRQ delivery开始。

HPET、BGRT、PCI hook与SPCR保持独立条件
--------------------------------------

MADT后 ``acpi_boot_init`` 还依次：

* 按 ``CONFIG_HPET_TIMER`` 等条件解析HPET table，记录MMIO resource/capability；047 quirk可先禁用
  不可靠platform；
* 仅在 ``CONFIG_ACPI_BGRT`` 且没有 ``bgrt_disable`` 时解析BGRT boot graphic；
* ``acpi_noirq==false`` 时把未来PCI init hook改为 ``pci_acpi_init``；这只选择later path，不枚举PCI；
* 调用 ``acpi_parse_spcr(earlycon_acpi_spcr_enable,acpi_spcr_add)``，在build/table/option支持时处理
  firmware UART并可设置early/preferred console。

fixed command line已有 ``console=ttyS0``，但没有 ``earlycon`` 或 ``acpi=spcr``；这不等于SeaBIOS必须
有SPCR，也不把SPCR call写成必然新增console。BGRT在BIOS q35也保持table-present条件。

full MP parser只补ACPI没有覆盖的部分
------------------------------------

``acpi_boot_init`` 返回后，ordinary PC调用 ``mpparse_parse_smp_config``。它先要求早先确实找到
``smp_found_config`` 与 ``mpf_found``；若ACPI已经同时得到LAPIC和IOAPIC，立即返回，fixed normal q35
不会重复登记一套MPS topology。

若ACPI只有LAPIC而IOAPIC失败，full MP parser可验证并遍历MP configuration blocks，但遇
``MP_PROCESSOR`` 时因 ``acpi_lapic`` 已真而跳过processor registration，只补bus/IOAPIC/interrupt
data。若ACPI完全禁用且MPS有效，则MPS可登记processor与I/O configuration。MPS不支持
Hyper-Threading的完整logical描述，所以它不是与MADT等价的双写来源。

Local APIC MMIO fixmap通常已在045建立
--------------------------------------

``init_apic_mappings`` 的名字容易让人把Local APIC mapping错误推迟到048。实际
``register_lapic_address`` 在045 early MADT成功时已经调用 ``apic_set_fixmap``：非x2APIC把
``mp_lapic_addr`` 映射到uncached ``FIX_APIC_BASE`` 并读取boot CPU APIC ID；x2APIC使用MSR interface
不需要MMIO fixmap。

本次“last opportunity”函数先验证TSC deadline timer。x2APIC mode随后返回；若尚无
``smp_found_config``，才按vendor/family/APIC feature、 ``nolapic/lapic`` policy与default APIC base
做最后detect，失败则 ``apic_disable``。它不是在successful q35路径重新映射一次MADT LAPIC。

``topology_init_possible_cpus`` 把temporary registry冻结成masks
-------------------------------------------------------------

full ACPI/MP parser已把enabled/disabled APIC identities放入 ``topo_info`` 与bitmaps。函数若连boot
APIC都没有，先注册一个synthetic APIC ID 0，只保证通用topology query结构可用，不会重新启用被
禁用的APIC。

若有SMP config且APIC有效，它以 ``assigned+disabled`` 与047已经收紧的 ``nr_cpu_ids`` 取allowed；
否则ordinary非Xen PV限制为UP。随后更新assigned/disabled counts、 ``total_cpus`` 与最终
``nr_cpu_ids``，计算package/node/die/core/thread capacity。

最后它先把present/possible masks重置到CPU0，再给可接受的disabled APIC identities分配logical
IDs；遍历 ``[0,allowed)`` 时逐一设置possible，只有APIC ID位于 ``phys_cpu_present_map`` 才设置
present。此时possible CPU可能尚未present，present CPU也尚未online；仍只有CPU0 online/active。

``init_cpu_to_node`` 现在才把logical CPU接到SRAT affinity
---------------------------------------------------------

045已经可以从SRAT保存 ``APIC ID→node``，但当时logical CPU registry尚未完成。现在
``init_cpu_to_node`` 遍历possible CPUs，用early ``x86_cpu_to_apicid`` 查
``__apicid_to_node``；有有效nid时先确保CPU-only/memoryless node online，再写early
``x86_cpu_to_node_map``。

dummy/fake NUMA场景没有准确APIC affinity时，045的 ``numa_init_array`` round-robin fallback继续
保留，不在这里伪造SRAT。 ``init_gi_nodes`` 随后把只有Generic Initiator、没有CPU/RAM而尚未online
的nodes标online，使later zonelist/node-data阶段不丢其affinity identity。fixed ordinary q35是否
有SRAT/GI nodes仍取决于QEMU NUMA CLI。

IOAPIC resources先分配描述，再建立uncached fixmaps
---------------------------------------------------

``io_apic_init_mappings`` 先按 ``nr_ioapics`` 用memblock分配一组 ``struct resource`` 与名称
``IOAPIC n``，标 ``IORESOURCE_MEM|IORESOURCE_BUSY``。这里仅准备resource objects；ordinary
``x86_init.resources.reserve_resources`` 在049只登记standard I/O ports，IOAPIC resources要到later
``pcibios_resource_survey()`` 调用 ``ioapic_insert_resources`` 才进入 ``iomem_resource`` tree，不能
提前记成已发布。

每个已登记IOAPIC在 ``smp_found_config`` 路径取firmware physical address，映射到从
``FIX_IO_APIC_BASE_0`` 起的连续fixmap slots，normal protection是nocache。encrypted guest还通过
``is_private_mmio`` 决定encrypted/decrypted pgprot。若没有IOAPIC，resource setup返回NULL且loop
为空；若已有 ``nr_ioapics`` 却没有 ``smp_found_config``，fallback会为每项从memblock分配fake
PAGE_SIZE physical page，而不是使用firmware MMIO address。

mapping只令kernel可访问IOAPIC registers，尚未完成runtime IRQ domain/vector allocation、最终
redirection table programming或unmask device pins。

guest late hook取决于实际hypervisor detection
----------------------------------------------

最后 ``x86_init.hyper.guest_late_init`` 在native table中是 ``x86_init_noop``；KVM、Hyper-V、Xen等
early detection可以替换它。fixed QEMU accelerator没有指定，故不能把QEMU等同于KVM，也不能断言
hook必为空；它在topology/NUMA/APIC identity完成后做相应guest late setup。

本章结束状态
------------

* current executor：CPU0上的 ``setup_arch``，下一条是 ``e820__reserve_resources()``；
* CPU/mode：BSP/logical CPU0，x86-64 long mode，IF=0，无schedule/AP bring-up；
* ACPI FADT：enabled路径已应用legacy/i8042/RTC/VGA/PM-timer facts；
* MADT processor registry：成功路径已首次枚举Local APIC/x2APIC usable entries；
* ACPI IOAPIC model：normal q35路径已登记IOAPIC/GSI overrides/SCI/legacy/NMI routes；
* HPET/BGRT/SPCR：按build、table与effective options解析或no-op；
* future PCI hook： ``acpi_noirq==false`` 时选择 ``pci_acpi_init``；尚未枚举PCI；
* MP table：ACPI LAPIC+IOAPIC成功时skip；partial/disabled ACPI时按实际fallback补足；
* Local APIC：normal path已从045持有address/fixmap或x2APIC MSR mode；last-opportunity check完成；
* final ``nr_cpu_ids``：按firmware registry与047 capacity得出，具体值未固定；
* CPU masks：allowed logical IDs已possible，actual firmware-present IDs已present；仅CPU0 online/active；
* CPU-to-node：有效SRAT affinity已接到logical IDs；fallback mapping保留；
* Generic Initiator nodes：存在时已online；
* IOAPIC：resource objects已准备、MMIO fixmaps已建；resources尚未插入tree；
* device IRQ：未分配最终vector/unmask，CPU IF仍为0；
* guest late hook：按actual detected environment执行或no-op。

关键边界
--------

#. 045只登记LAPIC address；048 full MADT才首次枚举processor records。
#. FADT x86 handler落实legacy flags与PM timer；SCI route在MADT IOAPIC阶段使用canonical FADT字段。
#. ACPI enabled但没有MADT会清MPS discovery；只有明确 ``acpi=off`` 才走纯MPS takeover语义。
#. full MADT processor、IOAPIC、source override、SCI fallback与NMI是有序的不同passes。
#. 设置 ``acpi_ioapic/smp_found_config`` 表示configuration有效，不表示device interrupts已打开。
#. full MP parser在ACPI LAPIC+IOAPIC齐全时skip；ACPI LAPIC-only时不会重复登记processors。
#. Local APIC non-x2APIC fixmap通常在045 ``register_lapic_address`` 时已建立，不由048重建。
#. possible、present、online与active masks在topology finalize后仍不能互换。
#. disabled firmware CPU可获得possible logical ID，但不因此present/online。
#. SRAT APIC affinity在045保存，直到possible logical IDs确定后才由 ``init_cpu_to_node`` 接回。
#. IOAPIC resource object、fixmap mapping、later PCI-survey resource-tree insertion与runtime IRQ
   programming是四个边界；049的standard-I/O reservation不插入IOAPIC资源。
#. QEMU不自动等于KVM；guest late hook按actual hypervisor detection决定。

下一入口
--------

第049章从：

.. code-block:: c

   e820__reserve_resources();

开始。进入前E820/memblock/direct-map identities已经存在，CPU/APIC topology也已finalize；但E820与
IOAPIC resources尚未完成本阶段的resource-tree发布， ``setup_arch`` 仍未返回。

资料
----

* `Linux 7.2-rc1固定提交：full ACPI到guest-late调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L1225-L1244>`_；
* `Linux 7.2-rc1固定提交：acpi_boot_init的BOOT/FADT/MADT/HPET/BGRT/PCI/SPCR顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/acpi/boot.c#L1643-L1676>`_；
* `Linux 7.2-rc1固定提交：full MADT processor与IOAPIC passes <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/acpi/boot.c#L1030-L1344>`_；
* `QEMU固定提交：q35 MADT processor、IOAPIC与source-override生成 <https://gitlab.com/qemu-project/qemu/-/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/acpi-common.c#L35-L145>`_；
* `Linux 7.2-rc1固定提交：MP full parser与ACPI complement guards <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/mpparse.c#L477-L550>`_；
* `Linux 7.2-rc1固定提交：Local APIC last-opportunity detection与early fixmap <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/apic.c#L2010-L2102>`_；
* `Linux 7.2-rc1固定提交：possible/present CPU topology finalize <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/topology.c#L435-L552>`_；
* `Linux 7.2-rc1固定提交：logical CPU接回NUMA与Generic Initiator nodes <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/numa.c#L254-L325>`_；
* `Linux 7.2-rc1固定提交：IOAPIC resource allocation与fixmap <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/apic/io_apic.c#L2494-L2585>`_。
