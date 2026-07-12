项目状态
========

最后更新
--------

2026-07-12

当前任务
--------

仓库当前只写 Linux Kernel。

已经完成：

#. ``LK-BOOT-001``：按下电源键后，CPU 从哪里取得第一条指令？
#. ``LK-BOOT-002``：SeaBIOS 怎样从 16 位入口进入 32 位 C 代码？
#. ``LK-BOOT-003``：SeaBIOS 怎样识别内存并把初始化代码搬到 RAM？
#. ``LK-BOOT-004``：SeaBIOS 怎样在低端内存建立 IVT、BDA 和 EBDA？
#. ``LK-BOOT-005``：SeaBIOS 怎样把自己变成可供启动软件调用的 BIOS？
#. ``LK-BOOT-006``：SeaBIOS 怎样建立中断基础并启动内部线程？
#. ``LK-BOOT-007``：SeaBIOS 怎样为 q35 编号 PCI 总线并发现设备？
#. ``LK-BOOT-008``：SeaBIOS 怎样启用 q35 MMCONFIG 并为 PCI 设备分配地址？
#. ``LK-BOOT-009``：SeaBIOS 怎样接通 q35 PCI 中断并打开设备地址解码？
#. ``LK-BOOT-010``：SeaBIOS 怎样进入 SMM 并把处理入口藏进 SMRAM？
#. ``LK-BOOT-011``：SeaBIOS 怎样规定物理地址的缓存类型并准备每个 CPU 的 MSR？
#. ``LK-BOOT-012``：SeaBIOS 怎样用 INIT/SIPI 唤醒其他 CPU？
#. ``LK-BOOT-013``：SeaBIOS 怎样把 CPU、IRQ 和内存信息写成固件表？
#. ``LK-BOOT-014``：SeaBIOS 怎样执行 QEMU 的 ACPI table-loader 并找到 RSDP？
#. ``LK-BOOT-015``：SeaBIOS 怎样沿 RSDP 读懂 ACPI 表图并解析 DSDT？
#. ``LK-BOOT-016``：SeaBIOS 怎样建立时间基准、18.2 Hz BIOS 时钟并初始化 TPM？
#. ``LK-BOOT-017``：SeaBIOS 为什么先运行 VGA Option ROM 再初始化其他设备？
#. ``LK-BOOT-018``：SeaBIOS 怎样枚举 USB 设备并初始化 PS/2 键盘？
#. ``LK-BOOT-019``：SeaBIOS 怎样发现 q35 的 AHCI 磁盘并把它加入启动列表？
#. ``LK-BOOT-020``：SeaBIOS 怎样扫描普通 Option ROM 并把 BCV、BEV 加入启动列表？
#. ``LK-BOOT-021``：SeaBIOS 怎样执行 BCV 并把启动盘映射成 BIOS 0x80？
#. ``LK-BOOT-022``：SeaBIOS 怎样把硬盘第一扇区读到 0x7c00 并交给 GRUB？

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GRUB i386-pc
   → bzImage
   → Linux 6.12.95

当前控制流位置
--------------

第二十二章结束在：

::

   maininit()
   → make_bios_readonly()
   → wbinvd
   → q35 PAM write-protect
   → startBoot()
   → 清理 0x7000..0x8ffff
   → call16_int(0x19)
   → handle_19()
   → BootSequence = 0
   → do_boot(0)
   → boot_disk(0x80)
   → INT 13h AH=02h, CHS 0/0/1
   → IDMap[EXTTYPE_HD][0]
   → q35 AHCI port 0 drive_s
   → CHS 转 LBA 0
   → 32 位 AHCI CMD_READ
   → DMA 512 bytes 到物理地址 0x7c00
   → Carry Flag 清零
   → 检查 0x55aa
   → 条件 TPM 测量 boot sector
   → AX=0xaa55, DL=0x80, IF=1
   → farcall16 / iretw
   → CS:IP = 0000:7c00

此刻机器状态：

* 当前执行者：GRUB i386-pc ``boot.img``；
* 当前 CPU：BSP；
* 模式：16 位实模式；
* 分页：关闭；
* ``CS:IP``：``0000:7c00``；
* ``DL``：``0x80``；
* ``AX``：``0xaa55``；
* FLAGS.IF：1；
* 物理 ``0x7c00..0x7dff``：启动盘 LBA 0 的 512 字节；
* MBR signature：已通过 ``0x55aa`` 检查；
* SeaBIOS AHCI/INT 13h 服务：仍可供 GRUB 调用；
* GRUB ``core.img``：尚未读取；
* GRUB 32 位 core：尚未执行；
* Linux bzImage：尚未读取；
* Linux：尚未取得控制权。

完成状态
--------

``complete`` 表示章节已经到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。
读者反馈只用于指出哪里难懂、希望展开或阅读不连续。

资料格式
--------

章节末尾的资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航；章节列表集中放在 Linux
Kernel 目录页。

固定事实来源
------------

* BIOS ``INT 19h``、``INT 13h``、MBR、实模式调用约定与 q35 PAM 资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/post.c``、``src/fw/shadow.c``、``src/boot.c``、``src/disk.c``、``src/block.c``、``src/hw/ahci.c``、``src/stacks.c``、``src/romlayout.S`` 和 ``src/std/disk.h``。

当前下一步
----------

先固定 GRUB i386-pc 的准确源码 release/commit 和磁盘安装布局，再从 ``boot.img`` 在 ``0000:7c00`` 的第一条汇编指令开始，追踪它怎样保留启动驱动号并读取 ``core.img``。