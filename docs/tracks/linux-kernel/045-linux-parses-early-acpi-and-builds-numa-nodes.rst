第四十五章：Linux 怎样登记 LAPIC 地址并给 memblock RAM 建立 NUMA node？
=======================================================================

第四十四章结束时，CPU0仍在 ``setup_arch``、IF=0；initramfs已经有可持续访问的
``initrd_start/end``，ACPI initial table list也在成功SeaBIOS路径中完成定位与reservation。当前
入口是：

.. code-block:: c

   vsmp_init();

本章按fixed Linux 7.2-rc1继续到 ``initmem_init()`` 返回。途中early ACPI/MP阶段只把Local APIC
physical address准备到足以进行NUMA解析的程度；它不会枚举MADT processor entries或建立完整CPU
topology。 ``initmem_init`` 随后给 ``memblock.memory`` ranges建立NUMA node identity，为下一章的
reserved-memory与paging收尾提供拓扑基础。

q35不会进入ScaleMP vSMP控制路径
---------------------------------

``vsmp_init`` 先通过early direct PCI config读取 ``00:1f.0`` vendor/device，只有命中ScaleMP
vSMP controller才设置 ``is_vsmp``。若early PCI access不可用或ID不匹配， ``is_vsmp_box`` 为false
并立即返回。

fixed q35的 ``00:1f.0`` 是ICH9 LPC function，不是ScaleMP device，所以不会：

* 从vSMP topology register限制 ``setup_max_cpus``；
* 映射vSMP control BAR并设置magic control bits；
* 因vSMP interrupt steering关闭用户IRQ affinity修改。

这次检测也不枚举PCI bus；它只在普通PCI core初始化前用固定config mechanism识别一个专用平台。

``io_delay_init`` 只在没有override时查DMI quirk
------------------------------------------------

``io_delay_type`` 的初值由build在 ``0x80``、 ``0xed``、 ``udelay(2)`` 与 ``none`` 四种策略中选择，
early ``io_delay=`` 又可覆盖它并设置 ``io_delay_override=1``。 ``io_delay_init`` 自身只执行：

.. code-block:: c

   if (!io_delay_override)
       dmi_check_system(io_delay_0xed_port_dmi_table);

table只列出几台向port ``0x80`` 写入会出问题的旧Quanta/HP/Compaq机器，且callback只在当前类型为
``0x80`` 时改到 ``0xed``。fixed QEMU/SeaBIOS DMI不匹配这些实体机条目；若builtin command line没有
未知override，结果就保持build default。本次call不执行I/O calibration，也不等待2微秒。

``early_platform_quirks`` 在fixed source只识别Apple
-----------------------------------------------------

旧叙事容易把这个名字扩张成一组早期PCI、HPET、IOMMU或timer workaround；fixed 7.2-rc1函数实际
只有：

.. code-block:: c

   x86_apple_machine =
       dmi_match(DMI_SYS_VENDOR, "Apple Inc.") ||
       dmi_match(DMI_SYS_VENDOR, "Apple Computer, Inc.");

因此fixed q35结果为false。其他PCI fixups与platform quirks各有后续入口，不能记到这次call名下。

early ACPI先完成table manager与blacklist决定
---------------------------------------------

``early_acpi_boot_init`` 若第四十四章已令 ``acpi_disabled`` 为真，立刻返回1。有效ACPI路径先调用
``acpi_table_init_complete``，再解析可选BOOT table的simple-boot flag。随后第二次blacklist检查
可能因table内容禁用ACPI；只有 ``acpi=force`` 才覆盖这一决定。

这里仍是early table access，不创建ACPICA namespace、不执行DSDT/SSDT AML，也不枚举ACPI device。
函数继续调用 ``early_acpi_process_madt`` 的目的，是在NUMA source parsing前先登记Local APIC基址。

early MADT pass不枚举processor entries
----------------------------------------

``early_acpi_process_madt`` 先通过 ``acpi_table_parse(ACPI_SIG_MADT, acpi_parse_madt)`` 读取MADT
header。 ``acpi_parse_madt`` 要求boot CPU具备APIC feature，然后取得header内32-bit LAPIC address；
若 ``PCAT_COMPAT`` flag存在，还记录legacy PIC compatibility。

