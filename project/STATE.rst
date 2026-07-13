项目状态
========

最后更新
--------

2026-07-13

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-041``。最新三章：

#. ``LK-BOOT-039``：x86_64_start_kernel 怎样清理临时环境并保存启动数据？
#. ``LK-BOOT-040``：Linux 怎样进入 start_kernel 并建立最早的通用内核状态？
#. ``LK-BOOT-041``：Linux setup_arch 怎样接管命令行并导入 E820 内存图？

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

第四十一章已经完成：

::

   start_kernel()
   → setup_arch(&command_line)
   → resolve effective command line
   → install early traps and early ioremap
   → parse_boot_params()
   → reserve kernel image
   → reserve low 64 KiB
   → reserve initramfs physical range
   → reserve setup_data chain
   → reserve BIOS regions
   → e820__memory_setup()
   → parse_setup_data()
   → copy_edd()
   → immediately before setup_initial_init_mm()

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/setup.c:setup_arch()``；
* CPU：BSP / Linux CPU 0；
* mode：64 位 long mode；
* interrupts：关闭；
* 命令行：已接管；
* ``boot_params``：主要字段已翻译；
* kernel、低 64 KiB、initramfs、setup_data 与 BIOS ranges：已预留；
* 基础 E820：已从 ``boot_params`` 导入并 sanitize；
* 扩展 ``setup_data``：已解析；
* ``memblock.memory``：尚未由 E820 RAM 建立；
* ``max_pfn``：尚未计算；
* direct map：尚未重建；
* ``setup_arch()``：尚未返回；
* initramfs：尚未展开。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``setup_initial_init_mm()`` 开始，追踪 ``init_mm`` 边界、NX 与 early 参数、DMI/hypervisor/ROM 资源、kernel resource tree、E820 修正、MTRR trim、``max_pfn``、memory layout randomization 和 MPTABLE 查找，停在 ``early_alloc_pgt_buf()`` 前。