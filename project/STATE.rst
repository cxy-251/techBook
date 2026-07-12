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

第二十一章结束在：

::

   maininit()
   → interactive_bootmenu()
   → 条件调整 BootList 头部
   → wait_threads()
   → prepareboot()
   → tpm_prepboot()
   → bcv_prepboot()
   → 执行 BCV
   → map_hd_drive(AHCI port 0)
   → IDMap[HD][0]
   → BDA hdcount = 1
   → logical CHS / EBDA FDPT / IVT 0x41
   → 构造最终 BEV[]
   → cdrom_prepboot()
   → pmm_prepboot()
   → malloc_prepboot()
   → e820_prepboot()
   → HaveRunPost = 2
   → BIOS checksum
   → prepareboot() 返回

``maininit()`` 接下来执行：

.. code-block:: c

   make_bios_readonly();
   startBoot();

此刻机器状态：

* 当前执行者：SeaBIOS ``maininit()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* BCV：已经执行；
* 固定 AHCI port 0 硬盘：已经映射为 BIOS 第一块硬盘；
* ``DL=0x80``：将解析到 ``IDMap[EXTTYPE_HD][0]``；
* BDA ``hdcount``：固定单盘路径为 1；
* logical CHS / FDPT：已经建立；
* 最终 ``BEV[]``：已经形成；
* PMM：已经关闭；
* E820：已经冻结；
* BIOS checksum：已经更新；
* MBR sector 0：尚未读取；
* ``0x7c00``：尚未写入启动扇区；
* GRUB：尚未执行；
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

* BIOS drive numbering、CHS translation、FDPT、EDD 与 PMM 资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/post.c``、``src/boot.c``、``src/block.c``、``src/disk.c``、``src/pmm.c``、``src/malloc.c`` 和 ``src/e820map.c``。

当前下一步
----------

从 ``maininit():make_bios_readonly()`` 开始，追踪 q35 PAM shadow write-protect、``startBoot():INT 19h``、``do_boot():boot_disk(0x80)`` 和 ``INT 13h AH=02h`` 怎样把第一扇区读到物理地址 ``0x7c00``。