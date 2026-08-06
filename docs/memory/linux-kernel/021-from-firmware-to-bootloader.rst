第021章：从固件到 Bootloader
============================

本章必须记住
------------

#. Linux 内核开始执行之前，CPU、内存和启动设备已经经历了固件与 bootloader 的准备阶段。
#. 启动过程本质上是状态交接：前一阶段准备镜像、参数和硬件状态，后一阶段按照架构协议解释这些状态。
#. 固件是 CPU 复位后最早运行的软件环境，常见形式包括 BIOS、UEFI、Open Firmware、Coreboot、U-Boot 和虚拟机固件。
#. 固件通常完成最基本的 CPU、内存控制器、芯片组和启动设备初始化，并选择下一段启动程序。
#. 固件已经发现或初始化过硬件，不表示 Linux 可以直接沿用全部状态；内核仍会重新建立自己的中断、内存、调度和驱动模型。
#. Bootloader 的核心职责是选择内核，把内核镜像、initramfs、启动参数和硬件描述放到合适的物理内存位置，然后跳转到内核入口。
#. Bootloader 必须避免内核镜像、initramfs、设备树、启动参数和保留内存彼此覆盖。
#. 启动参数、内存映射、ACPI 表、设备树和 UEFI configuration table 都属于内核接管机器时的重要输入。
#. 内核镜像格式和入口规则由目标架构定义，不能把 x86 的启动协议直接套用到 arm64 或 RISC-V。
#. x86 启动常通过 setup header 和 ``struct boot_params`` 传递命令行、initrd 地址、内存信息和扩展数据。
#. arm64 启动通常通过寄存器和设备树传递状态，其中 ``x0`` 指向 FDT，入口前的 MMU、cache、中断和寄存器状态必须满足 arm64 启动协议。
#. RISC-V、PowerPC、MIPS 等架构同样有自己的镜像放置、寄存器和固件接口约定。
#. UEFI 启动可以先进入 GRUB、systemd-boot 等 bootloader，也可以由 Linux EFI stub 直接把内核镜像作为 EFI 程序加载。
#. EFI stub 位于内核镜像的一部分，它在 UEFI 环境中承担收集命令行、initramfs、内存映射和退出 Boot Services 等 loader 职责。
#. UEFI 的 Boot Services 只在退出服务前可用；内核接管后不能继续把固件启动服务当作普通运行时 API。
#. Secure Boot 主要验证启动组件是否由受信任密钥签名，它不能证明内核逻辑、配置和运行时状态一定正确。
#. 固件提供的内存映射和硬件描述属于输入证据，内核需要验证、复制并保留必要区域，不能无限期信任原始指针和临时服务。
#. Bootloader 跳转成功只证明控制权已经交给内核入口，不证明解压、页表、架构初始化和 ``start_kernel()`` 已经成功。
#. 排查早期启动时，应先判断失败发生在固件选择、镜像加载、参数放置、入口跳转还是内核早期代码，而不是笼统地说“内核启动失败”。

必背路径
--------

通用启动交接：

::

   CPU 复位
   → 固件建立最小硬件环境
   → 固件选择启动目标
   → bootloader 或 EFI stub 运行
   → 加载架构对应的内核镜像
   → 加载 initramfs
   → 准备 kernel command line
   → 准备 ACPI、FDT 或其它硬件描述
   → 按架构协议设置 CPU 和寄存器状态
   → 跳转到内核入口

x86 UEFI 常见路径：

::

   UEFI firmware
   → EFI 启动项
   → GRUB、systemd-boot 或 Linux EFI stub
   → 加载 bzImage 与 initramfs
   → 填充 setup header 和 boot_params
   → 取得最终 UEFI memory map
   → 退出 Boot Services
   → 跳转到 x86 内核早期入口

arm64 常见交接：

::

   固件或 U-Boot
   → 准备可用 RAM
   → 加载 Image 或先解压 Image.gz
   → 放置 FDT 与 initramfs
   → 在 /chosen 中提供 bootargs 和 initrd 范围
   → 按协议设置 x0 与 CPU 状态
   → 跳转到 arm64 kernel image 入口

启动失败的第一层分类：

::

   固件没有找到启动项
   → bootloader 没有找到或验证镜像
   → 镜像、initramfs 或参数放置错误
   → 架构入口状态不满足协议
   → 已跳入内核，但早期架构代码失败

必须区分
--------

* 固件与 bootloader：固件首先建立最小平台环境并选择下一段程序；bootloader 选择和放置内核启动材料，并完成内核入口交接。
* 硬件已初始化与内核已接管：固件初始化只为继续启动提供条件；Linux 接管后仍要建立自己的对象、策略和驱动状态。
* 镜像已加载与内核已启动：镜像进入内存只表示 loader 完成文件放置；内核还要经过入口、解压、页表和通用初始化。
* 启动协议与运行时 ABI：启动协议约束 bootloader 到内核入口的短暂交接；系统调用 ABI 约束内核启动后的用户态接口。
* Secure Boot 与系统正确性：Secure Boot 验证签名信任链；它不验证代码没有 bug，也不保证配置、模块和运行状态符合预期。

一句话结论
----------

Linux 启动的第一步不是 ``start_kernel()``，而是固件和 bootloader 按架构协议把镜像、参数、硬件描述与 CPU 状态可靠交给内核入口。