接着 ``early_acpi_parse_madt_lapic_addr_ovr`` 只扫描
``ACPI_MADT_TYPE_LOCAL_APIC_OVERRIDE`` entries，用可选64-bit地址覆盖header值，并调用：

.. code-block:: c

   register_lapic_address(acpi_lapic_addr);

fixed helper把 ``acpi_table_parse_madt`` 的返回值直接放进 ``error``：返回0（没有address-override
entry且无错误）时才设置 ``acpi_lapic=1`` 与 ``smp_found_config=1``； ``-EINVAL`` 则把MADT视为
无效并禁用ACPI；正数表示实际处理了override entry，address虽已登记，却不进入这两个condition。
fixed QEMU q35 MADT builder写header默认LAPIC地址以及CPU/IOAPIC等entries，不生成Local APIC Address
Override entry，因此本场景的正常结果是返回0并设置两个flags。

这个early helper没有调用 ``acpi_parse_madt_lapic_entries``，所以没有遍历Local APIC/x2APIC
processor records，没有登记ACPI UID、enabled/online-capable CPU，也没有解析IOAPIC、interrupt
source override或NMI source。那些工作属于后面的 ``acpi_boot_init``。本章只能说“LAPIC地址可用”，
不能说“possible CPU topology已由MADT建立”。

hardware-reduced ACPI只在FADT flag成立时改platform hooks
---------------------------------------------------------

``acpi_reduced_hw_init`` 检查 ``acpi_gbl_reduced_hardware``。若成立，x86 early hook会跳过legacy PIC
与传统timer/pre-vector assumptions；普通PC-compatible q35/SeaBIOS不预期设置该模式，因此保持
ordinary hooks。无论哪条branch，都没有在这里启动timer或打开interrupt。

early MP parser也只到LAPIC address边界
--------------------------------------

下一条 ``x86_init.mpparse.early_parse_smp_cfg`` 在ordinary PC指向
``mpparse_parse_early_smp_config``。第043章前面的 ``find_mptable`` 已可能找到并reserve MP floating
pointer/config table；现在helper根据状态分支：

* 没有 ``smp_found_config`` 或 ``mpf_found``，直接返回；
* early ACPI已经设置 ``acpi_lapic``，直接返回，不让MP table覆盖其选择；
* 仅在没有ACPI LAPIC时，映射MP table、检查signature/version/checksum/LAPIC address，并注册该
  LAPIC基址。

即便进入第三条， ``smp_read_mpc(...,early=true)`` 也在 ``register_lapic_address`` 后返回，不遍历
``MP_PROCESSOR/MP_IOAPIC/MP_INTSRC`` blocks。若MP floating pointer使用default configuration，early
path同样只注册default LAPIC address。full MP configuration parser是后续另一次call。

fixed QEMU/SeaBIOS成功MADT路径已经令 ``acpi_lapic=1``，所以本次early MP parser在guard处返回；
fallback路径也不能被描述成已枚举CPU。

setup_data为空，所以没有x86 flattened DT输入
----------------------------------------------

``x86_flattree_get_config`` 只在 ``CONFIG_OF_EARLY_FLATTREE`` build中包含实际代码。若
``initial_dtb`` 非0，它先early-map header、读取total size、映射完整FDT并验证，然后
``unflatten_and_copy_device_tree``；只有ACPI disabled且最终确有populated DT，才把后续full SMP
parser hook替换为 ``x86_dtb_parse_smp_config``。

第042章已从fixed boot params确认 ``setup_data=0``，因而 ``add_dtb`` 从未设置
``initial_dtb``。本次没有DT bytes可映射；即便build包含OF，unflatten也不会凭空生成tree，更不会
在当前call执行 ``dtb_cpu_setup``。DT的CPU/APIC parsing仍留给被选择后的later full hook。

``initmem_init`` 在x86-64只进入NUMA初始化
-------------------------------------------

x86-64 implementation是：

.. code-block:: c

   void __init initmem_init(void)
   {
       x86_numa_init();
   }

它不重建direct map，不创建zones，也不启动buddy allocator。若kernel未编入 ``CONFIG_NUMA``，inline
``x86_numa_init`` 直接把所有 ``memblock.memory`` 标成node 0。这是最小单node结果。

