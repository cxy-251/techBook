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

第十九章结束在：

::

   maininit()
   → synchronous device_hardware_setup()
   → block_setup()
   → q35 ICH9 AHCI function 00:1f.2
   → BAR5 / bus master
   → HBA reset / AHCI enable
   → per-port threads
   → fixed boot disk on SATA port 0
   → command list / received FIS / command table
   → link DET=3 and device ready
   → IDENTIFY DEVICE
   → model / LBA capacity / transfer mode
   → persistent AHCI structures
   → boot_add_hd()
   → device_hardware_setup() 返回
   → wait_threads()
   → 所有当前 USB、PS/2、AHCI 与其他设备线程完成

``maininit()`` 接下来执行：

.. code-block:: c

   optionrom_setup();

此刻机器状态：

* 当前执行者：SeaBIOS ``maininit()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* 固定 storage controller：QEMU q35 内置 ICH9 AHCI，典型 BDF ``00:1f.2``；
* 固定启动盘：SATA port 0；
* AHCI HBA/port engine：已经初始化；
* IDENTIFY、LBA capacity、model、transfer mode：已经记录；
* persistent command/FIS DMA structures：已经建立；
* ``BootList``：已经包含 AHCI hard-disk entry，以及条件 USB/CD/其他内建设备；
* 当前设备线程：全部完成；
* BIOS ``0x80`` drive mapping：尚未由 ``bcv_prepboot()`` 建立；
* MBR sector 0：尚未读取；
* 普通非 VGA Option ROM：尚未扫描；
* GRUB：尚未被读取或执行；
* Linux：尚未装入内存。

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

* AHCI 1.3.1、ATA/ATAPI 与 PCI Firmware 资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/block.c``、``src/hw/ahci.c``、``src/boot.c``、``src/stacks.c`` 和 ``src/post.c``；
* QEMU 提交 ``a759542a2c62f0fd3b65f5a66ad9868201014669`` 的 ``hw/i386/pc_q35.c`` 与 ``include/hw/southbridge/ich9.h``。

当前下一步
----------

从 ``maininit():optionrom_setup()`` 开始，扫描普通 PCI/CBFS Option ROM，解释 ``have_driver``、PnP expansion header、BCV、BEV 和 PXE 怎样继续扩充 BootList。