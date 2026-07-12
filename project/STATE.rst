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

第十四章结束在：

::

   qemu_platform_setup()
   → romfile_loader_execute("etc/table-loader")
   → ALLOCATE ACPI blobs
   → ADD_POINTER
   → ADD_CHECKSUM
   → 条件 WRITE_POINTER
   → find_acpi_rsdp()
   → RsdpAddr 保存成功

``qemu_platform_setup()`` 接下来执行：

.. code-block:: c

   acpi_dsdt_parse();
   virtio_mmio_setup_acpi();
   return;

此刻机器状态：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* 当前主流程 CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* AP：已经完成固件报到并停在 ``HLT``；
* ACPI table blob：已经复制到最终客户机内存；
* ACPI 表间地址：已经完成重定位；
* ACPI checksum：已经在重定位后重新计算；
* RSDP：已经在 F-segment 找到并保存；
* RSDT/XSDT、FADT、MADT、MCFG：尚未在正文中展开；
* DSDT AML：尚未由 SeaBIOS 轻量解析；
* 平台定时器与周期 IRQ0：尚未完成最后初始化；
* TPM：尚未初始化；
* 存储、USB 与网络驱动：尚未开始介质探测；
* ``BootList``：尚无具体启动设备；
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

* ACPI Specification 与 QEMU bios-linker-loader 接口；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* QEMU 提交 ``a759542a2c62f0fd3b65f5a66ad9868201014669``；
* SeaBIOS ``src/fw/romfile_loader.c``、``src/fw/paravirt.c`` 与 ``src/fw/biostables.c``；
* QEMU ``hw/acpi/bios-linker-loader.c``、``include/hw/acpi/aml-build.h`` 与 ``hw/i386/acpi-build.c``。

当前下一步
----------

收到继续指令后，从 ``RsdpAddr`` 进入 RSDT/XSDT、FADT、MADT、MCFG 和 DSDT，并追踪 ``acpi_dsdt_parse()`` 与 ``virtio_mmio_setup_acpi()``。