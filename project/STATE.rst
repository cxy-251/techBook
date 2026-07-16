项目状态
========

最后更新
--------

2026-07-16。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   content present      = 001-193
   audit verified       = 001-015
   verified_through     = 015
   blocked batches      = none
   next batch           = 016-018
   next batch status    = ready

历史正文已经写到第193章，但只有001—015按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。016—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`013—015审查报告 <audits/linux-kernel/013-015.rst>`_：状态 ``repaired``。

本批修复了：

* 第013章继承第012章未固定的 ``-smp`` 分支，不再把AP执行与HLT停驻写成必然事实；
* 第013章把静态legacy ``$PIR``、q35 ICH9真实路由与ACPI ``_PRT`` 分层；
* 第013章补齐MP package跨度、present enabled位、IRQ0 override与600字节复制上限；
* 第013章把QEMU SMBIOS ``AUTO`` 的2.x优先/3.x回退与SeaBIOS legacy fallback拆开；
* 第014章证明loader返回0不汇总逐命令错误，命令执行也没有事务回滚；
* 第014章把RSDP搜索与 ``loader_err`` 拆成正交结果；
* 第015章把ACPI当前消费路径收敛为XSDT/RSDT→FADT→32位DSDT受限解析；
* 第015章不再把MADT、MCFG或 ``_PRT`` 写成SeaBIOS此刻已经解释；
* 第015章纠正无RSDP时 ``acpi_setup()`` 会生成内建兼容表的错误：当前实现只打印提示。

第015章已验证结束状态
---------------------

::

   current executor       = SeaBIOS platform_hardware_setup() on BSP/MainThread
   completed call         = qemu_platform_setup()
   next call              = coreboot_platform_setup(), then timer_setup()
   current CPU            = BSP
   CPU mode               = 32-bit protected mode
   paging                 = disabled
   A20                    = enabled
   NMI                    = masked by CMOS index bit 7
   maskable interrupts    = IF=0
   PIC unmasked           = master IRQ2 and slave IRQ13
   current thread         = MainThread; explicit LNRO0005 blk/scsi may add init workers
   present vCPU count     = not fixed by current -smp conditions
   no -smp override       = present=1; no AP executed entry_smp
   explicit multi-vCPU    = APs normally replay logged prefix and halt with IF=0
   MaxCountCPUs           = QEMU APIC-ID limit, at least present count
   PIR table              = static legacy template; conditional FSEG installation
   MP table               = conditional MaxCountCPUs<=255 and <=600-byte FSEG copy
   SMBIOS                 = QEMU AUTO romfile path; 2.x first, 3.x fallback
   ACPI loader            = per-command soft failures are not summarized by loader_err
   normal q35 RsdpAddr    = valid RSDP in FSEG
   ACPI table blob        = linked in HIGH; complete graph remains for later OS discovery
   SeaBIOS ACPI parse     = FADT -> 32-bit DSDT limited device cache only
   MADT/MCFG/_PRT         = not interpreted by this SeaBIOS control flow
   virtio-mmio            = only conditional LNRO0005 devices; fixed disk remains ICH9 AHCI
   no-RSDP fallback       = warning only; current acpi_setup() builds no tables
   storage drivers        = not started; AHCI media not probed
   GRUB/Linux             = not loaded

下一入口
--------

第016章从 ``qemu_platform_setup()`` 返回后的调用顺序继续：

::

   qemu_platform_setup() returns
   → coreboot_platform_setup()
   → timer_setup()
   → clock_setup()
   → tpm_setup()

016—018批次必须先读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/013-015.rst`` 的“整批控制流与交接”、
   “执行上下文与对象账本”、“发现并修复”中的第015章与“连续性检查”；
#. 第015章末尾、第016—018章正文和第019章开头；
#. ``.sources/seabios`` 与 ``.sources/qemu`` 固定提交中timer/clock、TPM、option ROM、
   VGA console、USB/PS2 input及相邻调用涉及的源码。

不要读取001—014全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

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
* 016—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
