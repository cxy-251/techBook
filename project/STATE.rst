项目状态
========

最后更新
--------

2026-07-12

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-037``。最新三章：

#. ``LK-BOOT-035``：Linux startup_64 怎样把压缩内核搬到安全解压位置？
#. ``LK-BOOT-036``：Linux 怎样建立解压映射并选择正式内核的位置？
#. ``LK-BOOT-037``：Linux 怎样解压 ELF 内核并进入正式 startup_64？

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

第三十五至三十七章已经完成：

::

   compressed startup_64
   → compute decompressed physical base in RBP
   → compute relocated compressed base in RBX
   → switch to relocated boot stack
   → preserve boot_params in R15
   → configure 4-level or 5-level paging
   → copy initialized compressed image backwards
   → repoint GDTR
   → jump to relocated compressed copy
   → clear compressed BSS
   → load stage2 IDT
   → initialize extendable identity maps
   → map compressed image, boot_params, cmdline and setup_data
   → sanitize boot_params
   → initialize compressed early console and RSDP
   → calculate needed_size
   → choose fixed or KASLR physical/virtual output
   → decompress payload through the configured decompressor
   → parse ELF program headers
   → move PT_LOAD segments
   → apply 32-bit, inverse-32-bit and 64-bit relocations
   → remove compressed exception handling
   → jump to decompressed arch/x86/kernel/head_64.S:startup_64
   → switch to __top_init_kernel_stack
   → establish early GS base and formal GDT/IDT
   → call __startup_64()
   → calculate phys_base and fix early page tables
   → load early_top_pgt into CR3
   → jump to high-half common_startup_64

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/kernel/head_64.S:common_startup_64``；
* 当前主流程 CPU：BSP；
* CPU 模式：64 位 long mode；
* interrupts：关闭；
* current RIP：正式内核高半区虚拟地址；
* compressed image：已完成使命；
* 正式 kernel ELF：已解压并按 ``PT_LOAD`` 布局完成；
* kernel relocation：已完成；
* ``boot_params``：地址仍由 ``R15`` 保存；
* stack：``__top_init_kernel_stack``；
* GS base：boot CPU early fixed percpu data；
* ``phys_base``：已记录实际物理 relocation delta；
* ``CR3``：修正后的 ``early_top_pgt``；
* 正式 high-half mapping：已启用；
* 临时 identity mapping：仍在早期页表中，尚未全部清理；
* boot CPU number：尚待 ``common_startup_64`` 继续确定和建立；
* initramfs：尚未展开；
* ``x86_64_start_kernel()``：尚未调用；
* ``start_kernel()``：尚未调用。

完成状态
--------

``complete`` 表示章节到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 ``arch/x86/kernel/head_64.S:common_startup_64`` 开始，追踪 CR4 清理与 PGE、boot CPU 编号和 percpu offset、TSS/stack、early IDT、``initial_code``，直到 ``x86_64_start_kernel()`` 取得控制权。随后再进入 ``start_kernel()``，不提前跨过中间汇编与架构初始化。
