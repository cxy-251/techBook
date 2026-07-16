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
   audit verified       = 001-021
   verified_through     = 021
   blocked batches      = none
   next batch           = 022-024
   next batch status    = ready

历史正文已经写到第193章，但只有001—021按
``project/LINUX_KERNEL_CONTRACT.rst`` 完成固定源码审查。022—193仍是 ``pending``，
不得把“文件存在”写成“技术内容已验证”。第193章之后的新生产保持暂停。

最近完成批次
------------

`019—021审查报告 <audits/linux-kernel/019-021.rst>`_：状态 ``repaired``。

本批修复了：

* 第019章补齐无floppy/legacy ATA drive时仍发生的IVT 1Eh、IRQ6、BDA disk-control与
  IRQ14变化；
* 第019章固定QEMU ``PI=0x3f`` 的六个AHCI port worker：port 0成功，ports 1—5
  link-down并释放temporary对象；
* 第019章纠正 ``have_driver`` 的发布时点、AHCI轮询而非IRQ、DMA buffer替换而非搬移、
  SET FEATURES失败非致命，以及第一次 ``wait_threads`` 的真实barrier作用；
* 第020章固定无network override的q35默认e1000e，核对组合ROM首幅x86/iPXE image的
  ``BCV=0``、 ``BEV=0x0385``，不再把PXE写成纯条件可能；
* 第020章纠正checksum、PnP init、legacy BCV、BEV登记与INT 19h窄恢复的边界；
* 第021章证明固定无输入菜单不改BootList，第二次 ``wait_threads`` 当前不迭代；
* 第021章纠正“执行了BCV”和“BootList被转换”的错误：固定 ``call_bcv=0``，另行构造
  hard-disk、iPXE、floppy fallback三项 ``BEV[]``；
* 第021章固定 ``IDMap[EXTTYPE_HD][0]``、BDA ``hdcount=1``、IVT 41h，并证明AHCI
  translation不走只针对 ``DTYPE_ATA`` 的CMOS特殊分支；
* 第021章把 ``e820_prepboot`` 收紧为只 ``dump_map``，撤销不存在的E820冻结开关。

第021章已验证结束状态
---------------------

::

   current executor       = SeaBIOS maininit() on BSP/MainThread
   completed call         = prepareboot()
   next call              = make_bios_readonly()
   current CPU            = BSP
   CPU mode               = 32-bit protected mode
   paging                 = disabled
   A20                    = enabled
   NMI                    = masked by CMOS index bit 7
   MainThread IF           = 0
   cooperative threads    = none; have_threads=false
   PIC additionally open  = IRQ0, IRQ1, IRQ6, IRQ8, IRQ12, IRQ14;
                            old IRQ2/IRQ13 remain open
   internal timer         = KVM-provided scaled TSC or ICH9 PM timer
   fixed TPM              = absent; no TPM log/PCR state
   fixed machine USB      = false; no USB controller/worker/boot item
   fixed i8042            = present; PS/2 worker has exited
   fixed AHCI PCI         = 00:1f.2, BAR5 memory + bus master, have_driver=1
   fixed AHCI ports       = PI 0x3f; port0 persistent, ports1-5 released
   AHCI port0 drive       = DTYPE_AHCI, 512-byte sectors, IDENTIFY complete
   AHCI runtime memory    = bounce low; ctrl/port F-segment; DMA areas ZoneHigh
   fixed default NIC      = e1000e without network override
   ordinary ROM result    = iPXE x86 image init returned; BCV=0, BEV=0x0385
   BootList order         = AHCI hard disk priority101; iPXE BEV priority9999
   BCV call count         = 0
   IDMap HD[0]            = AHCI port0 drive
   BDA hdcount            = 1
   BIOS drive 0x80        = resolves to IDMap HD[0]
   FDPT                   = EBDA fdpt[0], IVT 41h published
   final BEV[]            = [hard disk, iPXE, floppy fallback]
   CDCount/CD emulation   = 0 / absent
   PMM header             = signature 0, entry 0
   memory handoff         = malloc_prepboot complete; current E820 map dumped
   E820 freeze bit        = none
   HaveRunPost            = 2
   BIOS segment checksum  = 0 modulo 256
   BIOS shadow writes     = still enabled until make_bios_readonly()
   MBR / 0x7c00           = not read / not populated with boot sector
   GRUB / Linux           = not executing / not loaded

下一入口
--------

第022章从 ``prepareboot()`` 后的下一条调用继续：

::

   prepareboot() returns
   → make_bios_readonly()
   → startBoot()
   → INT 19h
   → BEV[0] generic hard disk
   → INT 13h with DL=0x80
   → IDMap[EXTTYPE_HD][0]
   → AHCI READ of LBA 0 to 0x7c00

022—024批次必须先读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. 本文件；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/audits/linux-kernel/019-021.rst`` 的“整批控制流与交接”、
   “执行上下文与对象账本”、“已核定的整批成功路径”、“发现并修复”和“连续性检查”；
#. 第021章末尾、第022—024章全文和第025章开头；
#. 两份track manifest的审计游标片段；
#. 固定SeaBIOS源码中q35 PAM shadow、 ``startBoot``、16/32位thunk、INT 19h/INT 13h、
   ``boot_disk`` 与AHCI READ路径；
#. 固定QEMU源码中q35 PAM/ROM shadow和AHCI READ实现；
#. 固定GRUB 2.14 commit中 ``boot.img``、 ``diskboot.img``、blocklist与相邻handoff源码。

不要读取001—020全文、完整193章目录或历史前向检查点，除非审查中发现必须回溯的矛盾。

源码缓存
--------

::

   .sources/seabios HEAD = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   .sources/qemu HEAD    = a759542a2c62f0fd3b65f5a66ad9868201014669

两个缓存均由 ``.gitignore`` 排除且源码worktree干净。QEMU使用稀疏检出；019—021批次已
按需加入 ``hw/ide``、 ``hw/net``、 ``hw/pci`` 及相关include。缺少下一批目录时继续按
需补齐，不为未来章节预读全部源码。GRUB缓存若已存在，使用前必须重新核对固定commit。

已知结构债务
------------

* 第022章既有开头把E820写成 ``frozen``；第021章已证明没有冻结开关，022—024批次必须
  结合后续不再修改的控制流修正文义；
* 第065章存在两个正文文件；
* 第066章存在两个正文文件；
* 001—073尚未逐章登记到当前track manifest；
* 022—193尚未按专用合同补齐章末结构和精确证据，必须随顺序审查处理，不能批量机械改写。

历史前向终点
------------

回溯审查开始前的第193章终点保存在
``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``。它只用于审查闭合后的对照，不是当前
执行依据，也不代表UDP入口已经验证。
