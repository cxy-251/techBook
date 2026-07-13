项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-050``。最新三章：

#. ``LK-BOOT-048``：Linux 怎样完成 ACPI、Local APIC、IOAPIC 与 possible CPU 拓扑？
#. ``LK-BOOT-049``：Linux 怎样登记物理资源并完成 setup_arch？
#. ``LK-BOOT-050``：Linux 怎样把 memblock 物理内存变成 node、zone 和 struct page？

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

第四十八至五十章已经完成：

::

   acpi_boot_init()
   → full FADT / MADT / HPET / SPCR parsing
   → Local APIC / IOAPIC mappings
   → possible CPU and CPU-to-node topology
   → E820 and standard I/O resource registration
   → wallclock backend / thermal LVT / MCE / unwind
   → return from setup_arch()
   → mm_core_init_early()
   → conditional HugeTLB CMA reservation
   → conditional gigantic HugeTLB boot allocation
   → arch_zone_limits_init()
   → sparse_init()
   → derive zone and movable PFN ranges
   → initialize pg_data_t and per-node zones
   → initialize struct page metadata and pageblock layout
   → set high_memory

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``mm_core_init_early()`` 已返回，``jump_label_init()`` 尚未调用；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* current task：``init_task``；
* interrupts：关闭，``early_boot_irqs_disabled = true``；
* NUMA ``pg_data_t``：已建立；
* zones：已按 x86 PFN 和 node 范围建立；
* sparse memory / vmemmap：已初始化；
* ``struct page``：已为可管理 PFN 建立和初始化；
* pageblock / zone ``free_area[]``：结构已建立；
* memblock：仍管理普通 RAM 与 reservation；
* zone ``managed_pages``：普通 RAM 尚未全部释放进 buddy；
* buddy allocator：基础结构存在，尚未接收全部可分配页；
* slab allocator：尚未建立；
* static key/static call：尚未完成运行时代码修补；
* early LSM：尚未初始化；
* bootconfig：尚未检查；
* per-CPU area：尚未建立；
* scheduler：尚未初始化；
* AP：尚未唤醒；
* initramfs：尚未解包。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``start_kernel():jump_label_init()`` 开始，追踪 static key 的 jump-table 修补、static call call-site 修补、early LSM hooks、initrd 尾部 bootconfig 检查，以及 ``saved_command_line`` / ``static_command_line`` 的 memblock 持久副本。