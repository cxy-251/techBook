项目状态
========

最后更新
--------

2026-07-11

当前任务
--------

仓库当前只写 Linux Kernel。

正在编写：

``LK-BOOT-001：按下电源键后，CPU 从哪里取得第一条指令？``

当前主线
--------

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GRUB i386-pc
   → bzImage
   → Linux 6.12.95

当前章节范围
------------

从平台开始建立供电、时钟并保持处理器复位讲起，追踪 x86 复位取指位置、固件地址映射和
SeaBIOS 的 ``reset_vector``，结束在远跳转进入 ``entry_post``。

章节划分
--------

正文沿真实时间线连续叙述。内容达到适合一次阅读的篇幅，并遇到执行者、CPU 模式、运行环境或控制入口
的自然交接点时换章。每章末尾保留当前执行者、当前状态和下一入口，后续章节从该位置继续。

已经完成
--------

* 确认书的主题仍然是 Linux Kernel，上电、固件和 bootloader 只承担必要前传；
* 撤销“一篇覆盖上电到内核解压”的过大章节范围；
* 建立第一章 ``01-power-on-first-instruction.rst``；
* 第一章结束点固定为 SeaBIOS ``reset_vector`` 跳入 ``entry_post``；
* 章节不按 Roadmap 条目切分，也不提前规划整本书。

当前下一步
----------

只审阅和修改 ``docs/tracks/linux-kernel/01-power-on-first-instruction.rst``，检查物理上电、处理器复位状态、
固件地址映射和 SeaBIOS 入口之间是否讲得连续准确。当前章节稳定后，再沿 ``entry_post`` 的真实执行路径
决定下一章。