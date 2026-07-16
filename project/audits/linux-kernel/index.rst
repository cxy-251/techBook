Linux Kernel回溯审查账本
========================

本账本只登记批次状态和报告入口。技术证据保存在各批报告与修订后的正文中。

当前游标
--------

::

   mode             = retrospective-audit
   production       = paused
   verified_through = 048
   current_batch    = none
   next_batch       = 049-051
   current_status   = ready

状态语义遵守 ``project/LINUX_KERNEL_CONTRACT.rst``。

批次
----

* `001-003 <001-003.rst>`_：``repaired``；固定QEMU/SeaBIOS源码核验完成，无阻塞。
* `004-006 <004-006.rst>`_：``repaired``；固定SeaBIOS源码核验完成，无阻塞。
* `007-009 <007-009.rst>`_：``repaired``；固定SeaBIOS/QEMU源码核验完成，无阻塞。
* `010-012 <010-012.rst>`_：``repaired``；SMM、MTRR/MSR与SMP条件边界核验完成，无阻塞。
* `013-015 <013-015.rst>`_：``repaired``；PIR/MP/SMBIOS、ACPI loader与受限DSDT解析核验完成，无阻塞。
* `016-018 <016-018.rst>`_：``repaired``；timer/clock/TPM、VGA Option ROM与USB/PS2条件边界核验完成，无阻塞。
* `019-021 <019-021.rst>`_：``repaired``；AHCI磁盘、默认iPXE ROM与drive map/prepareboot边界核验完成，无阻塞。
* `022-024 <022-024.rst>`_：``repaired``；SeaBIOS INT 19h/MBR交接、GRUB boot.img与diskboot blocklist边界核验完成，无阻塞。
* `025-027 <025-027.rst>`_：``repaired``；GRUB模式切换/E820 heap、embedded module与动态normal入口核验完成，无阻塞。
* `028-030 <028-030.rst>`_：``repaired``；动态normal、grub.cfg/menu与linux.mod按需装载核验完成，无阻塞。
* `031-033 <031-033.rst>`_：``repaired``；bzImage/initramfs装载、boot_params与Linux startup_32交接核验完成，无阻塞。
* `034-036 <034-036.rst>`_：``repaired``；compressed long-mode入口、搬迁、identity map与解压选址核验完成，无阻塞。
* `037-039 <037-039.rst>`_：``repaired``；解压/ELF/relocation、正式高半区入口与bootdata保存核验完成，无阻塞。
* `040-042 <040-042.rst>`_：``repaired``；generic启动前缀、setup_arch/E820与PFN边界核验完成，无阻塞。
* `043-045 <043-045.rst>`_：``repaired``；memblock/direct map、initrd/ACPI initial tables与early
  LAPIC/NUMA边界核验完成，无阻塞。
* `046-048 <046-048.rst>`_：``repaired``；CMA/KASAN、tboot/vsyscall/early quirks与full
  MADT/possible CPU/IOAPIC映射边界核验完成，无阻塞。

已知但尚未轮到的结构债务
------------------------

* 第049章起的历史启动正文仍引用旧版本标签或未经固定源码复核的artifact/数值；
* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 既有boot章节没有逐章登记到当前track manifest；
* 历史正文与通用学习设计规则长期并存，适用关系曾不明确；现由Linux Kernel专用合同消除歧义。

结构债务在顺序审查到对应编号时处理；不会因此把001—064跳过。
