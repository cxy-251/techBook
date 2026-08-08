第019章：Power-On Sequence and Boot Entry
========================================

核心知识点
----------

* 手机上电后的主线是 ``Power-On Reset → Boot ROM → early firmware → bootloader → kernel entry``。这一阶段尚不存在 App、Framework 或普通系统服务。
* Power-On Reset 把任意掉电或重启历史收束到可预测硬件状态；PMIC 建立关键电源轨，SoC 释放 reset，CPU 从固定 reset vector 开始执行。
* Boot ROM 位于片上不可变或硬件保护区域，是首个可执行入口和硬件 root of trust。它负责读取最小启动状态、找到下一级代码并执行首轮验证或模式分流。
* 早期 firmware 负责让 DRAM、storage、clock、power domain、security engine 和必要显示/USB 通路达到 bootloader 可用状态。
* Boot device 与 boot mode 是两个维度：前者回答“从哪里加载”，后者回答“为什么走 normal / recovery / fastboot / DFU 等路径”。
* Bootloader 在拥有 DRAM 和存储能力后读取分区、选择 slot、判断启动模式、验证启动对象，并准备 kernel image、ramdisk、device tree、bootconfig 与安全状态。
* normal boot、recovery、fastboot/DFU 的本质差异是控制权和镜像接受范围不同。恢复模式不是普通 App 功能，而是高权限维护路径。
* kernel handoff 的核心是“执行入口 + 硬件描述 + 启动参数 + 安全状态”。只加载 kernel image 不足以保证内核能正确接管设备。
* 启动故障应先区分硬件上电失败、Boot ROM/firmware 失败、镜像选择或校验失败、kernel handoff 失败，而不是统一归类为“系统启动不了”。

关键路径
--------

正常启动：

::

   power key / reset event
   → PMIC establishes power rails
   → SoC releases reset
   → CPU executes Boot ROM
   → verify / load early firmware
   → initialize DRAM and storage
   → bootloader selects normal boot
   → verify boot objects
   → load kernel + ramdisk + hardware description
   → jump to kernel entry

模式分流：

::

   reset reason + key state + persistent boot metadata
   → bootloader mode decision
   → normal boot / recovery / fastboot / DFU
   → corresponding image and trust policy

故障定位：

::

   no power / no reset
   → Boot ROM cannot load next stage
   → firmware cannot initialize memory/storage
   → bootloader rejects image or slot
   → kernel handoff fails

概念辨析
--------

* **Reset vector 与 Boot ROM**：reset vector 是 CPU 复位后的取指规则，Boot ROM 是通常映射到该入口的不可变启动代码。
* **Boot device 与 boot mode**：boot device 是镜像来源，boot mode 是启动意图和控制路径，两者可以组合。
* **Recovery 与 normal boot**：Recovery 是独立或受控的修复环境，拥有普通应用不具备的系统分区操作能力。
* **Boot ROM 与 bootloader**：Boot ROM 固化在硬件中，bootloader 通常位于可更新存储并承担更复杂的平台策略。
* **Kernel image 与 kernel handoff**：镜像只是载荷之一，内核还需要 ramdisk、硬件描述、内存布局、启动参数与验证状态。

本章结论
--------

手机开机首先是一条硬件控制权和信任状态逐级转移的链路。分析启动问题时，应从供电与 reset 开始，沿 Boot ROM、early firmware、bootloader、mode selection、image verification 和 kernel handoff 逐级定位；只有这些阶段完成后，操作系统内核和后续用户空间才真正开始存在。