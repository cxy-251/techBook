项目状态
========

最后更新
--------

2026-07-12

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成 ``LK-BOOT-001`` 至 ``LK-BOOT-034``。最新章节：

``LK-BOOT-034``：Linux startup_32 怎样建立 4 GiB 映射并进入 64 位模式？

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

固定来源与布局
--------------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   Linux release     = 6.12.95
   Linux source tag  = gregkh/linux v6.12.95
   kernel            = /boot/bzImage-6.12.95
   initramfs         = /boot/initramfs-6.12.95.img

当前控制流位置
--------------

第三十四章结束在：

::

   Linux compressed startup_32
   → cld / cli
   → temporary 4-byte stack in boot_params.scratch
   → call/pop computes actual startup_32 address into EBP
   → load Linux GDT
   → switch to Linux __KERNEL32_CS
   → switch to 16 KiB boot stack
   → verify_cpu checks CPUID, long mode and SSE
   → compute safe relocation base in EBX
   → CR4.PAE = 1
   → clear six initial page-table pages
   → PML4[0] points to PDPT
   → four PDPT entries point to four page directories
   → 2048 two-megabyte PDEs identity-map low 4 GiB
   → CR3 = initial PML4
   → EFER.LME = 1
   → invalidate LDT and load early TSS
   → push __KERNEL_CS and startup_64
   → CR0.PG = 1 activates long mode
   → lret loads 64-bit code segment
   → startup_64

此刻机器状态：

* 当前执行者：Linux 6.12.95 ``arch/x86/boot/compressed/head_64.S:startup_64``；
* 当前主流程 CPU：BSP；
* CPU 模式：64 位 long mode；
* paging：开启；
* 初始 paging level：4；
* 初始映射：低 4 GiB identity mapped；
* 初始大页：2 MiB；
* ``CR4.PAE``：1；
* ``EFER.LME`` / ``EFER.LMA``：1；
* interrupts：关闭；
* boot_params 指针：由 32 位入口寄存器继续携带；
* compressed image：尚未搬到安全解压位置；
* BSS：尚未清零；
* ``extract_kernel()``：尚未调用；
* initramfs：尚未解析；
* 最终内核 image：尚未解压；
* ``start_kernel()``：尚未到达。

完成状态
--------

``complete`` 表示章节已经到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。

资料格式
--------

章节末尾资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航。

当前下一步
----------

从 compressed ``startup_64`` 第一条指令开始，追踪 boot_params 保存、解压输出地址计算、5-level paging 配置、compressed image 向安全高端倒序复制、GDT 重定位、跳入 ``.Lrelocated``、清 BSS、建立更完整 identity maps 和调用 ``extract_kernel()``。
