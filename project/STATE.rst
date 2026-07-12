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

第五章结束在：

::

   maininit():platform_hardware_setup()

此刻机器状态：

* 当前执行者：重定位后的 SeaBIOS ``maininit()``；
* CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* IVT、BDA、EBDA 和额外 16 位中断栈：已经建立；
* BIOS32、PCI BIOS、PMM 和 PnP 发现入口：已经建立；
* 启动优先级规则：已经建立；
* 具体启动设备：尚未加入 ``BootList``；
* 键盘 BDA 环形队列：已经初始化；
* 鼠标 BIOS 支持标志：已经设置；
* PCI、PIC、定时器、PS/2 和磁盘硬件初始化：尚未执行；
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

* Intel x86 处理器复位与保护模式资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/post.c``、``src/boot.c``、``src/pcibios.c`` 和 ``src/romlayout.S``；
* SeaBIOS ``src/pmm.c``、``src/pnpbios.c``、``src/kbd.c`` 和 ``src/mouse.c``；
* SeaBIOS ``src/std/pmm.h``、``src/std/pnpbios.h``、``src/std/bda.h``；
* SeaBIOS ``Memory_Model.md`` 和 ``Execution_and_code_flow.md``。

当前下一步
----------

收到继续指令后，从 ``maininit():platform_hardware_setup()`` 开始，沿实际控制流继续。