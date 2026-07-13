项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-046``。最新三章：

#. ``LK-BOOT-044``：Linux 怎样扩大启动日志并确认 initramfs 与 ACPI 表可以安全访问？
#. ``LK-BOOT-045``：Linux 怎样从 MADT、MP table 和 SRAT 建立 CPU 拓扑与 NUMA node？
#. ``LK-BOOT-046``：Linux 怎样完成 x86-64 paging 收尾并建立 KASAN shadow？

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

第四十四至四十六章已经完成：

::

   setup_log_buf(1)
   → migrate early printk records when needed
   → reserve_initrd() and establish initrd virtual range
   → scan conditional ACPI overrides
   → locate and reserve ACPI initial tables
   → vsmp_init() conditional path
   → configure I/O delay and early platform quirks
   → early_acpi_boot_init()
   → parse early MADT CPU/APIC topology
   → early MP table fallback
   → initmem_init()
   → assign memblock RAM to NUMA nodes
   → dma_contiguous_reserve() conditional CMA
   → arch_reserve_crashkernel() conditional path
   → early xDBC conditional console
   → x86_init.paging.pagetable_init()
   → native x86-64 paging_init()
   → conditional kasan_init()
   → sync_initial_page_table() (x86-64 no-op)

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* printk：动态 ring buffer 已按需建立；
* initramfs：可通过 ``initrd_start`` / ``initrd_end`` 访问，尚未展开；
* early ACPI CPU/APIC topology：已建立；
* NUMA：已保证至少一个 online memory node；
* memblock RAM：已带 node 归属；
* CMA：已按配置完成条件保留；
* crashkernel：固定命令行未请求；
* direct map：继续由 ``init_top_pgt`` / ``swapper_pg_dir`` 承载；
* native ``pagetable_init``：x86-64 实际调用短小的 ``paging_init()``，未重建 direct map；
* KASAN：若配置启用，正式 shadow 已建立；
* ``sync_initial_page_table()``：x86-64 为空操作；
* zone/buddy allocator：尚未建立；
* 完整 ACPI/FADT/HPET、APIC/IOAPIC 与资源注册：尚未完成；
* ``setup_arch()``：尚未返回。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``setup_arch():tboot_probe()`` 开始，追踪 Trusted Boot 条件路径、vsyscall 映射、完整 ``acpi_boot_init()``、local APIC/IOAPIC 映射、possible CPU 与 CPU-to-node 收尾、E820/resource 注册、wall clock、MCE、unwind，直到 ``setup_arch()`` 返回。