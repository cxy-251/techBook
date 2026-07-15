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
   audit verified       = 001-012
   verified_through     = 012
   blocked batches      = none
   next batch           = 013-015
   next batch status    = ready

历史正文已经写到第193章，但只有001—012按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。013—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`010—012审查报告 <audits/linux-kernel/010-012.rst>`_：状态 ``repaired``。

本批修复了：

* 第010章把QEMU SMM auto能力分支写成无条件SMI/SMBASE迁移的问题；
* 第010章把ICH9 ``SMI_LOCK`` 扩大为整个SMI_EN锁、把 ``0x0a`` 误写成MCH
  ``D_LCK`` 的问题；
* 第010章遗漏不支持save-state revision会让BSP永久轮询的问题；
* 第011章颠倒 ``wrmsr_smp`` 写BSP与32项容量检查顺序的问题；
* 第011章遗漏 ``15 + 2 * vcnt`` 容量边界、把固定PCI hole误写成3.5 GiB的问题；
* 第011章把条件FEATURE_CONTROL输入写成稳定结果的问题；
* 第012章把未固定的 ``-smp`` 分支收敛成“AP必然执行并停驻”的问题；
* 第012章把 ``etc/max-cpus`` 当成普通最大CPU数而非APIC-ID上界的问题；
* 第009章到第010章的相邻SMM预告已同步改为条件入口。

第012章已验证结束状态
---------------------

::

   current executor       = SeaBIOS qemu_platform_setup() on BSP/MainThread
   next branch            = if (MaxCountCPUs <= 255)
   current CPU            = BSP
   CPU mode               = 32-bit protected mode
   paging                 = disabled
   A20                    = enabled
   NMI                    = masked by CMOS index bit 7
   maskable interrupts    = IF=0
   PIC unmasked           = master IRQ2 and slave IRQ13
   SeaBIOS threads        = MainThread only
   SMM                    = success or capability-skip branch; see 010-012 report
   MTRR                   = configured only when CPUID/MTRRcap gates pass
   smp_msr                = at most 32 replay entries; overflow writes BSP but truncates AP template
   present vCPU count     = not fixed by current -smp conditions
   no -smp override       = present=1; no AP executed entry_smp
   explicit multi-vCPU    = APs normally replay logged prefix and halt with IF=0
   MaxCountCPUs           = QEMU APIC-ID limit, at least present count
   BSP local APIC         = software enabled; LINT0 ExtINT; LINT1 NMI
   FoundAPICIDs           = BSP plus any normally reported APs
   AP trampoline 0x10000 = original 8 bytes restored
   firmware tables       = PIRQ/MP/SMBIOS not built yet
   storage drivers        = not started; AHCI media not probed
   GRUB/Linux             = not loaded

下一入口
--------

第013章从 ``smp_setup()`` 返回后的条件判断开始：

::

   if (MaxCountCPUs <= 255) {
       pirtable_setup();
       mptable_setup();
   }
   smbios_setup();

013—015批次必须先读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/010-012.rst`` 的“整批控制流与交接”、
   “执行上下文与对象账本”、“发现并修复”中的第012章与“连续性检查”；
#. 第012章末尾、第013—015章正文和第016章开头；
#. ``.sources/seabios`` 与 ``.sources/qemu`` 固定提交中PIRQ、MP table、SMBIOS、
   ACPI table loader及相邻调用涉及的源码。

不要读取001—011全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

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
* 013—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
