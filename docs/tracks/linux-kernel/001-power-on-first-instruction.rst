第一章：按下电源键后，CPU 从哪里取得第一条指令？
====================================================

这本书讲 Linux 内核。Linux 还没有被装入内存之前，必须先有一段代码把机器带到能够装入内核的位置。
故事从电源键被按下开始。

为了让软件阶段的每一次跳转都能定位到固定源码，当前主线使用：

::

   x86-64
   → QEMU q35
   → SeaBIOS
   → GRUB i386-pc
   → bzImage
   → Linux 6.12.95

真实主板的电源控制器、电压调节器、时钟发生器和复位线路因平台而异。QEMU 也不会模拟电压上升和晶振
锁定这样的模拟过程。因此，本章先讲物理机器必然存在的“供电、时钟、复位”关系；从处理器被释放复位
开始，再进入可以由 QEMU 和 SeaBIOS 源码逐条定位的软件故事。

电源键只是一次开机请求
----------------------

电源键通常不直接连接到 CPU 的“开始执行”输入。按下它以后，首先收到请求的是平台电源管理逻辑。
在真实 PC 中，这部分逻辑可能分布在嵌入式控制器、芯片组、电源管理控制器和电源供应器中。

平台接下来要完成一组有先后关系的动作：

* 打开待机电源之外的主要电压轨；
* 等待电压调节器报告输出稳定；
* 启动并稳定处理器、芯片组和总线需要的时钟；
* 让相关设备保持在复位状态，避免它们在供电和时钟不稳定时开始工作；
* 在最低启动条件满足后，释放处理器复位。

这些动作的具体信号名和时序属于主板实现。对后面的软件来说，最重要的结果只有一个：在复位释放之前，
CPU 不能从任意地址继续执行；复位释放之后，CPU 必须从架构规定的状态开始取指。

QEMU 中的“上电”是什么
--------------------

当前主线运行在 QEMU q35 虚拟平台上。宿主机早已完成真实供电，因此 QEMU 不需要模拟电压轨缓慢上升。
它完成的是同一件事的软件模型：

* 创建 q35 芯片组和外围设备的虚拟状态；
* 分配客户机物理内存；
* 把 SeaBIOS 固件映像放入虚拟地址空间的 ROM 区域；
* 把虚拟 CPU 放入 x86 复位状态；
* 开始运行负责启动的虚拟 CPU。

多处理器机器中，启动故事先沿 bootstrap processor，也就是 BSP 展开。其他处理器不会与 BSP 一起执行
同一条固件主线；它们会在后续阶段通过专门的启动协议加入。SeaBIOS 源码也为后续处理器启动保留了独立的
``entry_smp`` 入口。本章只跟随 BSP。

复位不是调用一个 reset 函数
--------------------------

处理器复位是一组由架构定义的状态变化。它不依赖栈，也不是某段普通软件调用的函数。

复位释放后，当前环境具有几个决定性的特征：

* CPU 执行 16 位指令；
* 保护模式尚未开启；
* 分页尚未开启；
* 64 位 long mode 尚未开启；
* 普通软件栈尚未建立；
* DRAM 不能因为“机器已经开机”就被默认视为可用；
* CPU 不知道磁盘、GRUB 和 Linux 位于哪里。

处理器此刻能做的第一件事，是按照复位状态中的 ``CS`` 和指令指针发起取指。

第一条指令为什么位于 0xfffffff0
-------------------------------

现代 x86 处理器的传统复位路径把代码段和指令指针设置成下面的状态：

::

   CS 可见选择子 = 0xf000
   CS 隐藏基址   = 0xffff0000
   RIP/EIP       = 0xfff0

CPU 形成取指地址时使用隐藏的段基址加指令偏移：

::

   0xffff0000 + 0x0000fff0 = 0xfffffff0

因此，复位后的第一条指令位于物理地址：

::

   0xfffffff0

它距离 4 GiB 边界只有 16 字节。

这里不能套用普通实模式中常见的：

::

   physical = CS × 16 + IP

直接计算。按照可见的 ``CS = 0xf000`` 和 ``IP = 0xfff0``，普通公式只能得到 ``0x000ffff0``。
复位状态特殊之处就在于：``CS`` 的可见部分是 ``0xf000``，处理器内部缓存的段基址却是
``0xffff0000``。这个隐藏基址使第一次取指落在 4 GiB 顶部，而不是传统 1 MiB 边界附近。

CPU 并不知道那里叫 BIOS
----------------------

CPU 只发出对 ``0xfffffff0`` 的取指请求。它不知道这个地址属于“BIOS”，也不会自动访问磁盘。
地址请求最终返回什么字节，由平台的物理地址映射决定。

真实机器通常通过芯片组地址译码，把 SPI flash 中的一部分固件内容映射到处理器复位入口所在的高地址窗口。
QEMU 则用虚拟内存区域完成同样的可见结果：SeaBIOS 的固定 ROM 内容出现在复位向量所指向的位置。

这一步存在两个互相独立的约定：

#. x86 架构规定 CPU 从 ``0xfffffff0`` 取第一条指令；
#. 平台规定访问 ``0xfffffff0`` 时返回固件映像中的哪些字节。

