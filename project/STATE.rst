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
   boot.img         = LBA 0
   core.img         = contiguous from LBA 1

GNU 官方发布包是 ``grub-2.14.tar.xz``；源码引用使用 ``GitMirroring/grub`` 的固定发布提交。

当前控制流位置
--------------

第二十五章结束在：

::

   SeaBIOS → 0000:7c00
   → GRUB boot.img
   → canonicalize CS=0
   → DS=SS=0, SP=0x2000
   → preserve DL=0x80
   → INT 13h EDD probe
   → INT 13h AH=42h read LBA 1 to 0x70000
   → copy diskboot.img to 0x8000
   → jump 0000:8000
   → diskboot.img reads blocklist
   → load core.img LBA 2..N through 0x70000 bounce buffer
   → copy remaining core to 0x8200...
   → jump 0000:8200
   → startup_raw
   → real stack = 0x1ff0
   → save encoded boot device 0x80ffffff
   → real_to_prot()
   → load GDT
   → CR0.PE = 1
   → CS=0x08, data selectors=0x10
   → protected stack = 0x7fff0
   → verify A20
   → optional Reed–Solomon recovery
   → LZMA decompress to 0x100000
   → enter decompressed startup.S
   → copy formal GRUB core code to link address 0x9000
   → clear BSS
   → grub_boot_device = 0x80ffffff
   → call grub_main()

此刻机器状态：

* 当前执行者：GNU GRUB 2.14 ``grub_main()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* A20：已经开启并由 GRUB 重新验证；
* flat code/data segments：已经建立；
* protected-mode stack：位于低端 GRUB 保留区，栈顶约 ``0x7fff0``；
* 正式 GRUB core 代码：位于链接地址 ``0x9000``；
* 解压和模块区域：从 ``0x100000`` 附近开始；
* BSS：已经清零；
* ``grub_boot_device``：``0x80ffffff``；
* 启动 BIOS drive：``0x80``，后续会推导为 ``hd0``；
* BIOS 实模式服务：仍可通过 ``prot_to_real`` / ``real_to_prot`` 桥调用；
* GRUB machine initialization：尚未展开；
* GRUB heap：尚未在正文中建立；
* 内建模块：尚未在正文中初始化；
* ``grub.cfg``：尚未读取；
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

* GNU GRUB 2.14 官方发布包；
* GRUB 发布提交 ``d38d6a1a9b79427848976f53d474392cd29c2a71``；
* GRUB ``boot.S``、``diskboot.S``、``startup_raw.S``、``realmode.S``、``startup.S``、``init.c``、``util/setup.c`` 和 ``util/mkimage.c``；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* QEMU 提交 ``a759542a2c62f0fd3b65f5a66ad9868201014669``；
* Linux 6.12.95 与 Linux/x86 Boot Protocol。

当前下一步
----------

从 GNU GRUB 2.14 ``grub_main()`` 开始，追踪 ``grub_machine_init()``、控制台、BIOS memory map、GRUB heap、内建模块和启动设备 ``hd0`` 的建立。只在到达读取 ``grub.cfg`` 前的自然交接点后换章。
