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
#. ``LK-BOOT-023``：GRUB boot.img 怎样从 0x7c00 读出 core.img 的第一扇区？
#. ``LK-BOOT-024``：GRUB diskboot.img 怎样按 blocklist 读完 core.img？
#. ``LK-BOOT-025``：GRUB startup_raw 怎样进入保护模式并调用 grub_main？
#. ``LK-BOOT-026``：GRUB 怎样通过 BIOS E820 建立自己的堆？
#. ``LK-BOOT-027``：GRUB 怎样加载内建模块并建立 hd0、root 和 prefix？

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GNU GRUB 2.14 i386-pc
   → bzImage
   → Linux 6.12.95

固定 GRUB 来源与安装布局
-----------------------

::

   GNU GRUB release = 2.14
   release commit   = d38d6a1a9b79427848976f53d474392cd29c2a71
   target           = i386-pc
   partition table  = MBR
   first partition  = LBA 2048
   first filesystem = ext4
   GRUB directory   = /boot/grub
   boot.img         = LBA 0
   core.img         = contiguous from LBA 1

当前固定 ``core.img`` 至少嵌入 ``biosdisk``、``part_msdos``、``ext2``、``normal`` 及自动依赖；embedded prefix 为 ``(,msdos1)/boot/grub``，简单同盘路径不嵌入额外 config 对象。

当前控制流位置
--------------

第二十七章结束在：

::

   grub_main()
   → grub_machine_init() returns
   → grub_verifiers_init()
   → no OBJ_TYPE_CONFIG in the fixed simple path
   → grub_register_exported_symbols()
   → grub_load_modules()
   → iterate gmim preload objects
   → validate ET_REL modules
   → allocate module sections from the GRUB heap
   → resolve dependencies and exported symbols
   → apply i386 relocations
   → grub_dl_init() / GRUB_MOD_INIT
   → biosdisk registers the BIOS disk backend
   → part_msdos registers the MBR partition map
   → ext2 registers ext2/ext3/ext4 filesystem reading
   → normal registers normal mode and menu/script facilities
   → grub_machine_get_bootlocation()
   → grub_boot_device 0x80ffffff becomes fwdevice hd0
   → embedded prefix (,msdos1)/boot/grub
   → cmdpath = (hd0)
   → root = hd0,msdos1
   → prefix = (hd0,msdos1)/boot/grub
   → reclaim_module_space()
   → grub_register_core_commands()

此刻机器状态：

* 当前执行者：GNU GRUB 2.14 ``grub_main()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* GRUB heap：已建立，原始预装模块输入区已经回收；
* core exported symbols：已注册；
* core.img 内建 ELF：已重定位并执行初始化函数；
* ``biosdisk``：已注册到通用磁盘层；
* BIOS drive ``0x80``：可按 GRUB 名称 ``hd0`` 打开；
* ``part_msdos``：已注册；
* ``ext2``：已注册，可读取固定 ext4 分区；
* ``normal``：已注册；
* ``cmdpath``：``(hd0)``；
* ``root``：``hd0,msdos1``；
* ``prefix``：``(hd0,msdos1)/boot/grub``；
* embedded config：固定简单路径中不存在；
* 磁盘 ``grub.cfg``：尚未打开；
* GRUB 菜单：尚未建立；
* Linux ``bzImage``：尚未读取；
* Linux：尚未取得控制权。

完成状态
--------

``complete`` 表示章节已经到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。
读者反馈只用于指出哪里难懂、希望展开或阅读不连续。

资料格式
--------

章节末尾的资料使用可点击 RST 链接。章节正文不添加上一章、下一章或目录导航；章节列表集中放在 Linux Kernel 目录页。

固定事实来源
------------

* GNU GRUB 2.14 官方发布包与发布提交 ``d38d6a1a9b79427848976f53d474392cd29c2a71``；
* GRUB ``grub-core/kern/main.c``、``grub-core/kern/dl.c``、``grub-core/kern/i386/pc/init.c``、``grub-core/disk/i386/pc/biosdisk.c``；
* GRUB ``util/grub-install.c``、``util/grub-install-common.c``、``util/mkimage.c`` 与 ``include/grub/kernel.h``；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* QEMU 提交 ``a759542a2c62f0fd3b65f5a66ad9868201014669``；
* Linux 6.12.95 与 Linux/x86 Boot Protocol。

当前下一步
----------

从 ``grub_main():grub_load_normal_mode()`` 开始，追踪 ``normal`` 命令怎样由 ``prefix`` 构造 ``(hd0,msdos1)/boot/grub/grub.cfg``，并沿 ``biosdisk → part_msdos → ext2`` 打开该文件，停在第一条有效配置行交给 ``grub_normal_parse_line()`` 之前。
