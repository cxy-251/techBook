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

第九章结束在：

::

   qemu_platform_setup()
   → pci_setup()
   → pci_bios_init_devices()
   → pci_enable_default_vga()
   → pci_setup() 返回

``qemu_platform_setup()`` 接下来执行：

.. code-block:: c

   smm_device_setup();

此刻机器状态：

* 当前执行者：SeaBIOS ``qemu_platform_setup()``；
* CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* q35 MMCONFIG：已经启用并标记为 ``E820_RESERVED``；
* PCI bus number、BAR 与 bridge window：已经配置；
* PCI INTx line：已经计算并写入；
* ICH9 PIRQA-H：已经路由到 IRQ10/IRQ11；
* IRQ10/IRQ11：已经设置为 level-triggered；
* ICH9 LPC PMBASE、SCI、RCBA 与 PM timer 地址：已经建立；
* PCI I/O 与 memory decode：已经打开；
* PCI SERR 与 bridge SERR forwarding：已经打开；
* bus mastering：尚未统一开启，由具体驱动按需设置；
* 默认 VGA 路径：已经选择并保证可达；
* VGA Option ROM：尚未执行；
* SMM：尚未安装；
* ATA、AHCI、NVMe、USB、virtio 与网络驱动：尚未开始设备探测；
* 磁盘、光驱与网络启动项：尚未加入 ``BootList``；
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

* Intel x86 处理器复位、实模式、保护模式与 SMM 资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/fw/pciinit.c`` 和 ``src/fw/dev-q35.h``；
* SeaBIOS ``src/hw/pci.c``、``src/hw/pci.h``、``src/hw/pcidevice.c`` 和 ``src/hw/pci_regs.h``；
* SeaBIOS ``src/hw/ata.h`` 和 ``src/optionroms.c``；
* PCI Firmware Specification。

当前下一步
----------

收到继续指令后，从 ``qemu_platform_setup():smm_device_setup()`` 开始，继续追踪 q35/ICH9 SMI 设备准备、SMRAM
映射与 SeaBIOS SMM handler 安装。
