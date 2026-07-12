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

第四章结束在：

::

   interface_init():boot_init()

此刻机器状态：

* 当前执行者：SeaBIOS ``interface_init()``；
* CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* IVT：已经建立；
* BDA：已经建立；
* EBDA：位于 ``0x9fc00``，初始大小 1 KiB；
* traditional memory size：639 KiB；
* E820：EBDA 区域已经标记为保留；
* 额外 16 位中断栈：已经建立；
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
* SeaBIOS ``src/post.c``、``src/malloc.c``、``src/fw/paravirt.c``；
* SeaBIOS ``src/biosvar.h``、``src/std/bda.h``、``src/stacks.c``；
* SeaBIOS ``Memory_Model.md`` 和 ``Execution_and_code_flow.md``。

当前下一步
----------

收到继续指令后，从 ``interface_init():boot_init()`` 开始，沿实际控制流继续。