编入NUMA时先清旧node identity再试多个source
----------------------------------------------

真正的 ``x86_numa_init`` 在没有 ``numa=off`` 时按顺序尝试：

.. code-block:: text

   ACPI SRAT（CONFIG_ACPI_NUMA）
   → AMD northbridge NUMA（CONFIG_AMD_NUMA）
   → Device Tree NUMA（只在ACPI disabled时）
   → dummy node 0 fallback

每个候选都通过 ``numa_init``/``numa_memblks_init`` 事务化建立：先清parsed/possible/online node
masks，把 ``memblock.memory`` 与 ``memblock.reserved`` 的nid重置为 ``NUMA_NO_NODE``，清hotplug flag
并重置distance；source失败就由下一候选重新开始，不保留半套node identity。

成功source经过memory-block cleanup与可能的NUMA emulation后，由 ``numa_register_meminfo`` 把每个
``numa_memblk`` range用 ``memblock_set_node`` 写回actual memory regions。它还沿node boundary给
reserved ranges设置nid，并保证含kernel-reserved memory的node不被当作可整体hot-unplug。

SRAT提供affinity，但仍不是MADT CPU enumeration
-----------------------------------------------

ACPI NUMA source解析SRAT的processor/x2APIC affinity、generic initiator与memory affinity，另解析
SLIT distance；有CXL ACPI build时还可在SRAT后处理CEDT fixed memory windows。processor affinity把
``APIC ID → node`` 写入早期表，memory affinity把physical ranges归入proximity domain/node。

这与early MADT边界不冲突：SRAT可以先保存某个APIC ID的node affinity，但本章仍未从MADT创建
possible logical CPU列表，也没有把AP唤醒。E820/memblock回答“哪些地址是RAM且能否分配”，SRAT
回答“这些RAM/APIC identities靠近哪个node”，二者职责不同。

fixed QEMU command line没有固定 ``-numa`` topology，也没有固定kernel config，所以不能写死SRAT
存在或node数量。有效SRAT就采用其ranges；没有可接受SRAT时继续AMD/OF或dummy fallback。

dummy fallback先覆盖0到 ``max_pfn``，再与actual RAM对齐
------------------------------------------------------

``dummy_numa_init`` 是不可失败的最后source。它设置node 0并加入：

.. code-block:: text

   [0, PFN_PHYS(max_pfn)) → node 0

随后通用cleanup/register流程把这个拓扑范围应用到实际 ``memblock.memory``，并不会把E820 holes
变成RAM。 ``numa=off`` 也走同一dummy representation：通用MM仍得到一个node，而不是另造一套UMA
allocator。

node online与CPU-to-node兜底在zones之前完成
---------------------------------------------

``numa_register_nodes`` 先要求NUMA blocks在1 MiB容差内覆盖memblock RAM。对
``node_possible_map`` 中每个有有效PFN range的node，它分配node data并设置online；无memory的
CPU-only node可留在possible mask，由更后阶段按CPU信息处理。

接着源码清理由source留下、但对应node并未online的CPU mapping。 ``numa_init_array`` 对仍为
``NUMA_NO_NODE`` 的logical CPU indices，按现有online nodes round-robin填早期
``x86_cpu_to_node_map``。这是防止固件affinity不全的兜底，不是证明这些CPU已被MADT发现或已经
online。

本章到此仅建立 ``pg_data_t`` 等node根对象所需的早期基础。zone boundaries、page structs、KASAN
shadow收尾与buddy free lists仍在后面的paging/memory-init阶段。

本章结束状态
------------

* current executor：CPU0上的 ``setup_arch``，下一条是
  ``dma_contiguous_reserve(max_pfn_mapped<<PAGE_SHIFT)``；
