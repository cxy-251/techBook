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

第二章结束在：

::

   post.c:handle_post()

此刻机器状态：

* 当前执行者：SeaBIOS ``handle_post()``；
* CPU：BSP；
* 模式：32 位保护模式；
* 分页：关闭；
* 64 位模式：关闭；
* A20：开启；
* 栈：平坦地址 ``0x7000``；
* 可屏蔽中断：关闭；
* NMI：临时屏蔽；
* GRUB：尚未被搜索；
* Linux：尚未装入内存。

完成状态
--------

``complete`` 表示章节已经到达自然终点，关键技术事实已依据固定源码或规范核对。读者不承担技术审稿。
读者反馈只用于指出哪里难懂、希望展开或阅读不连续。

固定事实来源
------------

* Intel x86 处理器复位与保护模式资料；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* ``src/romlayout.S``；
* ``src/entryfuncs.S``；
* ``src/config.h``；
* ``src/x86.h``；
* ``src/hw/rtc.h``；
* ``src/misc.c``；
* ``src/post.c``；
* SeaBIOS ``Execution_and_code_flow.md``。

当前下一步
----------

收到继续指令后，从 ``handle_post()`` 的第一条调用开始，沿实际控制流继续。当前不预先命名或规划后续章节。
