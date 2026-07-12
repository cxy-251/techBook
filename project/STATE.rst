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

第六章结束在：

::

   platform_hardware_setup():qemu_platform_setup()

此刻机器状态：

* 当前执行者：重定位后的 SeaBIOS ``platform_hardware_setup()``；
* CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* 传统 DMA：控制器已复位，级联通道已接通，普通通道未开始传输；
* PIC：两片 8259A 已初始化；
* 硬件 IRQ 向量：master 使用 ``0x08``，slave 使用 ``0x70``；
* master IRQ2 和 slave IRQ13：已解除屏蔽；
* SeaBIOS 内部协作式线程能力：已经建立，设备线程尚未创建；
* 数学协处理器 BIOS 标志与 ``INT 75h`` 兼容入口：已经建立；
* PCI 枚举：尚未执行；
* SMM、MTRR、SMP、ACPI、SMBIOS 和 MP table：尚未建立；
* 定时器、周期时钟、PS/2 和磁盘硬件：尚未初始化；
* 具体启动设备：尚未加入 ``BootList``；
* GRUB：尚未被搜索；
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
* SeaBIOS ``src/post.c``、``src/hw/dma.c``、``src/hw/pic.c`` 和 ``src/hw/pic.h``；
* SeaBIOS ``src/stacks.c``、``src/stacks.h`` 和 ``src/misc.c``；
* SeaBIOS ``Memory_Model.md`` 和 ``Execution_and_code_flow.md``。

当前下一步
----------

收到继续指令后，从 ``platform_hardware_setup():qemu_platform_setup()`` 开始，沿 QEMU q35 平台控制流继续。