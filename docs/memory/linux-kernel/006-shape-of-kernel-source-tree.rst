第006章：Linux 内核源码树的结构
===============================

本章必须记住
------------

#. Linux 内核顶层目录首先表示工程归属和维护边界，不表示一次请求的完整运行顺序。
#. 一条运行路径可以跨越 ``arch/``、``kernel/``、``mm/``、``fs/``、``net/`` 和 ``drivers/`` 等多个目录。
#. ``kernel/`` 主要保存调度、进程生命周期、时间、信号、同步和核心基础设施等通用控制逻辑。
#. ``mm/`` 主要保存物理页、虚拟内存、页表、缺页、slab、映射和回收等内存管理逻辑。
#. ``fs/`` 主要保存 VFS、文件对象、inode、目录项、挂载、读写路径和具体文件系统实现。
#. ``net/`` 主要保存 socket、协议栈、路由、网络包、队列和网络命名空间相关逻辑。
#. ``drivers/`` 主要保存总线、控制器、具体硬件驱动、``probe``、中断和 DMA 等设备逻辑。
#. ``arch/`` 保存 CPU 架构相关的启动、系统调用入口、异常、中断、页表格式、上下文切换和架构专用实现。
#. ``include/linux/`` 主要保存内核内部共享的类型、声明、宏和内联接口。
#. ``include/uapi/`` 主要保存用户态可见的 ABI 定义，例如系统调用参数、ioctl、netlink 和公开常量。
#. ``arch/*/include/asm/`` 保存架构相关的内核接口；``arch/*/include/uapi/`` 保存架构相关的用户态接口。
#. ``include/generated/`` 和架构生成头文件由构建过程产生，内容受架构、Kconfig 和构建规则影响。
#. ``Documentation/`` 保存官方设计说明、接口文档和开发规则，可以帮助建立源码地图，但不能单独证明当前运行路径。
#. ``scripts/`` 主要保存构建、检查和代码生成脚本；``tools/`` 主要保存 perf、测试和其他用户态辅助工具。
#. 通用代码表达多个架构共享的对象和控制流程；架构代码处理寄存器、异常、页表、指令和调用约定等 CPU 差异。
#. 阅读源码时应先找通用对象和子系统归属，只有遇到系统调用入口、异常、页表、原子操作或用户访问等架构能力时再进入 ``arch/``。

必背路径
--------

定位一个源码问题时采用以下顺序：

::

   根据问题判断所属子系统
   → 找到对应顶层目录
   → 在 include/linux 中找到核心对象和内部接口
   → 判断是否涉及用户态 ABI
   → 判断是否依赖具体 CPU 架构
   → 查阅 Documentation 中的对应说明
   → 沿对象和回调跨目录追踪实际调用路径

以 ``read()`` 为例：

::

   架构系统调用入口位于 arch/
   → 通用读写入口位于 fs/
   → struct file 和 file_operations 位于 include/linux/
   → 用户缓冲区处理依赖 mm/ 与架构用户访问能力
   → 具体实现进入文件系统、管道、套接字或 drivers/

必须区分
--------

目录归属与调用顺序
   目录说明代码由哪个工程边界负责；调用顺序由函数、对象、回调和状态决定。

通用代码与架构代码
   通用代码表达 Linux 统一机制；架构代码实现 CPU 和平台相关细节。

内核内部接口与用户态 ABI
   ``include/linux/`` 面向内核内部；``include/uapi/`` 面向用户程序和工具链。

手写头文件与生成头文件
   手写头文件是源码接口；生成头文件是某次配置和构建产生的结果。

一句话结论
----------

Linux 源码目录是工程地图：先用目录确定归属，再用对象、接口和回调还原真正的跨目录运行路径。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 6，The Shape of the Kernel Source Tree；
* 源文件：``docs/LinuxK/Part_02_Kernel_Source_Tree_and_Code_Navigation/Chapter_006_The_Shape_of_the_Kernel_Source_Tree.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_02_Kernel_Source_Tree_and_Code_Navigation/Chapter_006_The_Shape_of_the_Kernel_Source_Tree.md>`_。
