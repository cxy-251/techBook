项目状态
========

最后更新
--------

2026-07-11

当前任务
--------

仓库当前只写 Linux Kernel。

第一章已经完成初稿，正在等待实际阅读：

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

第一章范围
----------

第一章从开机请求讲到 SeaBIOS ``entry_post``：

* 平台为什么要先建立供电、时钟和复位条件；
* QEMU 如何把物理上电抽象为虚拟机器与 vCPU 复位状态；
* BSP 为什么从架构规定的复位位置开始；
* ``CS`` 可见值、隐藏基址和 ``RIP`` 如何得到 ``0xfffffff0``；
* 平台怎样让这个地址返回 SeaBIOS ROM 字节；
* SeaBIOS ``reset_vector`` 为什么只放一条远跳转；
* ``f000:e05b`` 为什么对应物理地址 ``0x000fe05b``；
* 控制权怎样进入 ``entry_post``。

固定事实来源
------------

* Intel x86 处理器复位状态；
* SeaBIOS 提交 ``c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf``；
* ``src/romlayout.S``；
* ``src/config.h``；
* SeaBIOS ``Execution_and_code_flow.md``。

章节划分
--------

正文沿真实时间线连续叙述。内容达到适合一次阅读的篇幅，并遇到执行者、CPU 模式、运行环境或控制入口
的自然交接点时换章。每章末尾保留当前执行者、当前状态和下一入口，后续章节从该位置继续。

当前下一步
----------

只阅读和修改 ``docs/tracks/linux-kernel/01-power-on-first-instruction.rst``。

当前不创建第二章。阅读反馈重点关注：

* 哪一段仍然像一句话带过；
* 哪个地址计算没有讲清楚；
* 物理平台与 QEMU 是否被混淆；
* 从复位向量到 ``entry_post`` 的交接是否连续；
* 哪些细节虽然正确，却打断故事。