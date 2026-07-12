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

第二十章结束在：

::

   maininit()
   → optionrom_setup()
   → 记录 post_vga 边界
   → 跳过 VGA/display 与 have_driver 设备
   → 部署 PCI 或 fw_cfg ROM
   → 选择匹配的 x86 image
   → 复制到 0xc0000..0xeffff
   → 验证 0xaa55 / size / checksum
   → 条件执行 PnP init vector
   → 条件恢复被错误捕获的 INT 19h
   → 部署 genroms/
   → 第二遍扫描最终 ROM 布局
   → legacy ROM 登记为 BCV
   → PnP header 登记为 BCV 或 BEV
   → optionrom_setup() 返回

``maininit()`` 接下来执行：

.. code-block:: c

   interactive_bootmenu();
   wait_threads();
   prepareboot();

此刻机器状态：

* 当前执行者：SeaBIOS ``maininit()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* 普通 PCI/CBFS Option ROM：已经部署和解析；
* ``have_driver`` 设备：已跳过普通 ROM 扫描；
* PnP init vector：已经条件执行；
* legacy/PnP BCV：已经登记，尚未执行；
* BEV：已经登记，尚未调用；
* ``BootList``：包含内建设备和条件 BCV/BEV/CBFS 条目；
* BIOS ``0x80`` drive mapping：尚未建立；
* MBR sector 0：尚未读取；
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

* PCI Expansion ROM、PnP BIOS、BCV、BEV 与 QEMU fw_cfg 资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/optionroms.c``、``src/std/optionrom.h``、``src/hw/pcidevice.c``、``src/boot.c`` 和 ``src/post.c``。

当前下一步
----------

从 ``maininit():interactive_bootmenu()`` 开始，追踪用户选择怎样调整 BootList，然后进入 ``prepareboot():bcv_prepboot()`` 执行 BCV、分配 BIOS 驱动号并生成最终 BEV 启动序列。