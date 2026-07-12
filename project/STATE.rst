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
#. ``LK-BOOT-028``：GRUB normal 怎样找到并打开 grub.cfg？
#. ``LK-BOOT-029``：GRUB 怎样解析 grub.cfg 并建立第一个 Linux 菜单项？
#. ``LK-BOOT-030``：GRUB 怎样自动选择菜单项并装入 linux 命令模块？

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

固定 grub.cfg
-------------

.. code-block:: cfg

   set timeout=0
   set default=0

   menuentry 'Linux 6.12.95' {
       linux /boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs-6.12.95.img
   }

当前控制流位置
--------------

第三十章结束在：

::

   grub_normal_execute()
   → grub_show_menu()
   → show_menu()
   → run_menu()
   → resolve default = entry 0
   → resolve timeout = 0
   → return entry 0 without drawing menu
   → grub_menu_execute_with_fallback()
   → grub_menu_execute_entry()
   → chosen = Linux 6.12.95
   → grub_script_execute_new_scope(entry->sourcecode)
   → execute setparams
   → reach linux command line
   → find dynamic linux placeholder from command.lst
   → grub_dyncmd_dispatcher()
   → grub_dl_load("linux")
   → open (hd0,msdos1)/boot/grub/i386-pc/linux.mod
   → read complete module into GRUB heap
   → parse ELF ET_REL
   → resolve dependencies and symbols
   → relocate allocatable sections
   → add module and run GRUB_MOD_INIT(linux)
   → register real linux and initrd commands
   → unregister dynamic placeholder
   → find real linux command
   → stop before grub_cmd_linux()

此刻机器状态：

* 当前执行者：GNU GRUB 2.14 dynamic command dispatcher；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* selected entry / ``chosen``：``Linux 6.12.95``；
* entry scope：已建立，``setparams`` 已执行；
* dynamic ``linux`` placeholder：已注销；
* ``linux.mod``：已从 ext4 读取、重定位并初始化；
* 真实 ``linux`` 与 ``initrd`` 命令：已注册；
* ``linux`` 参数：``/boot/bzImage-6.12.95 root=/dev/sda1 ro console=ttyS0``；
* ``grub_cmd_linux()``：尚未调用；
* ``/boot/bzImage-6.12.95``：尚未打开；
* ``/boot/initramfs-6.12.95.img``：尚未打开；
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
* GRUB ``grub-core/normal/main.c``、``normal/menu.c``、``normal/dyncmd.c``、``script/execute.c``；
* GRUB ``grub-core/kern/dl.c`` 与 ``grub-core/loader/i386/linux.c``；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* QEMU 提交 ``a759542a2c62f0fd3b65f5a66ad9868201014669``；
* Linux 6.12.95 与 Linux/x86 Boot Protocol。

当前下一步
----------

从真实 ``grub_cmd_linux()`` 开始，打开固定 ``/boot/bzImage-6.12.95``，验证 Linux/x86 setup header，建立 boot parameter 副本、命令行和 relocator-backed protected-mode payload；停在 ``grub_loader_set()`` 完成后，尚不执行 ``initrd``。
