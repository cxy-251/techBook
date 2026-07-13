项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-043``。最新三章：

#. ``LK-BOOT-041``：Linux setup_arch 怎样接管命令行并导入 E820 内存图？
#. ``LK-BOOT-042``：Linux 怎样修正 E820 并计算自己真正能管理的物理页？
#. ``LK-BOOT-043``：Linux 怎样把 E820 RAM 变成 memblock 并建立 early direct map？

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

第四十一至四十三章已经完成：

::

   setup_arch(&command_line)
   → resolve command line and parse boot_params
   → reserve kernel / low memory / initramfs / setup_data / BIOS ranges
   → import base and extended E820
   → setup_initial_init_mm()
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

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* E820：已修正并转换为 memblock；
* ``memblock.memory``：已建立；
* kernel、initramfs、setup_data、BIOS 与 trampoline：已加入 reserved；
* 低 1 MiB：全部保留但保持 direct mapped；
* early brk allocator：已封存；
* early direct map：已建立；
* CR3：已加载 ``swapper_pg_dir``；
* ``max_pfn_mapped``：已更新；
* memblock current limit：已扩大到 ``get_max_mapped()``；
* real-mode trampoline：物理区已预留，内容尚未最终初始化；
* initramfs：尚未展开，尚未完成 ``reserve_initrd()`` 的映射确认；
* ACPI/NUMA/完整架构页表初始化：尚未完成；
* ``setup_arch()``：尚未返回。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``setup_arch():setup_log_buf(1)`` 开始，追踪扩大 printk ring buffer、``reserve_initrd()`` 的 direct-map 检查与条件重定位、ACPI table 保留和 early ACPI/NUMA 解析、``initmem_init()``、``x86_init.paging.pagetable_init()`` 与 KASAN 正式页表接管。