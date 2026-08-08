第020章：Boot ROM, Bootloader, Firmware, Kernel Image, Verified Boot
==================================================================

核心知识点
----------

* 启动链把硬件可执行条件、镜像可信条件和内核接管条件连接起来：Boot ROM 提供最初信任点，bootloader 扩展硬件与策略能力，Verified Boot 决定镜像是否可接受。
* Boot ROM、primary bootloader、secondary bootloader 的差异主要在可变性和能力范围。越靠后越能访问 DRAM、storage、display、TEE、slot metadata 和复杂启动策略。
* Firmware 初始化的核心对象是 DRAM、storage、display 与 security engine。DRAM 让大镜像可装载，storage 让分区可读取，display 提供启动提示，安全硬件提供签名和版本状态基础。
* Kernel image 是执行主体，ramdisk 提供早期用户空间，device tree 描述非自发现硬件，bootconfig / command line 传递启动配置和平台状态。
* Android 的 ``boot``、``init_boot``、``vendor_boot`` 等镜像职责会随版本变化，但稳定模型仍是：通用 kernel、早期 init、vendor 启动材料与设备描述被拆分并在 handoff 前组合。
* Verified Boot 不只检查“文件有没有坏”，还要确认镜像来源、hash、签名、rollback index、分区描述与设备 lock state 是否满足当前策略。
* ``vbmeta`` 负责组织受信任的 hash、hashtree、签名和链式分区关系；``dm-verity`` 则在 kernel 读取大分区数据时进行 block-level 完整性校验。
* Bootloader lock state 决定设备是否允许刷写或启动非内置 root of trust 授权的系统。解锁状态通常伴随用户警告和数据保护边界变化。
* kernel handoff 必须把经过验证的启动事实传下去，使 kernel 和 userspace 能继续知道当前 slot、verified boot state、启动模式和设备安全状态。

关键路径
--------

启动对象准备：

::

   Boot ROM
   → verify first boot stage
   → bootloader initializes DRAM / storage / security
   → choose slot and boot mode
   → load boot / init_boot / vendor_boot materials
   → verify vbmeta and referenced partitions
   → assemble kernel + ramdisk + DT + bootconfig
   → jump to kernel

大分区完整性：

::

   trusted vbmeta
   → hashtree root
   → kernel dm-verity target
   → block read
   → hash verification
   → trusted data or integrity failure

锁状态：

::

   device locked / unlocked
   → root-of-trust policy
   → image acceptance range
   → boot warning / verification result
   → userspace receives boot state

概念辨析
--------

* **Boot ROM 与 secondary bootloader**：前者能力最小且不可变，后者拥有分区、slot、显示、验证和 handoff 等平台控制能力。
* **Kernel image 与 ramdisk**：kernel 提供内核执行代码，ramdisk 提供最早期用户空间和挂载所需材料。
* **Device Tree 与 bootconfig**：前者主要描述硬件拓扑，后者主要传递结构化启动配置和平台状态。
* **Verified Boot 与 dm-verity**：Verified Boot 建立整条启动信任关系，dm-verity 是其中面向大分区按块读取校验的机制。
* **签名合法与版本可接受**：旧镜像可以仍然拥有合法签名，rollback protection 负责阻止它回退到低于设备已接受的安全版本。

本章结论
--------

从 Boot ROM 到 kernel entry 的启动链必须同时解决“谁能执行、硬件是否可用、镜像是否可信、内核拿到什么输入”四个问题。分析启动失败时，应分别检查 boot stage、firmware 初始化、boot image 组成、vbmeta/verity、rollback state 和 device lock state，而不是把所有问题都归入单一的“刷机失败”或“内核问题”。