第022章：内核解压与早期架构初始化
=================================

本章必须记住
------------

#. Bootloader 跳转到内核后，首先运行的是受架构约束的早期入口代码，而不是已经完整建立运行环境的通用内核。
#. 早期入口的任务是建立让后续 C 代码可以继续执行的最小环境，包括栈、BSS、CPU 状态、页表、启动参数副本和早期内存描述。
#. x86 常见 ``bzImage`` 包含启动协议头、setup 代码、压缩载荷和解压 stub；它不是一个可以直接按普通 gzip 文件理解的文件。
#. x86 解压代码先选择安全的输出位置，再解压内核载荷、解析 ELF 的 ``PT_LOAD`` 段，并在需要时执行重定位。
#. 解压 stub 已经属于内核构建产物中的代码，但此时普通分配器、完整异常处理、正式控制台和通用驱动框架尚未建立。
#. arm64 官方启动路径没有内置通用解压器；``Image.gz`` 等压缩镜像通常由 bootloader 解压，内核入口接收未压缩 ``Image``。
#. 是否由内核自解压属于架构协议的一部分，不能把 x86 ``bzImage`` 的经验直接迁移到 arm64。
#. 早期 CPU 模式决定入口代码能够假定哪些寄存器、cache、MMU、中断和异常状态。
#. 早期页表用于把当前物理执行位置、内核链接地址和后续虚拟地址空间连接起来。
#. identity mapping 让一段虚拟地址直接对应同值物理地址，常用于分页切换和早期跳转期间保持当前代码可执行。
#. kernel mapping 把内核期望的虚拟地址映射到实际装载内核的物理页，使链接后的符号地址可以正确访问。
#. 物理地址、链接地址和运行时虚拟地址是不同概念，早期启动代码必须明确处理它们之间的转换。
#. x86 与 arm64 的页表寄存器、异常级别和切换细节不同，但目标相同：建立足以运行内核 C 代码的稳定地址语义。
#. ``start_kernel()`` 是通用初始化主入口，位于 ``init/main.c``；进入它之前，架构代码已经完成最低限度的 CPU 与地址空间准备。
#. ``setup_arch()`` 位于通用启动主线的早期位置，用于继续完成架构相关的内存、命令行、平台和保留区域处理。
#. Bootloader 提供的命令行、FDT、ACPI、initramfs 和内存映射必须在临时环境失效前被保存或登记。
#. ``memblock`` 是启动早期的物理内存描述与分配机制，用于管理普通页分配器建立之前的可用内存和保留内存。
#. ``memblock_add()`` 一类操作登记可用内存范围，``memblock_reserve()`` 一类操作登记不能分配的内核镜像、initramfs、FDT、固件表和其它保留区域。
#. “系统有多少 RAM”和“当前早期分配器可以使用多少 RAM”不是同一问题；保留区、固件区、设备区和内核自身占用都会减少可分配范围。
#. 早期内存描述错误可能导致镜像、页表、initramfs 或固件数据被覆盖，这类错误通常在完整日志系统建立前就会使机器卡死。
#. 架构入口成功进入 ``start_kernel()``，只证明最小运行环境已经建立，不表示内存、调度、设备和用户态已经可用。
#. 早期启动排查应按“解压前、解压中、MMU 切换前后、进入 ``start_kernel()``、执行 ``setup_arch()``”分阶段定位。

必背路径
--------

x86 压缩内核主路径：

::

   bootloader 加载 bzImage 与 boot_params
   → 进入 compressed entry
   → 建立解压 stub 的最小栈和执行环境
   → 选择不会覆盖启动材料的输出地址
   → 解压内核载荷
   → 解析 ELF PT_LOAD 段
   → 必要时应用 relocation 与 KASLR 位置调整
   → 跳转到解压后的架构内核入口
   → 建立早期页表和 CPU 状态
   → 进入 start_kernel()

arm64 典型主路径：

::

   bootloader 准备未压缩 Image 与 FDT
   → 按协议关闭 MMU并设置寄存器
   → primary_entry 保存启动信息
   → 建立初始 idmap 和早期栈
   → __cpu_setup 设置页表与 CPU 控制状态
   → 打开 MMU并切换到内核虚拟地址
   → __primary_switched 建立异常向量等状态
   → 调用 start_kernel()

早期内存建立：

::

   读取固件内存映射、FDT 或架构内存信息
   → 登记可用物理内存范围
   → 保留内核镜像与早期页表
   → 保留 initramfs、FDT、ACPI 与固件区域
   → 使用 memblock 完成早期分配
   → 初始化普通页分配器
   → 释放不再需要的早期临时内存

阶段化故障定位：

::

   bootloader 有输出但没有内核入口证据
   → 检查镜像格式、加载地址和入口协议

   有解压信息但无 Linux banner
   → 检查解压输出、重定位、页表和 CPU 模式

   有 Linux banner 但早期内存初始化失败
   → 检查内存映射、保留区域、FDT、ACPI 与 setup_arch

必须区分
--------

压缩启动镜像与 ``vmlinux``
   启动镜像面向 bootloader 和架构启动协议；``vmlinux`` 是链接后的内核 ELF 和调试依据。

解压代码与完整内核
   解压 stub 只能使用极少的早期能力；进入解压代码不表示通用内核设施已经可用。

物理地址与虚拟地址
   物理地址表示真实内存位置；虚拟地址由页表解释，内核链接符号通常依赖内核虚拟地址布局。

identity mapping 与 kernel mapping
   identity mapping 主要支撑切换和当前代码执行；kernel mapping 支撑正式内核虚拟地址访问。

总内存与可用内存
   固件报告的 RAM 总量还要扣除内核、initramfs、固件、设备和其它保留范围，才能成为早期可分配内存。

一句话结论
----------

内核在管理系统之前，必须先把自己解压或放置到正确位置，建立 CPU、页表、栈和早期内存管理，随后才能进入 ``start_kernel()`` 的通用初始化。

来源
----

* AIBook 书籍：LinuxK；
* AIBook 章节：Chapter 22，Kernel Decompression and Early Architecture Setup；
* 源文件：``docs/LinuxK/Part_05_Boot_Sequence_Initcalls_and_Early_Kernel_Initialization/Chapter_022_Kernel_Decompression_and_Early_Architecture_Setup.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_05_Boot_Sequence_Initcalls_and_Early_Kernel_Initialization/Chapter_022_Kernel_Decompression_and_Early_Architecture_Setup.md>`_。
