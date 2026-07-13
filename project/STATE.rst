项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-048``。最新三章：

#. ``LK-BOOT-046``：Linux 怎样完成 x86-64 paging 收尾并建立 KASAN shadow？
#. ``LK-BOOT-047``：Linux 怎样探测 tboot、映射 vsyscall 并在固件枚举前限制 CPU？
#. ``LK-BOOT-048``：Linux 怎样完成 ACPI、Local APIC、IOAPIC 与 possible CPU 拓扑？

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

第四十六至四十八章已经完成：

::

   x86_init.paging.pagetable_init()
   → native x86-64 paging_init()
   → conditional kasan_init()
   → tboot_probe()
   → map_vsyscall()
   → early_quirks()
   → topology_apply_cmdline_limits_early()
   → acpi_boot_init()
   → parse FADT / full MADT / HPET / BGRT / SPCR
   → select pci_acpi_init when ACPI IRQ routing is enabled
   → MP table fallback parse
   → init_apic_mappings()
   → topology_init_possible_cpus()
   → init_cpu_to_node()
   → init_gi_nodes()
   → io_apic_init_mappings()
   → x86_init.hyper.guest_late_init()

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：全局关闭；
* FADT：SCI、PM timer 等启动信息已解析；
* MADT：Local APIC、IOAPIC、GSI override 与 NMI 信息已处理；
* Local APIC：已确认，非 x2APIC 模式下已有 fixmap；
* IOAPIC：MMIO 已映射，redirection table 尚未正式启用；
* possible CPU 数量与 package/die/core/thread 拓扑：已最终确定；
* CPU-to-node：已建立；
* AP：尚未唤醒；
* 普通设备 IRQ：尚未开放；
* E820/resource tree：尚未完成注册；
* wall clock/MCE/unwind：尚未初始化；
* ``setup_arch()``：尚未返回。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``setup_arch():e820__reserve_resources()`` 开始，追踪 E820 与标准 PC resource tree、nosave regions、IOAPIC resource、PCI gap、VGA console 条件登记、wall clock、thermal LVT、machine check、refined jiffies、EFI quirk 和 unwind，直到 ``setup_arch()`` 返回。