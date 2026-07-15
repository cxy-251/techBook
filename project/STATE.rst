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
   audit verified       = 001-006
   verified_through     = 006
   blocked batches      = none
   next batch           = 007-009
   next batch status    = ready

历史正文已经写到第193章，但只有001—006按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。007—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`004—006审查报告 <audits/linux-kernel/004-006.rst>`_：状态 ``repaired``。

本批修复了：

* 第004章把早期栈顶 ``0x7000`` 写成当前精确ESP的问题；
* 第004章遗漏默认QEMU配置分支与IVT明确清零向量的问题；
* 第005章把四类静态启动优先级误写成QEMU读取三个CMOS槽位后的最终值；
* 第005章把BIOS32入口发布与PCI枚举、PIR表就绪混为同一边界的问题；
* 第006章标题声称启动了线程，但本章没有调用 ``run_thread()`` 的问题；
* 第006章DMA入口推断、 ``call16_override()`` 与RTC辅助线程边界；
* 三章缺失的合同章末结构与关键固定源码行锚。

第006章已验证结束状态
---------------------

::

   current executor       = SeaBIOS platform_hardware_setup()
   next call              = qemu_platform_setup()
   current CPU            = BSP
   CPU mode               = 32-bit protected mode
   paging                 = disabled
   A20                    = enabled
   maskable interrupts    = disabled; CanInterrupt=1 for later short windows
   NMI                    = masked by CMOS index bit 7
   early stack top        = 0x7000
   current ESP            = below 0x7000; exact value not fixed
   legacy DMA             = reset; cascade channel configured
   PIC vectors            = IRQ0-7→0x08-0x0f; IRQ8-15→0x70-0x77
   PIC unmasked           = master IRQ2 and slave IRQ13
   IVT IRQ13 entry        = INT 75h → entry_75
   Call16Data             = C16_BIG; saved a20=1
   SeaBIOS threads        = MainThread only; runtime policy loaded
   device thread stacks   = none
   PCI/SMM/MTRR/SMP       = not initialized
   GRUB/Linux             = not loaded

下一入口
--------

第007章从 ``platform_hardware_setup()`` 的下一条调用开始：

::

   qemu_platform_setup()
   → runningOnXen() == false
   → kvmclock_init() (conditional on runningOnKVM())
   → pci_setup()
   → pci_probe_host()
   → pci_bios_init_bus()
   → pci_probe_devices()

007—009批次必须先读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/004-006.rst`` 的“执行上下文与对象账本”、
   “发现并修复”中的第006章与“连续性检查”；
#. 第006章末尾、第007—009章正文和第010章开头；
#. ``.sources/seabios`` 与 ``.sources/qemu`` 固定提交中当前PCI/q35符号涉及的源码。

不要读取001—005全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

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
* 007—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
