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

第三章结束在：

::

   relocated post.c:maininit()

此刻机器状态：

* 当前执行者：重定位后的 SeaBIOS ``maininit()``；
* CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* A20：开启；
* 栈：平坦地址 ``0x7000``；
* BIOS 低地址区域：shadow RAM，可写；
* E820：已经形成初始内存地图；
* 临时低端区、临时高端区和永久高端区：已经建立；
* 一次性初始化代码：已经搬到普通 RAM；
* GRUB：尚未被搜索；
* Linux：尚未装入内存。

章节导航
--------

已完成章节末尾提供相对链接，可直接跳转上一章、下一章或 Linux Kernel 目录。尚未创建下一章时，只提供
上一章和目录链接。

完成状态
--------

``complete`` 表示章节已经到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。
读者反馈只用于指出哪里难懂、希望展开或阅读不连续。

固定事实来源
------------

* Intel x86 处理器复位与保护模式资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* SeaBIOS ``src/romlayout.S``、``src/entryfuncs.S``、``src/post.c``；
* SeaBIOS ``src/fw/shadow.c``、``src/fw/paravirt.c``、``src/fw/xen.c``；
* SeaBIOS ``src/malloc.c``、``src/output.c``、``src/hw/serialio.c``；
* SeaBIOS ``Linking_overview.md``、``Memory_Model.md`` 和 ``Execution_and_code_flow.md``。

当前下一步
----------

收到继续指令后，从重定位后的 ``maininit()`` 开始，沿实际控制流继续。