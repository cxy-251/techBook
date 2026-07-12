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

第十六章结束在：

::

   platform_hardware_setup()
   → timer_setup()
   → clock_setup()
   → 条件 tpm_setup()
   → platform_hardware_setup() 返回
   → maininit()

``maininit()`` 接下来执行：

.. code-block:: c

   if (threads_during_optionroms())
       device_hardware_setup();

   vgarom_setup();

设备探测是在 VGA Option ROM 前启动，还是在 VGA 之后同步执行，由 ``ThreadControl`` 和 ``threads_during_optionroms()`` 决定。

此刻机器状态：

* 当前执行者：SeaBIOS ``maininit()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* SeaBIOS 内部 deadline timer：已经选定；
* PIT channel 0：已经配置为约 18.2 Hz；
* BDA ``timer_counter``：已由 RTC 当前时间初始化；
* IRQ0 / INT 08h、INT 1Ch 与 INT 1Ah：已经建立；
* 条件 RTC IRQ8 / INT 70h：已经建立；
* 条件 TPM：已启动并建立 event log；
* 条件 measured boot：已测量 SMBIOS 并标记 option ROM scan 起点；
* USB、PS/2、ATA/AHCI/NVMe 与普通 virtio-pci 驱动：尚未完成 ``device_hardware_setup()``；
* VGA Option ROM：尚未执行；
* 普通 option ROM：尚未扫描；
* ``BootList``：尚未形成最终启动设备集合；
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

* PIT、RTC、BDA timer、INT 08h/1Ah/70h 与 TCG TPM 资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/hw/timer.c``、``src/clock.c``、``src/hw/rtc.c``、``src/std/bda.h``、``src/stacks.c`` 与 ``src/tcgbios.c``。

当前下一步
----------

收到继续指令后，从 ``maininit():threads_during_optionroms()`` 开始，确认设备探测与 option ROM 的时序，再进入 ``device_hardware_setup()``、USB、PS/2 和 block driver 初始化。