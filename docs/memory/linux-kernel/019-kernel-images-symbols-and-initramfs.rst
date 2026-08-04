第019章：Linux 内核镜像、符号与 initramfs
=========================================

本章必须记住
------------

#. 一次内核构建会产生多种文件，它们分别承担链接、启动、符号解释、模块交付和早期用户空间等职责。
#. ``vmlinux`` 是内建内核对象最终链接得到的 ELF 文件，通常包含完整段布局、符号以及可选调试信息。
#. ``vmlinux`` 适合使用 ``readelf``、``nm``、``objdump``、``gdb`` 和崩溃分析工具检查，不一定是 bootloader 直接加载的文件。
#. ``built-in.a`` 中的对象最终参与 ``vmlinux`` 链接；配置为模块的代码不会直接进入 ``vmlinux``。
#. 链接脚本决定 ``.text``、``.rodata``、``.data``、``.bss``、初始化段和 per-CPU 段等区域的排列。
#. ``bzImage``、``Image``、``zImage`` 等是架构相关启动镜像，文件格式、入口和加载要求由目标架构的启动协议决定。
#. x86 常使用 ``arch/x86/boot/bzImage``；arm64 常使用 ``arch/arm64/boot/Image``，不能把一种架构的镜像规则套到另一种架构。
#. x86 的 ``bzImage`` 不只是简单压缩的 ``vmlinux``，还包含启动头、早期入口和解压相关代码。
#. 发行版中的 ``/boot/vmlinuz-*`` 通常是可启动内核镜像的命名约定，不等同于构建树中的未压缩 ``vmlinux``。
#. ``System.map`` 是某次构建产生的地址到符号名称映射，用于把崩溃地址、函数地址和变量地址还原成符号。
#. ``kallsyms`` 是内核内部的运行时符号设施；启用相关配置后，Oops、panic、调用栈和 ``/proc/kallsyms`` 可以显示符号名称。
#. ``System.map``、``vmlinux``、模块调试文件和运行内核必须来自同一次匹配构建，否则地址解析可能得到错误结论。
#. KASLR、模块重定位和地址隐藏策略会影响运行时地址；分析时必须结合匹配构建和实际运行地址环境。
#. ``initramfs`` 通常是一个压缩的 cpio 归档，由 bootloader 与内核镜像一起加载，或在构建时直接嵌入内核。
#. 内核在启动早期把 initramfs 解包到内存中的 rootfs，并通常执行其中的 ``/init`` 作为早期用户空间入口。
#. 早期用户空间可以加载根文件系统所需模块、等待设备、解锁加密磁盘、组装 RAID/LVM、加载固件并挂载真正根文件系统。
#. 真正根文件系统准备完成后，早期用户空间通常使用 ``switch_root`` 等机制进入最终用户空间。
#. ``initrd`` 历史上通常表示可挂载的临时块设备镜像；``initramfs`` 是解包到 rootfs 的 cpio 文件集合，二者机制不同。
#. 根文件系统依赖的驱动若构建为模块，就必须在挂载根文件系统之前能够从 initramfs 或其它早期介质取得。
#. 驱动若已经内建进内核镜像，启动时不需要对应 ``.ko`` 才能执行其内建初始化路径。
#. ``/lib/modules/<kernel-release>/`` 必须与运行内核的 release 和构建接口匹配；错误模块目录会导致早期加载失败。
#. initramfs 内容必须与目标内核配置、模块依赖、存储布局、加密方式和启动参数一致。
#. bootloader 配置必须把正确的启动镜像、initramfs 和命令行组合在一起；仅生成新 ``vmlinux`` 不表示机器已经使用新内核启动。
#. ``uname -r`` 只能确认运行内核的 release 字符串；确认具体构建还需要配置、符号、构建标识和启动文件等证据。
#. 一个可启动内核实际上是镜像、模块、initramfs、固件、启动参数和 bootloader 条目的组合，不是单个文件。

必背路径
--------

从源码到启动镜像：

::

   Kconfig 与 Kbuild 选择内建对象
   → 各目录 built-in.a
   → 链接脚本组织内核段
   → 链接生成 vmlinux ELF
   → 架构 boot 规则提取、压缩或包装负载
   → 生成 bzImage、Image 或其它启动格式
   → bootloader 按架构协议加载并进入早期入口

符号分析路径：

::

   运行日志出现地址或 function+offset
   → 确认运行内核 release 和构建身份
   → 取得匹配的 vmlinux、System.map 和模块符号
   → 处理 KASLR 或模块重定位边界
   → 将地址解析为符号和源码位置
   → 回到调用链与对象状态判断原因

initramfs 启动路径：

::

   bootloader 加载内核镜像和 initramfs
   → 内核解包 initramfs 到内存 rootfs
   → 启动早期用户空间 /init
   → 加载存储、文件系统和安全相关模块
   → 发现并准备真正根设备
   → 挂载最终根文件系统
   → switch_root 进入正式用户空间

验证新内核是否真正启动：

::

   检查构建产物
   → 检查 /boot 中安装的启动镜像
   → 检查 bootloader 条目和 initramfs
   → 启动目标条目
   → 检查 uname -r、配置和模块目录
   → 使用匹配符号确认构建身份

必须区分
--------

``vmlinux`` 与启动镜像
   ``vmlinux`` 是链接后的 ELF；启动镜像是符合目标架构启动协议、供 bootloader 使用的文件。

``vmlinux`` 与 ``vmlinuz``
   ``vmlinux`` 通常是未压缩调试友好的链接产物；``vmlinuz`` 通常是发行版对可启动压缩镜像的文件命名。

``System.map`` 与 ``kallsyms``
   ``System.map`` 是构建输出文件；``kallsyms`` 是运行内核内部的符号解析设施。

initramfs 与最终根文件系统
   initramfs 是临时早期用户空间，用于准备最终根文件系统；它通常不是系统长期运行的根文件系统。

内核镜像更新与系统启动更新
   生成新镜像只是构建完成；还必须安装匹配模块和 initramfs，并更新 bootloader 的实际启动入口。

一句话结论
----------

``vmlinux`` 描述链接后的内核程序，架构镜像负责启动，符号文件负责解释地址，initramfs 负责在最终根文件系统可用前提供早期用户空间。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 19，Kernel Images, vmlinux, bzImage, and initramfs；
* 源文件：``docs/LinuxK/Part_04_Kconfig_Kbuild_Modules_and_Kernel_Images/Chapter_019_Kernel_Images_vmlinux_bzImage_and_initramfs.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_04_Kconfig_Kbuild_Modules_and_Kernel_Images/Chapter_019_Kernel_Images_vmlinux_bzImage_and_initramfs.md>`_。
