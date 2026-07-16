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
   audit verified       = 001-045
   verified_through     = 045
   blocked batches      = none
   next batch           = 046-048
   next batch status    = ready

046—193中文件存在不等于技术已验证；当前pending范围是046—193。第193章审查闭合前不生产新章。

最近完成批次
------------

`043—045审查报告 <audits/linux-kernel/043-045.rst>`_：状态 ``repaired``。

本批修复了：

* 三章从历史6.12.95叙事重写为fixed Linux 7.2-rc1，并按自然源码边界固定043/044/045出口；
* pgt buffer在 ``reserve_brk`` 前从brk取得；封存后 ``extend_brk`` 不再是current mapping可靠后备；
* E820 RAM、memblock memory/reserved与direct-map PTE身份分开，low 1MiB同时reserved与mapped；
* direct map只覆盖ISA兼容range与memblock RAM，记录mapped PFN后才切 ``init_top_pgt`` 并flush；
* printk early migration按条件分配text/descriptors/infos，失败回滚并补扫NMI-late records；
* initramfs修正为 ``/boot/initramfs.img``，按actual mapped PFN选择fast identity或safe relocation；
* ACPI override专用cpio scan与initial table定位/reservation分开；
* fixed ``early_platform_quirks`` 只判断Apple vendor，不附加PCI/HPET/IOMMU工作；
* early MADT/MP pass只登记LAPIC address，不枚举processor/IOAPIC/IRQ entries；
* SRAT affinity、logical CPU topology、node online与buddy allocator四个阶段严格分开；
* current ``setup_data=0`` 令 ``initial_dtb=0``，没有DT CPU/APIC topology。

当前符号
--------

::

   Z   = original boot_params physical address; copied and no longer reserved
   R/N = GRUB original initramfs physical address / true size
   E   = PAGE_ALIGN(R + N)
   L   = build LOAD_PHYSICAL_ADDR
   O   = actual physical kernel output base / formal phys_base
   V   = relocation virtual position value

initrd fast path保留original ``[R,E)`` 并令 ``initrd_start=R+PAGE_OFFSET``；relocation path先把N bytes
复制到 ``max_pfn_mapped`` 以下的新reserved range，成功后free original ``[R,E)``。actual branch受
未固定build/effective memory limits影响，不能在STATE中写死。

第045章结束状态
---------------

::

   current executor         = setup_arch(), initmem_init returned
   next call                = dma_contiguous_reserve(max_pfn_mapped << PAGE_SHIFT)
   CPU                      = BSP / logical CPU0 only executing
   CPU mode                 = 64-bit long mode
   IF / DF                  = 0 / 0
   current task             = init_task
   active CR3               = swapper_pg_dir = init_top_pgt
   old active root          = early_top_pgt no longer active
   early brk                = reserved and sealed; _brk_start = 0
   early pgt buffer         = reserved brk pages; 8 or 16 by build
   high kernel PMDs         = tightened to text through rounded current brk end
   memblock.memory          = page-aligned working-E820 RAM with NUMA node identity
   memblock.reserved        = kernel + low1M + initramfs/current copy + firmware/conditional ranges
   memblock current limit   = get_max_mapped()
   direct map               = ISA range plus actual memblock RAM ranges
   active mapped frontier   = pfn_mapped[] / max_pfn_mapped
   real-mode trampoline     = low storage reserved; contents not yet initialized
   early page-fault entry   = real PF gate or FRED exception setup; early mapping helper replaced
   printk ring              = dynamic iff requested and allocations succeeded; otherwise static
   printk percpu / console  = not ready / not formally initialized
   initrd virtual range     = valid fast or relocated identity; archive not unpacked
   EFI_BOOT                 = false; EFI secure-boot status switch skipped
   ACPI initial tables      = located/reserved on successful enabled SeaBIOS path
   ACPI early MADT          = LAPIC base registered; fixed q35 has no LAPIC address override entry
   acpi_lapic               = 1 on successful fixed q35 MADT path
   MP early parser          = skipped because acpi_lapic, or LAPIC-address-only fallback
   MADT/MP CPU and IOAPIC   = full entry parsing not yet performed
   flattened DT            = initial_dtb = 0; no populated tree
   NUMA                     = configured source result or dummy node 0 fallback
   memory nodes             = valid memory-range nodes online; zones not initialized
   CPU topology / APs       = not fully enumerated / no AP online
   buddy allocator          = not initialized

