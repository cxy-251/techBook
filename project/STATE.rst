项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-045``。最新三章：

#. ``LK-BOOT-043``：Linux 怎样把 E820 RAM 变成 memblock 并建立 early direct map？
#. ``LK-BOOT-044``：Linux 怎样扩大启动日志并确认 initramfs 与 ACPI 表可以安全访问？
#. ``LK-BOOT-045``：Linux 怎样从 MADT、MP table 和 SRAT 建立 CPU 拓扑与 NUMA node？

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

第四十三至四十五章已经完成：

::

   e820__memblock_setup()
   → reserve low 1 MiB and real-mode trampoline
   → init_mem_mapping()
   → load swapper_pg_dir and flush TLB
   → expand memblock current limit
   → setup_log_buf(1)
   → reserve_initrd()
   → locate and reserve ACPI initial tables
   → vsmp_init() conditional path
   → configure I/O delay and early platform quirks
   → early_acpi_boot_init()
   → parse early MADT CPU/APIC topology
   → early MP table fallback
   → Device Tree conditional path
   → initmem_init()
   → ACPI SRAT / platform NUMA attempts
   → guarantee at least node 0
   → assign memblock RAM to NUMA nodes

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* initramfs：可通过 ``initrd_start`` / ``initrd_end`` 访问，尚未展开；
* ACPI initial table list：已建立并保留；
* MADT：已进行早期 CPU/APIC 拓扑处理；
* MP table：已完成 fallback 条件解析；
* possible CPU topology：已开始建立；
* AP：尚未唤醒；
* NUMA：已通过 SRAT/平台路径或 dummy fallback 建立；
* ``memblock.memory``：已带 node 归属；
* 有效 memory node：已分配 node data 并 online；
* zone/buddy allocator：尚未建立；
* KASAN 正式 shadow：尚未建立；
* ``setup_arch()``：尚未返回。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``setup_arch():dma_contiguous_reserve(max_pfn_mapped << PAGE_SHIFT)`` 开始，追踪 CMA/crashkernel 条件保留、early xHCI debug、``x86_init.paging.pagetable_init()`` 在 x86-64 上映射到 ``paging_init()``、KASAN shadow 接管与 ``sync_initial_page_table()``。