只有第一项，CPU 会取到空洞或错误设备；只有第二项，CPU 又不知道何时从那里开始执行。两项拼在一起，
处理器才能进入固件。

SeaBIOS 怎样把代码放到复位向量
----------------------------

本章固定 SeaBIOS 源码提交：

::

   c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf

SeaBIOS 在 ``src/romlayout.S`` 中使用固定地址段放置传统 BIOS 入口。文件末尾明确写着：

.. code-block:: asm

           ORG 0xfff0 // Power-up Entry Point
           .global reset_vector
   reset_vector:
           ljmpw $SEG_BIOS, $entry_post

``ORG 0xfff0`` 表示这段代码必须位于固定 BIOS 区域的 ``0xfff0`` 偏移。平台把这部分 ROM 同时暴露到
处理器复位所需的高地址窗口后，``reset_vector`` 的机器码正好出现在 ``0xfffffff0``。

CPU 取到的第一条固件指令不是初始化内存、枚举 PCI 或寻找磁盘，而是一条 16 位远跳转：

::

   ljmpw $SEG_BIOS, $entry_post

为什么复位向量只放一条跳转
------------------------

从 ``0xfffffff0`` 到 32 位地址空间末尾只剩 16 字节。这里不适合放置完整初始化逻辑。
固件通常只在复位向量放一个极小的跳板，把 CPU 送到 ROM 中空间更充足的位置。

SeaBIOS 的 ``ljmpw`` 是一条立即数远跳转。它同时装入：

* 新的 ``CS``；
* 新的 ``IP``。

SeaBIOS 的 ``src/config.h`` 定义：

.. code-block:: c

   #define BUILD_BIOS_ADDR 0xf0000
   #define BUILD_BIOS_SIZE 0x10000
   #define SEG_BIOS        0xf000

``romlayout.S`` 又把 ``entry_post`` 固定在：

.. code-block:: asm

           ORG 0xe05b
   entry_post:
           cmpl $0, %cs:HaveRunPost
           jnz entry_resume
           ENTRY_INTO32 _cfunc32flat_handle_post

因此，远跳转装入的目标是：

::

   CS = 0xf000
   IP = 0xe05b

远跳转之后，``CS`` 被正常重新装载，复位时那个特殊的隐藏基址不再继续使用。在 16 位实模式地址规则下：

::

   0xf000 × 16 + 0xe05b = 0x000fe05b

控制权于是从高地址复位别名：

::

   0xfffffff0

跳到传统 BIOS 低地址窗口中的：

::

   0x000fe05b

高地址复位窗口和低端 ``0xf0000`` BIOS 区域返回的是同一份固件固定代码的对应内容。
第一次取指必须依赖高地址复位映射；完成远跳转后，SeaBIOS 就可以按传统 F-segment 布局继续执行。

第一条指令完成了什么
------------------

这条远跳转没有初始化 DRAM，没有配置 PCI，也没有找到 GRUB。它完成的是更早的一次边界转换：

* CPU 从架构规定的特殊复位 ``CS`` 缓存状态离开；
* 代码段被重新装入 SeaBIOS 期望的 ``0xf000`` 段；
* 指令指针落到 SeaBIOS 的正式开机入口 ``entry_post``；
* 后续固件代码终于拥有足够空间建立自己的运行环境。

SeaBIOS 文档把这一段控制流概括为：模拟器让 CPU 在 16 位模式下从复位向量开始执行，
``reset_vector`` 调用 ``entry_post``，随后 ``entry_post`` 再把执行带入 32 位的
``post.c:handle_post()``。本章只走到 ``entry_post``，模式切换和 ``handle_post()`` 留给下一段故事。

本章结束时的机器状态
------------------

控制权目前走过：

::

   开机请求
   → 平台建立最低供电和时钟条件
   → 释放 BSP 复位
   → CS.base 0xffff0000 + RIP 0xfff0
   → 物理地址 0xfffffff0
   → SeaBIOS reset_vector
   → 远跳转到 f000:e05b
   → 物理地址 0x000fe05b
   → SeaBIOS entry_post

此刻：

* 当前执行者：SeaBIOS；
* 当前 CPU：BSP；
* 指令环境：16 位启动环境；
* 当前代码位置：传统 BIOS F-segment；
* 当前入口：``src/romlayout.S:entry_post``；
* DRAM：尚不能假设已经完成可用初始化；
* GRUB：尚未被搜索或装入；
* Linux：尚未出现在内存中。

第一章在这里结束。下一段控制流从 ``entry_post`` 的第一条比较指令开始：SeaBIOS 要先判断这究竟是一次
真正的冷启动，还是已经运行过 POST 后发生的恢复或重启，然后才会建立进入 32 位 C 代码所需的环境。

资料
----

* `Intel® 64 and IA-32 Architectures Software Developer’s Manual <https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html>`_；
* `SeaBIOS execution and code flow <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/docs/Execution_and_code_flow.md>`_；
* `SeaBIOS src/romlayout.S <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/romlayout.S>`_；
* `SeaBIOS src/config.h <https://github.com/coreboot/seabios/blob/c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf/src/config.h>`_。