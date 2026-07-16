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
   audit verified       = 001-048
   verified_through     = 048
   blocked batches      = none
   next batch           = 049-051
   next batch status    = ready

049—193中文件存在不等于技术已验证；当前pending范围是049—193。第193章审查闭合前不生产新章。

最近完成批次
------------

`046—048审查报告 <audits/linux-kernel/046-048.rst>`_：状态 ``repaired``。

本批修复了：

* 046开头不再继承“045已枚举CPU topology”的错误；processor records首次在048 full MADT处理；
* CMA传入 ``max_pfn_mapped`` 只是global default limit，explicit/per-NUMA paths分开；
* crashkernel、xDBC、KASAN均按build/effective parameters与failure rollback保留条件；
* native paging hook只清node state，KASAN按 ``pfn_mapped[]`` 建shadow，x86-64 sync call为空；
* fixed GRUB ``tboot_addr=0`` 确定probe返回，nonzero E820 check不再夸大成整页验证；
* vsyscall build default固定为XONLY/NONE，EMULATE/XONLY/NONE三种PTE/gate结果分开；
* x86-64 ``x86_32_probe_apic`` no-op，early PCI quirk收紧到actual fixed table；
* topology early limit区分 ``maxcpus=0`` 与positive ``maxcpus=N``；
* full MADT processor、IOAPIC、source override、SCI/NMI passes与MP complement顺序固定；
* Local APIC normal fixmap在045已建立，048只做last detection；
* possible/present/online/active CPU masks、SRAT affinity与logical mapping时点分开；
* IOAPIC resource objects/fixmaps在048完成，但resource-tree insertion留给later PCI survey。

当前符号
--------

::

   Z   = original boot_params physical address; copied and no longer reserved
   R/N = GRUB original initramfs physical address / true size
   E   = PAGE_ALIGN(R + N)
   L   = build LOAD_PHYSICAL_ADDR
   O   = actual physical kernel output base / formal phys_base
   V   = relocation virtual position value

initrd fast path保留original ``[R,E)``；relocation path复制成功后已free original range。actual branch、
CMA/crashkernel reservations、KASAN/vsyscall modes与CPU/node counts都受未固定build/effective CLI影响，
STATE只保存源码边界，不制造数值。

第048章结束状态
---------------

::

   current executor          = setup_arch(), guest_late_init returned
   next call                 = e820__reserve_resources()
   CPU mode                  = x86-64 long mode
   IF / DF                   = 0 / 0
   current task              = init_task
   active CR3                = swapper_pg_dir = init_top_pgt
   early brk                 = reserved and sealed; _brk_start = 0
   memblock.memory           = working-E820 RAM with NUMA node identities
   memblock current limit    = get_max_mapped()
   direct map                = ISA compatibility range + actual memblock RAM
   CMA                       = conditional global/per-node reservations
   crashkernel               = conditional effective-option reservation
   KASAN                     = no-op or formal shadow in init_top_pgt
   sync_initial_page_table   = x86-64 no-op
   tboot                     = NULL; fixed GRUB tboot_addr = 0
   vsyscall                  = build no-op or effective EMULATE/XONLY/NONE
   early PCI quirks          = limited direct scan completed when allowed
   ACPI FADT                 = enabled path applied legacy/PM-timer facts
   MADT processors           = full Local APIC/x2APIC enumeration completed on success
   ACPI IOAPIC model         = q35 success path selected with GSI/SCI/NMI routes
   MP full parser            = skipped on complete ACPI or used as partial/disabled fallback
   Local APIC                = address registered; MMIO fixmap or x2APIC MSR mode
   nr_cpu_ids                = finalized from firmware registry and early capacity limit
   CPU possible/present      = finalized allowed/physical masks
   CPU online/active         = CPU0 only
   CPU-to-node               = SRAT mapping connected where valid; fallback retained
   Generic Initiator nodes   = conditionally onlined
   IOAPIC MMIO               = fixed nocache mappings established
   IOAPIC resources          = objects populated, not inserted into iomem tree yet
   device IRQ runtime        = no final vector/redirection enable; IF remains 0
   future PCI init hook      = pci_acpi_init when ACPI IRQ enabled
   guest late hook           = actual detected hypervisor hook or native no-op
   zones/buddy allocator     = not initialized
   setup_arch                = not returned

