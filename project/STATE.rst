项目状态
========

最后更新
--------

2026-07-15。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   content present      = 001-193
   audit verified       = 001-009
   verified_through     = 009
   blocked batches      = none
   next batch           = 010-012
   next batch status    = ready

历史正文已经写到第193章，但只有001—009按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。010—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`007—009审查报告 <audits/linux-kernel/007-009.rst>`_：状态 ``repaired``。

本批修复了：

* 第007章遗漏bridge bus-number reserve会扩大subordinate范围的问题；
* 第007章 ``revision`` 提取伪代码与固定源码不一致、设备表失败不回滚的问题；
* 第008章把 ``RamSize`` 强写成连续RAM末端的问题；
* 第008章遗漏bridge能力探测禁用旧窗口与 ``pci_pad_mem64`` 主动迁移的问题；
* 第008章把“无高端BAR”与 ``pcimem64_start=0`` 无条件等同的问题；
* 第009章把INTx路由已建立与IRQ10/11可交付混淆的问题；
* 第009章把PM timer切换和默认VGA选择写成无条件结果的问题；
* 三章缺失的合同章末结构与固定源码行锚。

第009章已验证结束状态
---------------------

::

   current executor       = SeaBIOS qemu_platform_setup()
   next call              = smm_device_setup()
   current CPU            = BSP
   CPU mode               = 32-bit protected mode
   paging                 = disabled
   A20                    = enabled
   NMI                    = masked by CMOS index bit 7
   maskable interrupts    = IF=0
   PIC unmasked           = master IRQ2 and slave IRQ13
   SeaBIOS threads        = MainThread only
   PCI config access      = q35 MMCONFIG in 32-bit flat mode
   MMCONFIG               = 0xb0000000-0xbfffffff; E820_RESERVED
   PCI topology           = bus numbering and PCIDevices cache complete
   PCI resources          = endpoint BARs and bridge windows mapped
   PCI INTx               = pin lines and PIRQA-H routes programmed to IRQ10/11
   IRQ10/IRQ11            = level-triggered but still PIC-masked
   PCI command            = IO/MEM/SERR requested; bus master not uniform
   ICH9 platform state    = PMBASE, SCI route, RCBA and SMBus setup applied when matched
   PM timer               = setup called; selected only if prior source was PIT
   default VGA            = selected if a VGA function exists; option ROM not run
   SMM/MTRR/SMP           = not initialized
   storage drivers        = not started; AHCI media not probed
   GRUB/Linux             = not loaded

下一入口
--------

第010章从 ``qemu_platform_setup()`` 中 ``pci_setup()`` 返回后的下一条调用开始：

::

   smm_device_setup()
   → 从 PCIDevices 查找 Q35 MCH 与 ICH9 LPC
   → smm_setup()
   → q35/ICH9 SMM安装与SMBASE relocation
   → mtrr_setup()
   → msr_feature_control_setup()
   → smp_setup()

010—012批次必须先读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/007-009.rst`` 的“执行上下文与对象账本”、
   “发现并修复”中的第009章与“连续性检查”；
#. 第009章末尾、第010—012章正文和第013章开头；
#. ``.sources/seabios`` 与 ``.sources/qemu`` 固定提交中SMM、MTRR、MSR和SMP涉及的源码。

不要读取001—008全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

源码缓存
--------

::

   .sources/seabios HEAD = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   .sources/qemu HEAD    = a759542a2c62f0fd3b65f5a66ad9868201014669

两个缓存均由 ``.gitignore`` 排除。QEMU使用稀疏检出；缺少目录时按当前批次补齐。

已知结构债务
------------

* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 001—073尚未逐章登记到当前track manifest；
* 010—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