已验证的043—045关系
-----------------

* ``early_alloc_pgt_buf`` 必须先消费开放brk， ``reserve_brk`` 随后保护used range并令
  ``_brk_start=0``；
* ``cleanup_highmap`` 清共享lower-level entries，明确translation回收发生在后续CR3切换/flush；
* ``e820__memblock_setup`` 只把RAM加入memory、SOFT_RESERVED加入reserved，并暂把low 1MiB标KHO
  scratch；
* ordinary x86-64 real-mode reserve在1MiB下找storage，size非0时reserve完整low 1MiB并清scratch；
* ``init_mem_mapping`` 映射ISA与memblock RAM，reserved-over-RAM仍mapped，physical holes不变成RAM；
* ``load_cr3(swapper_pg_dir)`` 后active root才是 ``init_top_pgt``；memblock limit随后扩大到actual
  mapped frontier；
* ``setup_log_buf(1)`` 不宣布per-CPU data ready，也不完成console；
* ``reserve_initrd`` 以 ``pfn_range_is_mapped`` 决定不copy或relocate，旧range只在copy成功后free；
* ``acpi_table_upgrade`` 只扫描 ``kernel/firmware/acpi/``， ``acpi_boot_table_init`` 只定位/保护
  initial tables；
* q35不命中ScaleMP和I/O-delay DMI quirks， ``early_platform_quirks`` 只得到非Apple结果；
* early MADT读取header LAPIC地址及可选override；fixed QEMU MADT没有override，返回0后设置
  ``acpi_lapic/smp_found_config``；
* early MP parser即使fallback也在processor configuration blocks前返回；
* ``initmem_init`` 只建立NUMA memory-node归属，不建立zones/buddy或完整logical CPU topology。

固定磁盘约定
------------

::

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

build ``.config``、compression、file sizes、RAM容量、QEMU CPU model/完整CLI、runtime addresses、
builtin command line、initramfs内容与microcode blob未提供，不得从commit制造。

下一入口
--------

第046章从fixed ``arch/x86/kernel/setup.c``：

.. code-block:: c

   dma_contiguous_reserve(max_pfn_mapped << PAGE_SHIFT);

开始。046旧开头把045误写成“已从MADT/MP建立早期CPU/APIC拓扑”，这是pending历史错误，下一批必须
首先改成“只登记LAPIC地址，NUMA memory-node identity已建立”。046—048需沿fixed顺序重新核定：

* CMA、crashkernel、early xHCI debug console及其build/effective option条件；
* ``x86_init.paging.pagetable_init``、KASAN、 ``sync_initial_page_table`` 的真实边界；
* TDX/EFI/ESRAM/ACPI table reserve、 ``reserve_standard_io_resources`` 等插入调用；
* ``early_acpi_boot_init`` 与后续 ``acpi_boot_init`` 的职责分界，full MADT CPU/IOAPIC entries实际
  在哪一章出现；
* 048相邻出口与049入口，只读校验后按自然源码边界重写三章。

046—048批次读取清单
-------------------

#. ``AGENTS.md``、合同、本文件与 ``043-045`` 报告；
#. 第045章末尾、046—048全文、049开头；
#. fixed ``setup.c`` 从 ``dma_contiguous_reserve`` 开始到048自然出口；
#. fixed CMA/crashkernel/xdbc/x86 paging/KASAN/ACPI/APIC实际被调用helper；
#. QEMU/SeaBIOS仅在对应firmware事实需要时读取，不从默认CLI制造runtime结果；
#. 两份manifest游标；旧046—048的版本标签、CPU topology与调用顺序一律重新核验。

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

* 第046章起历史正文仍有旧版本、旧结构或未经fixed源码核验的断言；
* 第065、066章各有重复正文文件；
* 001—073尚未逐章进入track machine-readable catalog；
* 046—193必须继续顺序审查，不能批量机械标verified。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存审查开始前的第193章状态，不是当前事实。
