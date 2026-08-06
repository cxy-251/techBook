第022章：内核解压与早期架构初始化
=================================

核心知识点
----------

早期入口先建立最小运行环境
   Bootloader 交权后，最先执行的是架构相关入口代码。此时普通分配器、完整异常处理、正式控制台和驱动框架尚未建立，入口代码必须先准备栈、BSS、CPU 状态、页表和启动信息。

解压责任取决于架构协议
   x86 ``bzImage`` 通常包含启动头、压缩载荷和解压 stub，由内核早期代码完成解压；arm64 常由 bootloader 解压 ``Image.gz``，内核入口接收未压缩 ``Image``。

解压阶段恢复真正的内核映像
   x86 解压代码选择安全输出位置，解压载荷，按 ELF ``PT_LOAD`` 段放置内核，并在需要时处理重定位和 KASLR 位置调整。解压 stub 只是过渡程序，不是完整内核运行环境。

地址语义必须在早期稳定
   物理装载地址、链接地址和运行时虚拟地址可能不同。早期代码必须建立页表，把当前执行位置与内核期望的虚拟地址空间连接起来。

Identity mapping 与 kernel mapping 承担不同角色
   Identity mapping 让切换页表或 MMU 时当前代码仍能执行；kernel mapping 把内核虚拟地址映射到实际物理页，使链接后的符号和数据能够正确访问。

架构代码为通用 C 入口铺路
   不同架构使用不同寄存器、异常级别、页表和 cache 规则，但目标相同：让 CPU、栈和地址空间达到可以调用 ``start_kernel()`` 的最低条件。

启动信息必须在临时环境失效前保存
   命令行、FDT、ACPI、initramfs 和固件内存映射来自前一阶段。架构代码需要复制、登记或保留这些信息，避免原始区域被后续内存管理覆盖。

``memblock`` 管理早期物理内存
   普通页分配器建立前，``memblock`` 记录可用内存与保留区域，并为内核镜像、页表、initramfs、FDT 和固件表等对象提供早期分配与保护。

关键路径
--------

x86 压缩内核主路径：

::

   bootloader 加载 bzImage 与 boot_params
   → 进入 compressed entry
   → 建立解压 stub 的栈和最小环境
   → 选择安全输出地址
   → 解压并放置 ELF PT_LOAD 段
   → 应用必要的 relocation
   → 跳转到解压后的架构入口
   → 建立早期页表和 CPU 状态
   → 调用 start_kernel()

arm64 典型主路径：

::

   bootloader 准备 Image、FDT 与 initramfs
   → 按协议设置寄存器并关闭 MMU
   → primary_entry 保存启动信息
   → 建立 idmap 与早期栈
   → __cpu_setup 配置 CPU 与页表属性
   → 打开 MMU并切换到内核虚拟地址
   → __primary_switched
   → 调用 start_kernel()

概念辨析
--------

压缩启动镜像与 ``vmlinux``
   压缩启动镜像面向 Bootloader 和架构启动协议；``vmlinux`` 是链接后的内核 ELF，主要用于链接、符号和调试分析。

解压 stub 与完整内核
   解压 stub 只具备恢复内核载荷所需的最低能力；完整内核设施要在架构初始化和 ``start_kernel()`` 之后逐步建立。

物理地址与虚拟地址
   物理地址表示真实内存位置；虚拟地址由页表解释，内核符号通常按链接后的虚拟地址布局访问。

Identity mapping 与 kernel mapping
   Identity mapping 支撑地址空间切换时的连续执行；kernel mapping 支撑正式内核虚拟地址下的代码和数据访问。

总内存与早期可用内存
   固件报告的 RAM 还要扣除内核、页表、initramfs、固件表和设备保留区域，剩余部分才可供早期分配。

本章结论
--------

内核在管理系统之前，必须先恢复自身映像，建立稳定的 CPU、栈、页表与早期内存描述，随后才能进入 ``start_kernel()``。