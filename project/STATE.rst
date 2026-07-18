项目状态
========

最后更新
--------

2026-07-18。

当前模式
--------

::

   mode                 = retrospective-audit
   forward production   = paused
   content present      = 001-193
   audit verified       = 001-051
   verified_through     = 051
   blocked batches      = none
   next batch           = 052-054
   next batch status    = ready

052—193中文件存在不等于技术已验证；当前pending范围是052—193。第193章审查闭合前不生产新章。

最近完成批次
------------

`049—051审查报告 <audits/linux-kernel/049-051.rst>`_：状态 ``repaired``。

本批修复了：

* working E820 current resources与 ``e820_table_kexec`` firmware-map view分开；
* high device-like E820和IOAPIC resource insertion都移回later PCI survey；
* standard resource hook只登记legacy I/O ports，PCI gap也只是later allocation hint；
* wallclock、thermal LVT、MCE、refined jiffies与ORC按真实build/runtime边界收紧；
* ``setup_arch`` 真实return后， ``mm_core_init_early`` 的HugeTLB条件路径和
  ``free_area_init`` 三阶段固定；
* zone span/present/managed/free、sparse metadata、possible node与 ``N_MEMORY`` 分开；
* x86 generic jump-label/static-call calls固定为041 arch-early初始化后的幂等返回；
* early LSM集合保持build-dependent；bootconfig trailer切除与XBC接受分开；
* fixed raw line恢复 ``BOOT_IMAGE=/boot/bzImage``，saved/static副本与extra ordering固定；
* 051只建立字符串，不提前执行第054章的普通参数分发。

当前符号
--------

::

   Z   = original boot_params physical address; copied and no longer reserved
   R/N = GRUB original initramfs physical address / true size
   E   = PAGE_ALIGN(R + N), the originally reserved initrd end
   B   = logical initrd_end after an optional valid bootconfig trailer is cut
   L   = build LOAD_PHYSICAL_ADDR
   O   = actual physical kernel output base / formal phys_base
   V   = relocation virtual position value

actual initrd relocation branch、HugeTLB reservations、memory model、zone sizes、early LSM set、bootconfig
extras与CPU count受未固定build/effective CLI/runtime inputs影响。STATE只保存源码边界，不制造数值。

第051章结束状态
---------------

::

   current executor          = start_kernel(), setup_command_line returned
   next call                 = setup_nr_cpu_ids()
   CPU mode                  = x86-64 long mode
   IF / DF                   = 0 / 0
   current task              = init_task
   CPU possible/present      = finalized by chapter 048
   CPU online/active         = CPU0 only
   nr_cpu_ids                = architecture value; generic compacting call still pending
   per-CPU areas             = not established; CPU0 migration pending
   active CR3                = swapper_pg_dir = init_top_pgt
   memblock.memory           = working-E820 RAM with NUMA node identities
   E820 current resources    = system ranges inserted; high device-like ranges delayed
   firmware-map early view  = registered from e820_table_kexec
   hibernation nosave holes  = registered
   legacy I/O resources     = busy in ioport tree
   IOAPIC resources          = objects only; not inserted into iomem tree
   pci_mem_start             = gap/fallback hint; no BAR assigned
   setup_arch                = returned
   HugeTLB early reserve     = conditional by build/effective options
   zone/node bounds          = initialized from memblock
   sparse/subsection map     = initialized per configured memory model
   struct page metadata      = required early initialization done; deferred part conditional
   buddy containers          = initialized
   buddy managed/free RAM    = ordinary memblock RAM not yet released
   jump labels/static calls  = arch-early state retained; generic calls returned idempotently
   early LSM                 = linked early entries initialized
   bootconfig                = trailer cut if valid; XBC extras conditional
   saved_command_line        = complete observable memblock copy
   static_command_line       = mutable kernel-parse memblock copy
   fixed raw GRUB line       = BOOT_IMAGE=/boot/bzImage root=/dev/sda1 ro console=ttyS0
   ordinary parameter parse  = pending chapter 054
   slab/scheduler/AP         = not initialized / not initialized / not started
   initramfs                 = not ordinarily unpacked

