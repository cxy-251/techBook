第017章：使用 Kbuild 构建 Linux 内核
===================================

本章必须记住
------------

#. Kbuild 把 Kconfig 的配置结果转换成目录递归、对象编译、内建链接、模块生成和符号检查。
#. 一个 ``.c`` 文件存在于源码树中，不表示它会进入目标内核；必须继续查看父目录和当前目录的 Kbuild 规则。
#. 内核构建规则由顶层 ``Makefile``、``.config``、架构 Makefile、``scripts/Makefile.*`` 和各目录的 ``Makefile`` 或 ``Kbuild`` 共同组成。
#. 顶层 ``Makefile`` 负责全局构建阶段和目标调度；各子目录规则决定当前目录具体编译哪些对象。
#. ``arch/$(SRCARCH)/Makefile`` 提供目标架构的编译参数、链接规则和启动镜像目标。
#. ``obj-y`` 表示对象进入当前 built-in 构建链；这些对象最终通过各目录的 ``built-in.a`` 参与 ``vmlinux`` 链接。
#. ``obj-m`` 表示对象进入模块构建链，并在模块后处理完成后生成 ``.ko`` 文件。
#. ``obj-$(CONFIG_FOO)`` 根据配置值自动变成 ``obj-y``、``obj-m`` 或空规则。
#. 父目录决定子目录以何种形态进入构建；子目录中的 ``obj-y`` 必须结合父目录上下文判断，不能看到 ``obj-y`` 就断定对象一定进入 ``vmlinux``。
#. 复合对象可以用 ``foo-y`` 或 ``foo-objs`` 指定由哪些 ``.o`` 文件链接成 ``foo.o``。
#. ``foo-$(CONFIG_BAR)`` 可以在主体对象已经启用后，继续按更细的配置选择内部对象。
#. Kbuild 对象列表的顺序会影响链接顺序；对于 initcall 等依赖链接排列的代码，调整 Makefile 顺序可能改变启动行为。
#. ``include/config/auto.conf`` 把配置结果提供给 Make；``include/generated/autoconf.h`` 把配置宏提供给 C 编译过程。
#. 生成头文件、版本字符串、依赖文件和中间对象属于构建输出，不能当作人工维护源码直接编辑。
#. ``vmlinux`` 是内建对象最终链接出的内核 ELF；模块对象不进入 ``vmlinux``，而是独立生成 ``.ko``。
#. ``EXPORT_SYMBOL()`` 把符号开放给模块使用；``EXPORT_SYMBOL_GPL()`` 只允许声明兼容 GPL 许可的模块使用。
#. 模块引用未导出的内核符号时，即使源码能够编译，模块链接或加载仍会失败。
#. MODPOST 在模块后处理阶段检查未解析符号、模块元数据和部分 section mismatch 等问题。
#. ``Module.symvers`` 记录导出符号及相关信息；启用 ``CONFIG_MODVERSIONS`` 时还会包含用于版本匹配的 CRC。
#. 外部模块必须针对目标内核的构建目录和配置构建，常见入口是 ``make -C <kernel-build> M=$PWD modules``。
#. ``modules_prepare`` 可以准备外部模块所需的部分生成文件，但在启用模块版本校验时，它不替代一次完整内核构建产生的 ``Module.symvers``。
#. 构建成功只证明目标被生成；代码是否执行仍取决于初始化、模块加载、设备匹配和运行时输入。

必背路径
--------

从配置符号追踪到构建产物：

::

   .config 中确认 CONFIG_FOO=y/m/n
   → 查看父目录 obj-$(CONFIG_FOO) 规则
   → 进入对应子目录
   → 查看 obj-y、obj-m 和复合对象列表
   → 查看更细的 CONFIG_* 条件对象
   → y 路径生成 built-in.a 并链接进 vmlinux
   → m 路径经过 MODPOST 并生成 .ko
   → 检查最终镜像、模块和符号记录

内建对象构建链：

::

   源文件 .c
   → 编译为 .o
   → 按 obj-y 和复合对象规则组织
   → 合并进目录 built-in.a
   → scripts/link-vmlinux.sh 等链接流程
   → vmlinux

模块构建链：

::

   源文件 .c
   → 编译为模块对象
   → 解析导出符号和依赖
   → MODPOST 检查并生成模块元数据
   → 链接为 .ko
   → 安装后由 depmod 建立加载依赖索引

外部模块的基本入口：

::

   固定目标内核版本和构建目录
   → 确认目标配置与生成头文件
   → make -C <kernel-build> M=<module-source> modules
   → 检查 MODPOST 与未解析符号
   → 使用匹配目标内核的 .ko

必须区分
--------

运行时调用链与构建依赖链
   调用链说明代码执行时谁调用谁；构建链说明哪些文件被编译、组合和链接。

目录中的 ``obj-y`` 与最终内建
   当前目录的 ``obj-y`` 还受父目录进入方式控制，必须沿父目录规则向上确认。

``built-in.a`` 与 ``vmlinux``
   ``built-in.a`` 是目录级内建对象集合；``vmlinux`` 是所有内建链条完成最终链接后的内核 ELF。

编译通过与模块可加载
   编译通过不保证符号可解析、版本匹配、签名合格或初始化成功。

导出符号与普通全局符号
   普通全局符号不自动对模块可见；模块只能可靠引用内核明确导出的符号。

一句话结论
----------

Kbuild 是配置到产物的依赖图：父目录决定是否进入，子目录决定编译什么，built-in 链接成 ``vmlinux``，module 链经过符号检查生成 ``.ko``。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 17，Kernel Build System with Kbuild；
* 源文件：``docs/LinuxK/Part_04_Kconfig_Kbuild_Modules_and_Kernel_Images/Chapter_017_Kernel_Build_System_with_Kbuild.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_04_Kconfig_Kbuild_Modules_and_Kernel_Images/Chapter_017_Kernel_Build_System_with_Kbuild.md>`_。
