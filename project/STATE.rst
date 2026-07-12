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

第十五章结束在：

::

   qemu_platform_setup()
   → RsdpAddr 已找到
   → XSDT/RSDT 表图可用
   → FADT/MADT/MCFG 等核心表已安装
   → acpi_dsdt_parse()
   → 建立受限 AML 设备索引
   → 条件 virtio_mmio_setup_acpi()
   → qemu_platform_setup() 返回

``platform_hardware_setup()`` 接下来执行：

.. code-block:: c

   coreboot_platform_setup();
   timer_setup();
   clock_setup();
   tpm_setup();

当前 QEMU/SeaBIOS 主线的有效下一入口是 ``timer_setup()``。

此刻机器状态：

* 当前执行者：SeaBIOS ``platform_hardware_setup()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* AP：已经完成固件报到并停在 ``HLT``；
* ACPI RSDP、RSDT/XSDT 与核心表：已经安装；
* FADT：已描述 ICH9 PM、SCI、PM timer 与 reset interface；
* MADT：已描述 CPU、local APIC、I/O APIC 和 interrupt override；
* MCFG：已描述 q35 MMCONFIG；
* DSDT：已由 SeaBIOS 建立受限设备索引；
* 条件 virtio-mmio block/SCSI：可能已经创建探测线程；
* qemu_platform_setup：已经返回；
* SeaBIOS 内部最终时间源：尚待 ``timer_setup()`` 确认；
* PIT IRQ0、RTC 与 BDA timer counter：尚待 ``clock_setup()``；
* TPM：尚未初始化；
* 普通存储、USB 与网络驱动：尚未进入 ``device_hardware_setup()``；
* ``BootList``：尚无完整启动设备集合；
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

* ACPI Specification、AML、MADT、FADT 与 MCFG；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* QEMU 提交 ``a759542a2c62f0fd3b65f5a66ad9868201014669``；
* SeaBIOS ``src/fw/biostables.c``、``src/fw/dsdt_parser.c``、``src/hw/virtio-mmio.c`` 与 ``src/fw/paravirt.c``；
* QEMU ``hw/i386/acpi-build.c`` 与 ``hw/acpi/aml-build.c``。

当前下一步
----------

收到继续指令后，从 ``platform_hardware_setup():timer_setup()`` 开始，追踪内部时间源、PIT IRQ0、RTC/BDA 时钟与条件 TPM measured boot 初始化。