* CPU/mode：BSP/logical CPU0，x86-64 long mode，IF=0，无schedule、无INIT/SIPI；
* vSMP：q35 device ID不匹配，未限制CPU数或写vSMP control；
* I/O delay：effective early override或build default保留；q35未命中列出的port-0x80 DMI quirks；
* ``x86_apple_machine``：false；本次platform quirk没有修改HPET/IOMMU/timer；
* ACPI：成功路径已完成table manager early phase与BOOT/blacklist检查；禁用路径保持disabled；
* LAPIC address：有效early MADT路径已从header/override登记；fallback可由early MP table登记；
* MADT/MP processor与IOAPIC entries：尚未由本章early pass枚举；
* ``acpi_lapic/smp_found_config``：fixed q35的无address-override MADT pass设置；无效/禁用路径不伪造；
* flattened DT： ``initial_dtb=0``，没有populated tree或DT SMP parse；
* ``memblock.memory`` node identity：按CONFIG_NUMA/source结果建立，至少有dummy node 0 fallback；
* SRAT affinity：若有效可记录APIC-to-node与memory-node关系；actual node数未固定；
* node objects：有memory range的nodes已分配early node data并online；
* CPU topology/AP online state：仍未完整建立，当前仅CPU0运行；
* zones/buddy allocator：尚未初始化。

关键边界
--------

#. ``vsmp_init`` 是单一ScaleMP探测，不是通用CPU topology入口。
#. fixed ``early_platform_quirks`` 只设置Apple布尔值，不能承载旧稿中的PCI/HPET/IOMMU claims。
#. early MADT只处理header LAPIC地址与address override，不遍历processor、IOAPIC或IRQ entries。
#. fixed q35 MADT没有Local APIC Address Override entry，helper返回0后才设置
   ``acpi_lapic/smp_found_config``；这仍不表示AP已经枚举或在线。
#. early MP parser在ACPI LAPIC有效时直接返回；fallback也只验证表并登记LAPIC address。
#. ``initial_dtb=0`` 来自fixed ``setup_data=0``；本章不会凭空生成DT topology。
#. SRAT APIC affinity与MADT processor enumeration是两份不同信息，前者不能替代后者。
#. NUMA source失败按ACPI→AMD→条件OF→dummy回退；dummy node不把physical holes变成RAM。
#. ``memblock_set_node`` 改的是现有memory/reserved range的nid，不改变其RAM/reserved身份。
#. node online、CPU online和memory page可由buddy分配是三个不同阶段。
#. ``numa_init_array`` 填缺失CPU-to-node映射，不证明相应logical CPU已发现或启动。
#. 045出口只完成NUMA早期归属；046才从CMA/crashkernel等reservation继续。

下一入口
--------

第046章从：

.. code-block:: c

   dma_contiguous_reserve(max_pfn_mapped << PAGE_SHIFT);

开始。进入前 ``memblock.memory`` 已有node identity，direct-map frontier仍是
``max_pfn_mapped``；MADT processor/IOAPIC full parse尚未发生，zones和buddy allocator也尚未建立。

资料
----

* `Linux 7.2-rc1固定提交：setup_arch early platform到initmem调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup.c#L1179-L1192>`_；
* `Linux 7.2-rc1固定提交：ScaleMP探测与控制边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/vsmp_64.c#L27-L141>`_；
* `Linux 7.2-rc1固定提交：I/O delay early override与DMI fallback <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/io_delay.c#L16-L153>`_；
* `Linux 7.2-rc1固定提交：early_platform_quirks实际Apple判断 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/quirks.c#L664-L672>`_；
* `Linux 7.2-rc1固定提交：early MADT仅处理LAPIC address override <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/acpi/boot.c#L1256-L1279>`_；
* `QEMU固定提交：q35 MADT header与entries不生成LAPIC address override <https://gitlab.com/qemu-project/qemu/-/blob/a759542a2c62f0fd3b65f5a66ad9868201014669/hw/i386/acpi-common.c#L95-L145>`_；
* `Linux 7.2-rc1固定提交：early ACPI BOOT/blacklist/reduced-hardware顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/acpi/boot.c#L1608-L1641>`_；
* `Linux 7.2-rc1固定提交：early MP parser不遍历configuration blocks <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/mpparse.c#L425-L550>`_；
* `Linux 7.2-rc1固定提交：x86 flattened-DT conditional入口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/devicetree.c#L339-L366>`_；
* `Linux 7.2-rc1固定提交：x86 NUMA source顺序、node登记与dummy fallback <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/numa.c#L128-L254>`_；
* `Linux 7.2-rc1固定提交：NUMA memory ranges写回memblock node identity <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/numa_memblks.c#L403-L473>`_。
