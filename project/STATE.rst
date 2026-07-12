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

第七章结束在：

::

   qemu_platform_setup()
   → pci_setup()
   → pci_probe_devices() 返回

``pci_setup()`` 接下来执行：

.. code-block:: c

   pcimem_start = RamSize;
   pci_bios_init_platform();

此刻机器状态：

* 当前执行者：SeaBIOS ``pci_setup()``；
* CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* 传统 DMA 与 8259A PIC：已经初始化；
* SeaBIOS 内部协作式线程能力：已经建立；
* PCI Configuration Mechanism #1：已经通过 ``0xcf8 / 0xcfc`` 验证；
* PCI bridge 的 primary、secondary、subordinate bus number：已经分配；
* ``PCIDevices``：已经保存已发现 function 的 BDF、vendor/device、class、header type 和 parent bridge；
* PCI 配置访问：仍使用 ``0xcf8 / 0xcfc``；
* SeaBIOS 内部 q35 MMCONFIG：尚未启用；
* PCI BAR 大小：尚未测量；
* PCI I/O 与 MMIO 地址：尚未分配；
* PCI INTx routing 和 command bits：尚未完成；
* PCI 设备驱动：尚未运行；
* 磁盘、光驱、USB 与网络启动设备：尚未探测；
* 具体启动设备：尚未加入 ``BootList``；
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

* Intel x86 处理器复位、实模式和保护模式资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/fw/paravirt.c``、``src/fw/pciinit.c`` 和 ``src/fw/dev-q35.h``；
* SeaBIOS ``src/hw/pci.c``、``src/hw/pci.h``、``src/hw/pcidevice.c`` 和 ``src/hw/pcidevice.h``；
* SeaBIOS ``src/hw/pci_regs.h``。

当前下一步
----------

收到继续指令后，从 ``pci_setup():pcimem_start = RamSize`` 和 ``pci_bios_init_platform()`` 开始，继续追踪 q35
MMCONFIG、BAR sizing、bridge window 与 PCI I/O/MMIO 地址分配。