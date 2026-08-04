第020章：建立可复现的 Linux 内核构建
=====================================

本章必须记住
------------

#. 可复现内核构建要求构建输入被明确记录，使同样的输入能够再次得到可比较、可解释和可追溯的输出。
#. 位级完全一致是最严格的可复现结果；即使暂时不能做到位级一致，也必须能够解释每项差异来自哪个输入。
#. 源码输入至少包括上游 commit 或 tag、额外补丁、工作区状态以及 ``CONFIG_LOCALVERSION`` 或 ``LOCALVERSION``。
#. 只记录“Linux 6.x”不足以复现构建；同一版本名称可能对应不同补丁、不同 dirty 状态和不同本地版本后缀。
#. 工具链不只有编译器，还包括链接器、汇编器、``objcopy``、``strip``、``pahole``、Make、脚本语言、压缩工具和证书工具等。
#. 使用 LLVM 构建时，配置和后续构建阶段应保持相同的 ``LLVM=``、目标架构和交叉编译设置。
#. 配置记录必须保存 Kconfig 求值后的最终 ``.config``，同时记录它由 defconfig、olddefconfig、人工修改或其它流程怎样生成。
#. 时间戳、构建用户、构建主机、绝对路径、Git dirty 状态、随机种子、签名材料和 initramfs 文件时间都可能改变构建输出。
#. ``KBUILD_BUILD_TIMESTAMP``、``KBUILD_BUILD_USER`` 和 ``KBUILD_BUILD_HOST`` 可以把部分隐式环境输入变成明确输入。
#. 调试信息中可能写入源码和输出目录的绝对路径；需要位级复现时，可使用编译器的 prefix-map 机制映射为稳定路径。
#. 自动生成的模块签名密钥、证书序列、随机化种子或每次变化的 initramfs 内容会破坏位级复现，必须固定或显式记录。
#. ``O=<dir>`` 或 ``KBUILD_OUTPUT=<dir>`` 用于 out-of-tree 构建，把源码输入与构建输出隔离。
#. 一旦选择 ``O=``，配置、编译、模块、安装和检查命令都应使用同一个输出目录，不能混用源码树内外两套状态。
#. 源码树应保持可审计和尽量干净；构建目录应可以整体删除后从零重建。
#. 调试构建和生产构建必须使用独立配置、独立输出目录和独立交付标识，不能复用彼此的中间对象。
#. 调试构建通常启用调试符号、frame pointer、lockdep、KASAN、KCSAN、UBSAN、ftrace 和更多诊断检查。
#. 调试功能会改变代码布局、内存占用、时序和性能；某个问题只在生产构建出现或只在调试构建消失时，不能直接互相替代结论。
#. 生产构建关注稳定运行、体积、性能、安全策略和部署要求，但不应删除故障回溯所需的构建记录与匹配符号。
#. ``INSTALL_MOD_PATH`` 和 ``INSTALL_HDR_PATH`` 可以把模块与导出头文件安装到 staging 目录，而不是直接修改当前运行系统。
#. 内核镜像、模块目录、initramfs、固件、配置、``vmlinux``、``System.map`` 和调试符号必须作为同一构建集合管理。
#. ``/lib/modules/<kernel-release>/`` 的目录名必须与该构建生成的 kernel release 一致。
#. ``modules.order`` 记录模块构建顺序，``modules.builtin`` 记录已经内建进内核的模块名；它们属于构建结果证据。
#. 交付清单应记录源码指纹、最终配置、工具版本、构建变量、目标架构、内核 release、文件哈希和打包步骤。
#. 只保存一个 ``vmlinuz`` 文件无法可靠复盘构建，也无法保证模块、initramfs 和符号与它匹配。
#. 可复现性需要通过至少两次独立干净构建比较验证，不能仅凭构建脚本看起来相同就宣布完成。
#. 比较时应先检查文件哈希，再检查 ELF 段、符号、模块元数据、归档内容和构建清单，以定位非确定性来源。
#. 可重建的内核才能可靠进行回归测试、``git bisect``、崩溃分析、安全修复、稳定分支回溯和部署审计。

必背路径
--------

建立构建输入清单：

::

   固定源码 commit、补丁和工作区状态
   → 固定目标架构和工具链版本
   → 固定配置生成步骤与最终 .config
   → 固定 local version 和构建元数据
   → 固定证书、随机种子、固件和 initramfs 输入
   → 把全部输入写入构建 manifest

干净的构建目录结构：

::

   source/
   → 只保存版本控制下的源码与补丁

   build/debug/
   → 调试配置、中间对象、vmlinux 和模块

   build/production/
   → 生产配置、中间对象、镜像和模块

   artifacts/<build-id>/
   → 镜像、模块、头文件、符号、initramfs 和 manifest

一次可审计的构建：

::

   创建全新输出目录
   → 使用 O=<build-dir> 生成最终配置
   → 使用同一 O= 完成内核和模块构建
   → 把模块安装到 staging root
   → 把头文件安装到 staging headers
   → 收集镜像、vmlinux、System.map 和配置
   → 生成匹配 initramfs
   → 写工具版本、变量、哈希和文件清单

验证可复现性：

::

   在独立干净目录执行第一次构建
   → 在相同显式输入下执行第二次构建
   → 比较文件哈希
   → 比较 ELF、符号、模块和归档内容
   → 找出时间、路径、随机数或工具差异
   → 修正隐式输入后重新构建

部署一个完整构建集合：

::

   安装架构启动镜像
   → 安装匹配 kernel release 的模块目录
   → 生成并安装匹配 initramfs
   → 保存 vmlinux、System.map、.config 和调试符号
   → 更新 bootloader 条目与启动参数
   → 启动后核对 release、配置和构建标识

必须区分
--------

源码版本与源码目录名称
   目录名称只是标签；commit、补丁集合和工作区状态才构成可验证的源码指纹。

配置来源与最终配置
   defconfig 或旧配置描述生成起点；Kconfig 求值后的最终 ``.config`` 才是实际构建输入。

out-of-tree 构建与干净构建
   ``O=`` 隔离输出位置；真正干净还要求新输出目录、可审计源码树和没有残留隐式输入。

调试构建与生产构建
   调试构建强调可观测性和检查；生产构建强调部署约束，两者的时序、布局和性能可能不同。

构建完成与交付完成
   构建完成得到镜像和模块；交付完成还要求匹配的 initramfs、符号、配置、清单和 bootloader 入口。

版本字符串相同与构建相同
   相同 ``uname -r`` 不保证二进制、配置、补丁和工具链相同；需要构建清单和哈希继续确认。

一句话结论
----------

无法从明确输入稳定重建的内核，就无法可靠证明它的来源、解释它的差异、复现它的故障或安全地部署它。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 20，Engineering a Reproducible Kernel Build；
* 源文件：``docs/LinuxK/Part_04_Kconfig_Kbuild_Modules_and_Kernel_Images/Chapter_020_Engineering_a_Reproducible_Kernel_Build.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_04_Kconfig_Kbuild_Modules_and_Kernel_Images/Chapter_020_Engineering_a_Reproducible_Kernel_Build.md>`_。