已验证的049—051关系
-----------------

* resource ownership、memblock ownership与page-table mapping互不等同；
* working E820发布current resources，kexec snapshot发布firmware-map view；
* high device-like E820与IOAPIC resource objects都延后到PCI survey插入；
* nosave holes不reserve/unmap，standard I/O request不编程legacy devices；
* ``pci_mem_start`` 不是已分配BAR，arch最后的software/candidate init也不启动对应runtime；
* ``mm_core_init_early`` 只调用HugeTLB CMA、HugeTLB boot allocation与 ``free_area_init``；
* zone span、present RAM、managed pages与free buddy pages是四个边界；
* ``free_area[]`` 与 ``struct page`` 已建不表示ordinary RAM已经free-to-buddy；
* x86在041已完成两种static patch init，051 generic calls由guard直接返回；
* early LSM只完成early group，ordinary security init仍在后面；
* bootconfig trailer切除、XBC接受和extra command-line生成是分开的条件；
* extra kernel line前置，extra init args排在 ``--`` 后且先于原init args；
* saved副本保留观察文本，static副本留给later原地解析。

固定磁盘约定
------------

::

   menuentry 'Linux 7.2-rc1' {
       linux /boot/bzImage root=/dev/sda1 ro console=ttyS0
       initrd /boot/initramfs.img
   }

build ``.config``、compression、file sizes、RAM容量、QEMU CPU/accelerator/SMP/NUMA/完整device CLI、
runtime addresses、builtin command line、initramfs内容/bootconfig与microcode blob未提供，不得从commit
制造。

下一入口
--------

第052章从fixed ``init/main.c``：

.. code-block:: c

   setup_nr_cpu_ids();
   setup_per_cpu_areas();
   smp_prepare_boot_cpu();

开始，审查到 ``smp_prepare_boot_cpu`` 返回。第053章预期从 ``early_numa_node_init`` 接续，第054章
处理 ``print_kernel_cmdline/parse_early_param/parse_args``；以fixed 7.2-rc1实际源码重新确认边界，不能
继承历史6.12.95叙述。

052—054批次读取清单
-------------------

#. ``AGENTS.md``、合同、本文件与 ``049-051`` 报告；
#. 第051章末尾、052—054全文、055开头；
#. fixed ``start_kernel`` 从 ``setup_nr_cpu_ids`` 到ordinary parameter dispatch结束；
#. generic ``setup_nr_cpu_ids``、percpu allocator与x86 ``smp_prepare_boot_cpu`` actual helpers；
#. ``early_numa_node_init``、 ``boot_cpu_hotplug_init`` 与CPUHP state；
#. ``parse_early_param`` one-shot state、 ``parse_args``、unknown boot option与init args ordering；
#. 两份manifest游标；旧052—054的6.12.95版本、CPU mask/per-CPU/parameter effect claims全部重核。

固定源码工作树
--------------

::

   /Volumes/LinuxKernel/seabios HEAD       = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   /Volumes/LinuxKernel/qemu HEAD          = a759542a2c62f0fd3b65f5a66ad9868201014669
   /Volumes/LinuxKernel/grub HEAD          = d38d6a1a9b79427848976f53d474392cd29c2a71
   /Volumes/LinuxKernel/linux-7.2-rc1 HEAD = 7404ce51637231382873d0b55edabc2f3b841a9d

均为clean、完整、非shallow、无active sparse checkout。 ``/Volumes/LinuxKernel/linux`` 不作为fixed
evidence；项目 ``.sources/`` 不承担缓存。

已知债务
--------

* 第052章起历史正文仍有旧版本、旧结构或未经fixed源码核验的断言；
* 第065、066章各有重复正文文件；
* 001—073尚未逐章进入track machine-readable catalog；
* 052—193必须继续顺序审查，不能批量机械标verified。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存审查开始前的第193章状态，不是当前事实。
