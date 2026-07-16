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
   audit verified       = 001-042
   verified_through     = 042
   blocked batches      = none
   next batch           = 043-045
   next batch status    = ready

043—193中文件存在不等于技术已验证；当前pending范围是043—193。第193章审查闭合前不生产新章。

最近完成批次
------------

`040—042审查报告 <audits/linux-kernel/040-042.rst>`_：状态 ``repaired``。

本批修复了：

* 三章从历史6.12.95叙事重写为fixed Linux 7.2-rc1，并逐章固定自然源码边界；
* fixed x86 ``smp_setup_processor_id`` 实际落到generic weak no-op，CPU0身份不在040重选；
* platform policy设置与041 BDA/EBDA physical reservation分开；
* GRUB原始command line保留 ``BOOT_IMAGE=/boot/bzImage``，并与未固定
  ``CONFIG_CMDLINE`` 的append/override结果分开；
* 041 early traps只替换DB/BP/条件VE，formal early ``#PF`` 继续服务direct-map自举；
* reservation固定为kernel、0—64 KiB、R/N、条件setup_data/BIOS/SNB；old Z明确不reserve；
* 当前 ``setup_data=0``，reserve与parse两个loop均为空；
* working/firmware/kexec三份E820与memblock reserved、iomem resource、PTE identity分开；
* ``setup_initial_init_mm`` 只登记virtual boundaries，active CR3仍是 ``early_top_pgt``；
* ``parse_early_param`` 用静态 ``done`` 保证只实际执行一次；
* max PFN按working E820的RAM/ACPI end、arch limit与条件MTRR重算，未制造RAM/PFN数值；
* memory KASLR只选择virtual layout，完整direct map留给043。

当前符号
--------

::

   Z   = original boot_params physical address; copied, no longer reserved
   R/N = original initramfs physical address / true size; reserved to PAGE_ALIGN(R+N)
   L   = build LOAD_PHYSICAL_ADDR
   O   = actual physical kernel output base / formal phys_base
   V   = relocation virtual position value

``Z`` 的内容已由formal global ``boot_params`` / ``boot_command_line`` 接管，后续RAM allocator可重用
原range；这不表示截至042已经覆盖。 ``R/N`` 仍只获得physical reservation，未relocate或unpack。

第042章结束状态
---------------

::

   current executor        = setup_arch(), early_alloc_pgt_buf call pending
   CPU                     = BSP / logical CPU0
   CPU mode                = 64-bit long mode, kernel high mapping
   IF / DF                 = 0 / 0
   current task            = init_task
   current stack           = init_task initial task stack; end magic installed
   CPU masks               = CPU0 possible/present/online/active
   GSBASE / GDT            = CPU0 initial per-CPU offset / CPU0 gdt_page
   active CR3              = early_top_pgt
   init_mm.pgd             = init_top_pgt (swapper_pg_dir alias), not active yet
   init_mm ranges          = _text / _etext / _edata / current _brk_end recorded
   early IDT               = DB/BP + conditional VE real early gates; PF still early helper
   early IRQ state         = early_boot_irqs_disabled=true; normal IRQs not enabled
   effective command line  = GRUB line with conditional CONFIG_CMDLINE append/override
   early params            = parsed once; done=1
   EFI_BOOT                = false on SeaBIOS/GRUB i386-pc path
   memblock.reserved       = kernel + low64K + R/N + BIOS + conditional platform tables/pages
   memblock.memory         = not populated from E820
   setup_data              = 0; no extension nodes
   E820 firmware/kexec     = loader snapshots
   E820 working            = early params + kernel/BIOS + conditional GART/MTRR fixes applied
   iomem resources         = kernel code/rodata/data/bss + conditional ROM resources
   max_pfn                 = computed symbolic working-E820 result
   max_possible_pfn        = max_pfn
   max_low_pfn             = computed with 4 GiB boundary
   max_low_pfn_mapped      = distinct existing direct-map frontier
   memory KASLR layout     = selected conditionally; page tables not built here
   initramfs               = R/N reserved; not relocated or unpacked
   early brk               = still open
   early page-table buffer = not allocated

已验证的040—042关系
-----------------

* ``x86_64_start_reservations`` 当前不再次copy Z，选择ordinary PC legacy policy并进入
  ``start_kernel``；
* 040依次建立stack sentinel、conditional early subsystems、IRQ software state和CPU0 masks，停在
  ``setup_arch`` 前；
* 041先输出GRUB line，再处理built-in line； ``early_cpu_init`` 后才用actual physical-address bits
  设置 ``iomem_resource.end``；
* 041顺序固定为prepare cmdline/IDT/CPU/ioremap → parse boot params → early reservations → base E820
  import/sanitize/copy → empty setup_data parse → EDD copy；
* kernel K/R仍可位于E820 RAM，同时被memblock reserved；Z可位于RAM但不再reserved；
* 042顺序固定为init_mm ranges → NX → one-shot early params → platform probes → resource/E820 fixes →
  max PFN/cache/MTRR → memory virtual layout → max low PFN → MP-table finder；
* 042不导入 ``memblock.memory``、不分配page-table buffer、不封存brk、不load
  ``init_top_pgt``。

固定磁盘约定
------------

::

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

build ``.config``、compression、file sizes、RAM容量、QEMU CPU model/完整CLI、runtime addresses、
builtin command line与microcode blob未提供，不得从commit制造。

下一入口
--------

第043章从fixed ``arch/x86/mm/init.c``：

.. code-block:: c

   void __init early_alloc_pgt_buf(void)
   {
       unsigned long tables = INIT_PGT_BUF_SIZE;
       phys_addr_t base;

       base = __pa(extend_brk(tables, PAGE_SIZE));
       ...

开始。043—045需要重新核定旧稿，不继承其6.12.95标签或状态结论：

* ``early_alloc_pgt_buf``、 ``reserve_brk``、x86-64 ``cleanup_highmap``、
  ``e820__memblock_setup`` 的fixed顺序和allocator可用范围；
* memory-encryption/random seed/EFI mirror等插入步骤是否改变旧043的自然出口；
* real-mode trampoline、 ``init_mem_mapping``、active CR3与early PF replacement的真实边界；
* ``setup_log_buf(1)``、 ``reserve_initrd`` 和ACPI table init的fixed 7.2-rc1顺序；
* ``vsmp_init``、early ACPI/MADT、MP fallback、DT/NUMA及 ``initmem_init`` 的实际分支；
* 第046章第一入口只作相邻校验，不越序修改。

043—045批次读取清单
-------------------

#. ``AGENTS.md``、合同、本文件与 ``040-042`` 报告；
#. 第042章末尾、043—045全文、046开头；
#. fixed ``setup.c`` 从 ``early_alloc_pgt_buf`` call开始到 ``initmem_init`` 后的自然边界；
#. fixed x86 ``mm/init.c``、 ``mm/init_64.c``、 ``kernel/e820.c``、 ``realmode/init.c`` 与memblock；
#. fixed printk/initrd/ACPI/MP/NUMA实际被调用的helper；
#. 两份manifest游标；旧043—045的版本标签、具体容量和调用顺序一律重新核验。

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

* 第043章起历史正文仍有旧版本、旧结构或未经fixed源码核验的断言；
* 第065、066章各有重复正文文件；
* 001—073尚未逐章进入track machine-readable catalog；
* 043—193必须继续顺序审查，不能批量机械标verified。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存审查开始前的第193章状态，不是当前事实。
