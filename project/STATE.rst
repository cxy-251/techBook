项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-042``。最新三章：

#. ``LK-BOOT-040``：Linux 怎样进入 start_kernel 并建立最早的通用内核状态？
#. ``LK-BOOT-041``：Linux setup_arch 怎样接管命令行并导入 E820 内存图？
#. ``LK-BOOT-042``：Linux 怎样修正 E820 并计算自己真正能管理的物理页？

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

第四十二章已经完成：

::

   setup_initial_init_mm()
   → configure NX support
   → parse early parameters
   → initialize DMI/hypervisor/TSC/ROM discovery
   → register kernel code/rodata/data/bss resources
   → verify kernel range is E820 RAM
   → reserve page 0 and remove 640 KiB–1 MiB from RAM
   → apply early GART and MTRR corrections
   → calculate max_pfn / max_possible_pfn / max_low_pfn
   → randomize large kernel virtual memory regions
   → find legacy MP table
   → immediately before early_alloc_pgt_buf()

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* 当前停点：``early_alloc_pgt_buf()`` 尚未调用；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* ``init_mm``：已登记 kernel code/data/brk 边界；
* NX：已反映到支持的 PTE mask；
* E820：已应用 early 参数、低端 BIOS 修正与 MTRR trim；
* kernel sections：已加入 ``iomem_resource``；
* ``max_pfn`` / ``max_possible_pfn`` / ``max_low_pfn``：已确定；
* memory layout randomization：已决定；
* ``memblock.memory``：尚未由 E820 RAM 建立；
* early page-table buffer：尚未分配；
*完整 direct map：尚未建立；
* initramfs：仍只被物理保留。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``arch/x86/mm/init.c:early_alloc_pgt_buf()`` 开始，追踪 brk 页表缓冲、``reserve_brk()``、``e820__memblock_setup()``、低 1 MiB real-mode 保留、``init_mem_mapping()`` 的页大小选择与 top-down/bottom-up 映射，停在 direct map 建立并更新 memblock 分配上限之后。