项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-047``。最新三章：

#. ``LK-BOOT-045``：Linux 怎样从 MADT、MP table 和 SRAT 建立 CPU 拓扑与 NUMA node？
#. ``LK-BOOT-046``：Linux 怎样完成 x86-64 paging 收尾并建立 KASAN shadow？
#. ``LK-BOOT-047``：Linux 怎样探测 tboot、映射 vsyscall 并在固件枚举前限制 CPU？

完整章节列表见 ``docs/tracks/linux-kernel/index.rst``，机器可读接续信息见 ``manifests/tracks/linux-kernel.toml``。

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 6.12.95

固定来源
--------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux release     = 6.12.95
   Linux source tag  = gregkh/linux v6.12.95
   Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d

当前控制流位置
--------------

第四十五至四十七章已经完成：

::

   initmem_init()
   → assign memblock RAM to NUMA nodes
   → dma_contiguous_reserve() conditional CMA
   → arch_reserve_crashkernel() conditional path
   → early xDBC conditional console
   → x86_init.paging.pagetable_init()
   → native x86-64 paging_init()
   → conditional kasan_init()
   → sync_initial_page_table() (x86-64 no-op)
   → tboot_probe()
   → map_vsyscall()
   → x86_32_probe_apic() architecture compatibility entry
   → early_quirks() direct PCI scan
   → topology_apply_cmdline_limits_early()

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* tboot：固定主线未检测到 measured-launch shared page；
* vsyscall：已按构建配置和命令行完成固定页/兼容模式设置；
* early PCI quirks：已扫描并应用匹配项；
* CPU 命令行上限：已在完整 firmware CPU enumeration 前生效；
* early MADT CPU/APIC topology：已存在；
* FADT/HPET/完整 MADT interrupt pass：尚未完成；
* Local APIC/IOAPIC 最终映射：尚未完成；
* AP：尚未唤醒；
* zone/buddy allocator：尚未建立；
* ``setup_arch()``：尚未返回。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``setup_arch():acpi_boot_init()`` 开始，追踪 FADT、MADT、HPET、SPCR 与 PCI ACPI hook，随后执行 MP table fallback、Local APIC 映射、possible CPU 初始化、CPU-to-node 收尾和 IOAPIC 映射。