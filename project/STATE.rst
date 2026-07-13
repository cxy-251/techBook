项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-044``。最新三章：

#. ``LK-BOOT-042``：Linux 怎样修正 E820 并计算自己真正能管理的物理页？
#. ``LK-BOOT-043``：Linux 怎样把 E820 RAM 变成 memblock 并建立 early direct map？
#. ``LK-BOOT-044``：Linux 怎样扩大启动日志并确认 initramfs 与 ACPI 表可以安全访问？

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

第四十二至四十四章已经完成：

::

   setup_initial_init_mm()
   → configure NX and parse early parameters
   → initialize DMI / hypervisor / TSC / ROM discovery
   → register kernel resources
   → correct E820 low BIOS ranges and apply MTRR trim
   → calculate max_pfn / max_possible_pfn / max_low_pfn
   → early_alloc_pgt_buf()
   → reserve and close brk
   → e820__memblock_setup()
   → reserve low 1 MiB and real-mode trampoline
   → init_mem_mapping()
   → load swapper_pg_dir and flush TLB
   → replace early page-fault IDT
   → expand memblock current limit to get_max_mapped()
   → setup_log_buf(1)
   → migrate early printk records when a dynamic buffer is required
   → reserve_initrd() and establish initrd_start/initrd_end
   → conditionally relocate initramfs below max_pfn_mapped
   → scan conditional ACPI overrides in initrd
   → locate, validate and reserve initial ACPI tables

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* E820：已修正并转换为 memblock；
* early direct map：已建立，``CR3`` 使用 ``swapper_pg_dir``；
* printk ring buffer：若需要，已迁移到 memblock 动态缓冲；
* initramfs：物理区仍保留，``initrd_start`` / ``initrd_end`` 已建立，尚未展开；
* ACPI override：已完成条件扫描；
* ACPI 初始 table list：已建立；
* ACPI table 物理区：已保留；
* MADT/SRAT 早期拓扑解析：尚未完成；
* NUMA node：尚未建立；
* ``setup_arch()``：尚未返回。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``setup_arch():vsmp_init()`` 开始，追踪虚拟 SMP 与 I/O delay 条件路径、early platform quirks、``early_acpi_boot_init()`` 对 MADT 的早期处理、MP table fallback、``initmem_init()`` 和 NUMA node 建立。