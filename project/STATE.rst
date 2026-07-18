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
   audit verified       = 001-054
   verified_through     = 054
   blocked batches      = none
   next batch           = 055-057
   next batch status    = ready

055—193中文件存在不等于技术已验证；当前pending范围是055—193。第193章审查闭合前不生产新章。

最近完成批次
------------

`052—054审查报告 <audits/linux-kernel/052-054.rst>`_：状态 ``repaired``。

本批修复了：

* ``nr_cpu_ids`` 拆开ordinary runtime upper bound、FORCE constant与UP compile paths；
* x86 first chunk的embed/page选择、fallback/panic、offset与CPU0 GDT/GS-base switch按源码固定；
* early per-CPU state只承诺template与显式APIC/ACPI/NUMA fields，不再声称整体迁移；
* node cpumask只分配backing，x86 local mask当前只分配sibling setup mask；
* boot-CPU hook按actual ``smp_ops`` 保留native/hypervisor条件；
* early NUMA checkpoint固定为skip或幂等重写，boot CPU hotplug直接补ONLINE ledger；
* possible/present/online/active、booted-once、AP sync与cpuhp state分开；
* 命令行按saved print、one-shot early guard、direct param、 ``__setup``、unknown和init arrays分流；
* fixed raw ``BOOT_IMAGE`` 恢复，root/ro/console只建立policy/spec，不执行设备动作；
* 051 saved init display order与054 runtime argv append order的差异已回补。

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

actual initrd relocation、SMP/UP、per-CPU allocator、NUMA、hypervisor hook、builtin/bootconfig tokens与
CPU/node counts受未固定build/runtime inputs影响。STATE只保存源码边界，不制造数值。

第054章结束状态
---------------

::

   current executor          = start_kernel(), command-line/init dispatch returned
   next call                 = random_init_early(command_line)
   CPU mode                  = x86-64 long mode, CPL0
   IF                        = 0 on known fixed handlers; parser warns on handler violation
   current task              = init_task
   CPU possible/present      = finalized by chapter 048
   CPU online/active         = CPU0 only
   nr_cpu_ids                = ordinary SMP highest possible ID + 1; FORCE constant; UP single CPU
   per-CPU first chunk       = SMP x86 embed/page success or UP generic single-unit path
   CPU0 per-CPU base         = runtime unit; SMP x86 direct GDT and MSR_GS_BASE loaded
   AP per-CPU units          = allocated on SMP, never executed
   early topology pointers   = corresponding APIC/ACPI/NUMA pointers retired on SMP x86
   node cpumasks             = backing allocated when NUMA; membership not batch-filled here
   sibling setup mask        = backing allocated on SMP x86
   boot CPU hook             = actual detected smp_ops returned, or UP weak no-op
   CPU0 booted-once          = set on SMP
   CPU0 AP sync              = SYNC_STATE_ONLINE on SMP
   CPU0 cpuhp state/target   = CPUHP_ONLINE / CPUHP_ONLINE
   AP hotplug/thread state   = template only / threads not initialized
   saved_command_line        = printed and unmodified
   static_command_line       = ordinary parsed/mangled; retained for any charp setter pointers
   early parameter pass      = chapter 041 result; generic chapter 054 call returned by done guard
   fixed BOOT_IMAGE          = ignored as bootloader marker
   fixed root/ro/console     = policy/name/spec stored; no mount or driver registration
   unknown kernel tokens     = conditionally classified into later sysctl/module or init env/argv
   original -- tail          = appended to argv if present and no prior parse error
   bootconfig extra init     = appended after original tail if present
   panic_later               = conditional on init env/argv capacity; fixed known tokens do not set it
   ordinary buddy RAM        = still held by memblock; free_area containers only
   slab/scheduler/AP         = not initialized / not initialized / not started
   initramfs/PID1            = not unpacked / not created

已验证的052—054关系
-----------------

* ordinary ``nr_cpu_ids`` 是ID bound，FORCE build保持NR_CPUS， ``num_possible_cpus`` 是weight；
* SMP x86 first chunk与UP generic chunk是独立compile paths；
* per-CPU unit/offset ready不等于AP started，CPU0 GS-base switch也不是task switch；
* 未显式copy的early per-CPU mutations不能假定保留；
* node cpumask allocation、CPU membership与sibling topology建立是不同阶段；
* actual ``smp_ops`` 由hypervisor detection决定，QEMU q35不等于KVM；
* early NUMA只补generic storage，CPU0 hotplug init只补ledger；
* CPU0直接ONLINE不代表运行过hotplug startup callbacks或创建hotplug threads；
* saved line与static parser line职责不同，early-only options不能由late bootconfig倒流执行；
* sysctl alias/dotted module parameter、ordinary ``__setup`` 与init env/argv是不同unknown branches；
* saved文本显示extra init在原tail前，runtime argv却先原tail、后extra init；
* root/console parameter state不等于root mount/console driver runtime。

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

第055章从fixed ``init/main.c``：

.. code-block:: c

   random_init_early(command_line);
   setup_log_buf(0);
   vfs_caches_init_early();
   sort_main_extable();
   trap_init();
   mm_core_init();

开始。055旧标题/边界需按7.2-rc1重新确认： ``mm_core_init`` 的memblock→buddy、slab、vmalloc与
page-ext/init-on-*实际顺序可能已不同于历史稿。第056预期接Maple Tree/text poking/ftrace，第057接
``sched_init``，均以fixed source自然边界为准。

055—057批次读取清单
-------------------

#. ``AGENTS.md``、合同、本文件与 ``052-054`` 报告；
#. 第054章末尾、055—057全文、058开头；
#. fixed ``start_kernel`` 从 ``random_init_early`` 到 ``sched_init`` 后真实出口；
#. random/log/vfs early alloc、exception table、x86 trap与 ``mm_core_init`` actual helpers；
#. memblock free、buddy managed counts、slab/vmalloc/page_ext/init-on-alloc/free顺序；
#. Maple Tree、poking、ftrace/early trace与scheduler runqueue/init_task actual state；
#. 两份manifest游标；旧055—057的6.12.95标签和allocator/scheduler claims全部重核。

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

* 第055章起历史正文仍有旧版本、旧结构或未经fixed源码核验的断言；
* 第065、066章各有重复正文文件；
* 001—073尚未逐章进入track machine-readable catalog；
* 055—193必须继续顺序审查，不能批量机械标verified。

历史前向终点
------------

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst`` 只保存审查开始前的第193章状态，不是当前事实。