已验证的046—048关系
-----------------

* global CMA default limit来自 ``max_pfn_mapped``，但user limit与per-NUMA declarations有独立规则；
* crashkernel在SRAT后reserve；fixed GRUB line无option不排除builtin command line；
* xDBC必须先定位DbC且hardware setup返回0，existing early console还可阻止register；
* native x86-64 ``paging_init`` 不建页表，KASAN path才临时切复制后的 ``early_top_pgt``；
* KASAN按mapped coverage而非free RAM建立正式shadow，最终返回 ``init_top_pgt``；
* tboot fixed zero path不建fixmap；nonzero branch的same-start/end E820 overlap不是full-page check；
* vsyscall EMULATE有PTE与user bits，XONLY无PTE但有execute gate，NONE无gate；
* early quirk是limited table scan，q35名字本身不代表命中实体机workaround；
* topology early limit只收capacity，048 ``topology_init_possible_cpus`` 才生成firmware-backed masks；
* full MADT在048首次调用 ``topology_register_apic`` 并解析IOAPIC/IRQ routes；
* full MP parser在complete ACPI时skip，partial ACPI时不重复LAPIC processors；
* Local APIC fixmap的normal创建点是045 ``register_lapic_address``；
* ``init_cpu_to_node`` 在logical IDs明确后才接回045保存的SRAT APIC affinity；
* IOAPIC resource allocation、fixmap、later resource-tree insertion与runtime IRQ programming是四阶段。

固定磁盘约定
------------

::

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

build ``.config``、compression、file sizes、RAM容量、QEMU CPU/accelerator/SMP/NUMA/完整device CLI、
runtime addresses、builtin command line、initramfs内容与microcode blob未提供，不得从commit制造。

下一入口
--------

第049章从fixed ``arch/x86/kernel/setup.c``：

.. code-block:: c

   e820__reserve_resources();

开始。049旧稿还需重新核定一个已发现边界： ``x86_init.resources.reserve_resources`` 的ordinary
x86-64实现只登记standard I/O ports，不插入IOAPIC resources；后者位于later
``pcibios_resource_survey``。049—051需要按fixed顺序重新核定：

* E820 resource objects、nosave PFNs、standard I/O ports与PCI gap的精确职责；
* VGA/OEM/wallclock/thermal LVT/MCE/refined jiffies/EFI/unwind条件，以及 ``setup_arch`` 真实出口；
* ``mm_core_init_early`` 在7.2-rc1的node/zone/``struct page``/buddy边界；
* ``start_kernel`` 的jump-label/static-call、early security、bootconfig与command-line调用顺序；
* 051出口与052 ``setup_nr_cpu_ids/setup_per_cpu_areas`` 入口只读相邻校验。

049—051批次读取清单
-------------------

#. ``AGENTS.md``、合同、本文件与 ``046-048`` 报告；
#. 第048章末尾、049—051全文、052开头；
#. fixed ``setup.c`` 从 ``e820__reserve_resources`` 到函数返回；
#. fixed ``start_kernel``、 ``mm_core_init_early``、bootconfig与command-line actual helpers；
#. fixed E820/resource/standard-I/O/PCI gap、wallclock/MCE/unwind实际调用；
#. 两份manifest游标；旧049—051的6.12.95标签与resource/buddy/second-init claims全部重核。

固定源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

均为clean、完整、非shallow、无active sparse checkout。 ``/Volumes/LinuxKernel/linux`` 不作为
fixed evidence；项目 ``.sources/`` 不承担缓存。

已知债务
--------

* 第049章起历史正文仍有旧版本、旧结构或未经fixed源码核验的断言；
* 第065、066章各有重复正文文件；
* 001—073尚未逐章进入track machine-readable catalog；
* 049—193必须继续顺序审查，不能批量机械标verified。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存审查开始前的第193章状态，不是当前事实。
