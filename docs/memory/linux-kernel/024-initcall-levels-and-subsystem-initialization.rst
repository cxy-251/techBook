第024章：Initcall 层级与子系统初始化
===================================

本章必须记住
------------

#. 内核进入 ``start_kernel()`` 后，仍有大量分散在各子系统中的初始化函数尚未执行。
#. Initcall 机制把这些分散函数在编译和链接阶段登记到特定 section，再由启动主线按层级扫描执行。
#. ``core_initcall(fn)``、``subsys_initcall(fn)``、``fs_initcall(fn)`` 等宏不会在定义位置直接调用 ``fn``，而是登记函数指针。
#. Initcall 的真实调用点来自链接脚本中的 section 排列，以及 ``init/main.c`` 中的区间扫描器。
#. 常见层级从早到晚包括 early、pure、core、postcore、arch、subsys、fs、rootfs、device 和 late。
#. 越早的 initcall 能依赖的设施越少；越晚的 initcall 通常可以依赖更多已经注册的框架、对象和驱动资源。
#. ``early_initcall()`` 在普通 initcall 层级之前执行，适合依赖面很小且必须早于 SMP 等阶段完成的初始化。
#. ``pure_initcall()``、``core_initcall()`` 和 ``postcore_initcall()`` 主要建立通用核心设施和内部状态。
#. ``arch_initcall()`` 把架构相关初始化放入普通 initcall 时间线。
#. ``subsys_initcall()`` 常用于建立总线、class、协议框架和其它供后续使用的子系统基础设施。
#. ``fs_initcall()`` 常用于文件系统和相关基础注册，``rootfs_initcall()`` 位于 fs 与 device 阶段之间的特殊边界。
#. ``device_initcall()`` 是大量内建设备驱动注册入口的常见层级；驱动注册后才可能与已有设备匹配并触发 probe。
#. ``late_initcall()`` 位于启动后段，适合依赖前面大多数初始化已经尝试完成的收尾工作。
#. Initcall 层级只提供粗粒度先后关系，它不是完整依赖管理系统。
#. 两个函数位于同一 initcall 层级时，执行顺序通常受对象文件和链接顺序影响。
#. Kbuild 中目录和 ``obj-y`` 列表的顺序可能影响同层 initcall 排列，因此调整 Makefile 顺序可能改变启动行为。
#. Initcall section 的排列由链接脚本决定；``do_initcalls()`` 按层级遍历，``do_initcall_level()`` 扫描当前区间，``do_one_initcall()`` 执行单个函数。
#. ``do_one_initcall()`` 会记录返回值，并检查初始化函数是否错误地留下 preempt count 或 IRQ 状态变化。
#. Initcall 返回负错误码通常表示当前初始化失败；是否影响整个系统继续启动，取决于该功能是否为后续必需依赖。
#. 一个 initcall 返回成功，只表示该初始化函数完成了自己的返回契约，不保证所有异步工作、设备 probe 和消费者已经完成。
#. 启动依赖应按 provider、framework 和 consumer 阅读：provider 发布资源，framework 提供注册与查找，consumer 使用资源。
#. Provider 的 initcall 已执行不等于资源一定可用；还要检查注册结果、错误返回和对象是否已经进入可查找集合。
#. 驱动 probe 发现依赖资源暂时未准备时，可以返回 ``-EPROBE_DEFER``，driver core 会把设备放入延迟 probe 路径并在以后重试。
#. Deferred probe 解决资源暂时未到达的问题，不能掩盖永久缺失、配置错误、设备树错误或错误的依赖描述。
#. 重复 ``-EPROBE_DEFER`` 需要继续查 provider 是否注册、依赖描述是否正确以及资源是否被错误码永久拒绝。
#. 内建代码的 initcall 随 ``vmlinux`` 启动时执行；模块的初始化函数在模块加载时执行，不能只看 ``module_init()`` 宏就推断启动时间。
#. 标记为 ``__init`` 的代码和数据在初始化完成后可以被释放，长期回调和对象指针不能继续引用它们。
#. ``initcall_debug`` 可以输出每个 initcall 的调用、返回值和耗时，是定位启动卡顿与失败的核心证据之一。

必背路径
--------

Initcall 从源码到执行：

::

   源码使用 xxx_initcall(fn)
   → 宏把 fn 指针放入对应 .initcall*.init section
   → Kbuild 决定对象文件和链接顺序
   → 链接脚本按层级排列 initcall sections
   → start_kernel() 推进到基本初始化阶段
   → do_initcalls() 依次遍历各 level
   → do_initcall_level() 扫描函数指针区间
   → do_one_initcall() 调用 fn 并记录结果

常见层级顺序：

::

   early
   → pure
   → core
   → postcore
   → arch
   → subsys
   → fs
   → rootfs
   → device
   → late

Provider 与 consumer：

::

   provider initcall 建立资源对象
   → 把资源注册到 framework
   → consumer driver 注册
   → driver core 匹配设备与驱动
   → probe 查找 provider 资源
   → 资源可用则完成初始化
   → 资源暂时缺失则返回 -EPROBE_DEFER
   → driver core 在以后重新尝试 probe

定位 initcall 顺序：

::

   找初始化函数使用的宏
   → 找宏对应 section
   → 找链接脚本中的 section 位置
   → 检查同层对象文件链接顺序
   → 用 initcall_debug 验证实际调用和耗时
   → 检查返回值与后续依赖

必须区分
--------

Initcall 层级与精确依赖
   层级只提供启动阶段的大方向；真实依赖还要由对象注册、固件描述、资源查找和驱动模型表达。

同层级与同时执行
   同一层级表示处于同一阶段，不表示函数并发执行，也不表示顺序无关；通常仍按链接后的排列扫描。

Initcall 成功与子系统完全可用
   返回成功只覆盖初始化函数自己的契约；异步任务、设备匹配、probe 和消费者可能仍未完成。

内建初始化与模块初始化
   内建代码在启动 initcall 路径执行；模块代码在模块加载路径执行。

Deferred probe 与永久失败
   Deferred probe 表示资源可能稍后出现；永久缺失、错误描述和真实硬件失败需要返回并处理对应错误。

一句话结论
----------

Initcall 用链接 section 把分散的初始化函数排成粗粒度启动顺序；真正的启动正确性仍取决于 provider、framework、consumer 的对象依赖和失败处理。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 24，Initcall Levels and Subsystem Initialization；
* 源文件：``docs/LinuxK/Part_05_Boot_Sequence_Initcalls_and_Early_Kernel_Initialization/Chapter_024_Initcall_Levels_and_Subsystem_Initialization.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_05_Boot_Sequence_Initcalls_and_Early_Kernel_Initialization/Chapter_024_Initcall_Levels_and_Subsystem_Initialization.md>`_。
