第024章：Initcall 层级与子系统初始化
===================================

核心知识点
----------

Initcall 登记分散的初始化入口
   内核各子系统的初始化函数分布在不同目录。``core_initcall()``、``subsys_initcall()``、``fs_initcall()`` 等宏把函数指针放入特定链接 section，而不是在定义位置直接调用函数。

链接 section 决定阶段顺序
   链接脚本按 early、pure、core、postcore、arch、subsys、fs、rootfs、device、late 等层级排列 initcall section，启动主线再依次扫描这些区间。

执行器把 section 转成真实调用
   ``do_initcalls()`` 遍历层级，``do_initcall_level()`` 扫描当前函数指针区间，``do_one_initcall()`` 调用单个初始化函数并记录返回值及部分上下文异常。

层级表达粗粒度依赖
   越早的 initcall 能依赖的设施越少；越晚的阶段通常可以依赖更多已经建立的框架和对象。层级适合表达“核心设施先于子系统、子系统先于大量驱动”的总体顺序。

同层顺序受链接结果影响
   两个函数位于同一层级时，先后通常由对象文件和 Kbuild 链接顺序决定。同层并不表示同时执行，也不表示二者没有顺序依赖。

初始化依赖通过对象可见性成立
   Provider 创建并注册资源，framework 提供登记和查找，consumer 再获取资源。Provider 的 initcall 已返回成功，不一定表示资源已经对所有消费者可见或异步工作已经完成。

Deferred probe 处理暂时缺失的资源
   Consumer 驱动在依赖尚未准备好时可返回 ``-EPROBE_DEFER``，driver core 稍后重试。它适用于资源可能晚到的情况，不能替代永久缺失、配置错误或硬件失败的诊断。

内建与模块具有不同初始化时间线
   内建代码的 initcall 随 ``vmlinux`` 启动执行；模块初始化函数在模块加载时执行。``module_init()`` 的实际时机必须结合代码是 ``y`` 还是 ``m`` 判断。

关键路径
--------

Initcall 从源码到执行：

::

   源码使用 xxx_initcall(fn)
   → fn 指针进入对应 .initcall*.init section
   → Kbuild 决定对象和链接顺序
   → 链接脚本排列各层 section
   → do_initcalls() 遍历层级
   → do_initcall_level() 扫描当前区间
   → do_one_initcall() 调用 fn 并记录结果

Provider 与 consumer：

::

   provider 初始化并创建资源
   → 把资源注册到 framework
   → consumer 驱动注册
   → driver core 匹配设备与驱动
   → probe 查找依赖资源
   → 可用时完成初始化
   → 暂时缺失时返回 -EPROBE_DEFER
   → 稍后重新 probe

概念辨析
--------

Initcall 层级与精确依赖
   层级只提供启动阶段的大方向；精确依赖仍由对象注册、资源查找、固件描述和驱动模型表达。

同层级与同时执行
   同层级表示处于同一初始化阶段；函数通常仍按链接后的顺序依次扫描执行。

Initcall 成功与子系统完全可用
   返回成功只覆盖当前函数的合同；异步任务、设备匹配、probe 和消费者状态可能仍未完成。

内建初始化与模块初始化
   内建初始化发生在启动 initcall 路径；模块初始化发生在运行时模块加载路径。

Deferred probe 与永久失败
   Deferred probe 表示依赖可能稍后出现；永久缺失、错误描述和真实硬件故障需要返回并处理相应错误。

本章结论
--------

Initcall 通过链接 section 建立粗粒度启动顺序；真正的初始化正确性取决于资源对象何时被发布、查找、使用以及失败后如何处理。