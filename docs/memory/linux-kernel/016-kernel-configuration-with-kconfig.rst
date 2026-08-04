第016章：使用 Kconfig 配置 Linux 内核
=====================================

本章必须记住
------------

#. Kconfig 决定哪些内核功能可以被选择，以及这些功能最终取 ``y``、``m`` 还是 ``n``。
#. 源码树中存在某个驱动、文件系统或调试功能，只能证明它可以参与构建，不能证明目标内核已经包含它。
#. Kconfig 文件中定义的符号通常不带 ``CONFIG_`` 前缀；写入 ``.config``、Makefile 和 C 代码后通常表现为 ``CONFIG_*``。
#. ``.config`` 是目标构建的最终配置输入；分析某个内核能力时，应查看目标构建使用的配置，而不是凭源码目录或另一台机器的配置判断。
#. ``bool`` 符号只有 ``y`` 和 ``n``；``tristate`` 符号具有 ``y``、``m``、``n`` 三种状态。
#. ``y`` 表示功能以内建代码进入内核镜像；``m`` 表示功能构建成可加载模块；``n`` 表示功能不进入目标构建结果。
#. ``CONFIG_FOO=m`` 并不表示功能已经可用；系统还必须具有匹配当前内核版本的模块文件、依赖信息和加载路径。
#. ``depends on`` 限制一个符号在什么条件下可见或可选；依赖不满足时，用户通常不能直接启用该符号。
#. ``default`` 只在用户没有作出更高优先级选择且依赖允许时提供默认值，它不能覆盖不满足的依赖。
#. ``select`` 从当前符号反向提高另一个符号的值，并可能绕过被选符号自身的依赖检查，因此只应选择没有复杂依赖的底层辅助符号。
#. ``imply`` 是较弱的反向建议；它可以提高目标符号的默认倾向，但仍允许其它依赖和用户选择限制最终结果。
#. 配置项不可见不等于它不存在；它可能被菜单层级、架构条件、依赖表达式或其它符号隐藏。
#. ``make menuconfig`` 适合搜索和人工调整符号；搜索结果可以显示符号位置、依赖和当前可选状态。
#. ``make defconfig`` 从目标架构的默认配置建立基线；默认配置只是起点，不保证覆盖当前机器全部硬件和用途。
#. ``make oldconfig`` 或 ``olddefconfig`` 用于把旧配置迁移到新源码；迁移后仍要审查新增、改名和默认值改变的符号。
#. ``make localmodconfig`` 根据当前系统已加载模块裁剪配置，可能删除当前未加载但以后仍需要的驱动，不应把结果直接当成通用配置。
#. Kconfig 结果会生成供 Make 使用的 ``include/config/auto.conf``，以及供 C 编译使用的 ``include/generated/autoconf.h``。
#. ``IS_BUILTIN(CONFIG_FOO)`` 判断功能是否内建，``IS_MODULE(CONFIG_FOO)`` 判断是否为模块，``IS_ENABLED(CONFIG_FOO)`` 判断功能是否为内建或模块。
#. ``IS_REACHABLE(CONFIG_FOO)`` 还考虑当前编译单元是否能实际调用目标实现，避免内建代码直接依赖尚未加载的模块实现。
#. 配置会改变编译单元、条件分支、结构体字段、调试检查、模块集合和最终运行能力，因此源码阅读必须绑定具体配置。

必背路径
--------

从功能名称追踪到目标内核能力：

::

   在 Kconfig 中找到符号定义
   → 确认符号类型、依赖、默认值和反向依赖
   → 查看目标构建的 .config 最终值
   → 查看 include/config/auto.conf 和 autoconf.h 的生成结果
   → 查看 Kbuild 怎样消费 CONFIG_* 值
   → 判断代码进入 vmlinux、进入 .ko，还是被排除
   → 再检查模块文件、加载状态和运行时路径

三态配置的构建结果：

::

   CONFIG_FOO=y
   → 对象进入 built-in 构建链
   → 最终链接进内核镜像

   CONFIG_FOO=m
   → 对象构建成模块
   → 运行时需要匹配模块和加载机制

   CONFIG_FOO=n
   → 对象不进入本次目标构建

配置迁移的基本顺序：

::

   保存旧配置
   → 固定新源码版本和输出目录
   → 执行 olddefconfig 或 oldconfig
   → 检查新增和变化的符号
   → 保存归一化后的最终 .config
   → 再开始构建

必须区分
--------

源码存在与功能存在
   源码存在只说明功能具有构建来源；目标配置和构建产物决定运行内核是否包含该功能。

``y`` 与 ``m``
   ``y`` 随内核镜像存在；``m`` 依赖模块文件、符号、签名、依赖关系和加载时机。

``depends on`` 与 ``select``
   ``depends on`` 限制当前符号的可选条件；``select`` 由当前符号反向强制另一个符号，不能用来掩盖复杂依赖。

配置意图与最终配置
   人工选择、defconfig 或旧配置只是输入意图；Kconfig 求值后的最终 ``.config`` 才进入构建。

``IS_ENABLED`` 与 ``IS_REACHABLE``
   ``IS_ENABLED`` 判断功能是否为 ``y`` 或 ``m``；``IS_REACHABLE`` 还判断当前代码能否实际到达模块实现。

一句话结论
----------

Linux 内核功能先由 Kconfig 决定是否存在以及以何种形态存在，再由 Kbuild 把最终配置转换成内建代码、模块或被排除的实现。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 16，Kernel Configuration with Kconfig；
* 源文件：``docs/LinuxK/Part_04_Kconfig_Kbuild_Modules_and_Kernel_Images/Chapter_016_Kernel_Configuration_with_Kconfig.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_04_Kconfig_Kbuild_Modules_and_Kernel_Images/Chapter_016_Kernel_Configuration_with_Kconfig.md>`_。
