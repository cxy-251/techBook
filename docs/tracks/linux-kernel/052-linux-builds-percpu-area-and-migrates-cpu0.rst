第五十二章：Linux 怎样收紧 CPU 编号并建立正式 per-CPU 寻址？
================================================================

第五十一章结束时，CPU0仍在 ``start_kernel``、IF=0；possible/present masks已经由048冻结，两份正式
命令行也已建立，但generic CPU ID upper bound与runtime per-CPU first chunk尚未完成。当前连续入口是：

.. code-block:: c

   setup_nr_cpu_ids();
   setup_per_cpu_areas();
   smp_prepare_boot_cpu();

本章按fixed Linux 7.2-rc1追踪三项返回。SMP build会把possible mask压成 ``nr_cpu_ids`` 上界，为每个
possible CPU建立per-CPU unit，并把正在执行的CPU0从early mapping切到direct GDT/runtime GS base；
最后调用actual ``smp_ops`` boot-CPU hook。这里只准备CPU-local storage与BSP hook，不发送INIT/SIPI，
AP仍未执行Linux代码。

``nr_cpu_ids`` 是编号上界而不是CPU数量
----------------------------------------

``CONFIG_SMP`` build中的 ``setup_nr_cpu_ids`` 找 ``cpu_possible_mask`` 在 ``NR_CPUS`` 范围内最后一个
set bit，再加1并交给 ``set_nr_cpu_ids``。ordinary runtime-sized build中，例如possible IDs为0和3，
结果是4而不是2：以后按CPU ID索引的arrays必须能访问ID 3；holes不被重新编号。

``NR_CPUS`` 是build ceiling，runtime ``nr_cpu_ids`` 是本次boot需要覆盖的exclusive upper bound，
``num_possible_cpus`` 才是mask weight；它们都不等于online CPU数。若启用 ``CONFIG_FORCE_NR_CPUS``，
``nr_cpu_ids`` 是compile-time ``NR_CPUS`` constant， ``set_nr_cpu_ids`` 只在computed bound不同时报
``WARN_ON`` 而不收缩。040的 ``boot_cpu_init`` 保证CPU0 possible，048才加入其他firmware-backed
possible IDs，所以find-last不会面对empty mask。

此前 ``nr_cpus=``、 ``possible_cpus=``、 ``nosmp`` 与topology capacity已经影响能进入possible mask的
IDs；本函数不重读MADT，也不唤醒CPU。positive ``maxcpus=N`` 主要限制later bring-up，不自动等同于
possible upper bound， ``maxcpus=0`` 才在early handler关闭SMP support。fixed raw GRUB line不含这些
options，但unknown builtin line仍禁止写死最终数值。

若build没有 ``CONFIG_SMP``， ``init/main.c`` 在本call site使用local inline stub，
``setup_nr_cpu_ids`` 什么也不做；UP build的single CPU identity来自compile-time path，不能把SMP的
find-last实现套过来。

SMP x86先为static与dynamic per-CPU需求规划first chunk
--------------------------------------------------------

``CONFIG_SMP`` x86链接 ``arch/x86/kernel/setup_percpu.c`` 的 ``setup_per_cpu_areas``。它打印
``NR_CPUS/nr_cpumask_bits/nr_cpu_ids/nr_node_ids`` 后选择first-chunk allocator。first chunk每个unit
包含vmlinux ``__per_cpu_start..__per_cpu_end`` 模板、reserved区与early dynamic区；x86-64还以
``PERCPU_MODULE_RESERVE`` 为module static per-CPU relocations预留可达空间。

``percpu_alloc=embed|page`` 已在041的early parameter pass决定 ``pcpu_chosen_fc``。没有强制page时先
调用 ``pcpu_embed_first_chunk``；x86-64传 ``PMD_SIZE`` atom alignment，并以
``early_cpu_to_node``/local-or-remote distance回调给allocator分组。NUMA-disabled build所有CPU都映到
node 0/local distance；NUMA topology或QEMU vCPU count未固定，故不制造unit地址、group或占用量。

embed失败会警告并回退 ``pcpu_page_first_chunk``；显式page直接走page-remapped路径。page helper按
possible CPU逐页取得backing、登记early vmalloc area、补PTE、复制static template，再commit first
chunk。两条路径都失败则panic，因为后续current CPU、scheduler、interrupt与statistics都依赖
per-CPU addressing，无法安全降级成共享变量。

first-chunk commit同时启动dynamic per-CPU allocator metadata，但不表示slab或ordinary buddy RAM已经
初始化。本批backing仍来自early allocator/memblock路径； ``memblock_free_all`` 仍在055。

offset让同一个link-time symbol落到不同unit
--------------------------------------------

allocator成功后，x86计算：

.. code-block:: c

   delta = (unsigned long)pcpu_base_addr - (unsigned long)__per_cpu_start;

并对每个possible CPU写：

.. code-block:: c

   per_cpu_offset(cpu)       = delta + pcpu_unit_offsets[cpu];
   per_cpu(this_cpu_off,cpu) = per_cpu_offset(cpu);
   per_cpu(cpu_number,cpu)   = cpu;

因此link-time per-CPU symbol加对应 ``__per_cpu_offset[cpu]`` 才得到该CPU副本； ``this_cpu`` access则
依赖当前CPU的segment/base。offset建立不让AP运行，只使其unit可以由CPU ID预先寻址。

x86只显式迁移三类early topology arrays
----------------------------------------

正式offset可用后，loop按build把early ``x86_cpu_to_apicid``、 ``x86_cpu_to_acpiid`` 与
``x86_cpu_to_node_map`` 复制到每个unit；NUMA path还调用 ``set_cpu_numa_node``，让generic per-CPU
``numa_node`` 对boot CPU和future AP都可用。随后对应 ``early_per_cpu_ptr`` 被置NULL，宣告init arrays
即将失效，later access必须走正式mapping。

这不是把整个early per-CPU area自动复制过去。源码只保证template初值和上述显式fields；
``switch_gdt_and_percpu_base`` 的注释明确说，未专门复制的early per-CPU mutations会丢失。正文因此不能
虚构“CPU0全部local state无损迁移”。

CPU0切换direct GDT与 ``MSR_GS_BASE``
------------------------------------

loop遇到logical CPU 0时调用 ``switch_gdt_and_percpu_base(0)``。x86-64先 ``load_direct_gdt``，保持
``%gs`` selector不写（写selector会清GS base），再把 ``MSR_GS_BASE`` 写成
``cpu_kernelmode_gs_base(0)``。在MSR write之前early mapping仍有效；之后kernel GS-relative per-CPU
access落到first-chunk unit 0。

当前C stack、 ``init_task``、CR3、CPL与控制流不变，也没有context switch；变化的是descriptor table与
per-CPU address base。其他possible CPU已有unit和offset，但要到各自AP low-level entry才加载自己的
runtime base。

NUMA反向mask与sibling-setup mask此时只建立容器
-----------------------------------------------

NUMA build的 ``setup_node_to_cpumask_map`` 必要时收紧 ``nr_node_ids``，随后为每个node分配一个
cpumask；它只使 ``cpumask_of_node`` backing可用，本函数没有把所有CPU bits填入这些masks。CPU membership
由later ``numa_add_cpu`` 等入口更新。non-NUMA build是inline no-op。

``setup_cpu_local_masks`` 在fixed 7.2-rc1只为 ``cpu_sibling_setup_mask`` 分配正确尺寸的boot cpumask，
供later topology sibling construction记录已处理CPU。旧稿所称“一次建立initialized/callin/callout
masks”不符合当前函数。

最后 ``sync_initial_page_table`` 是cross-x86公共call；fixed x86-64实现仍为空，不复制或重建
``init_top_pgt``。first-chunk mappings已位于当前kernel mapping中。

boot-CPU hook由实际检测到的 ``smp_ops`` 决定
----------------------------------------------

SMP x86的 ``smp_prepare_boot_cpu`` 只dispatch ``smp_ops.smp_prepare_boot_cpu()``。native default读取
当前CPU ID并调用 ``native_pv_lock_init``； ``CONFIG_PARAVIRT`` implementation在boot CPU带
``X86_FEATURE_HYPERVISOR`` 时enable ``virt_spin_lock_key``，non-paravirt build则是inline no-op。

但QEMU accelerator/hypervisor未固定：KVM、Xen、Hyper-V、VMware等detector可在更早阶段替换hook；
例如KVM hook先处理SEV per-CPU mapping与KVM guest CPU state，再调用native hook并初始化KVM spinlock。
所以本章只能记录actual detected hook已返回，不能把fixed q35写死为native或KVM。

UP build不链接x86 ``setup_percpu.c/smpboot.c``：generic ``setup_per_cpu_areas`` 为一个CPU建立dynamic
first chunk而static per-CPU保持identity mapping， ``init/main.c`` weak boot-CPU hook为no-op。这是
独立compile path，不经过上述SMP x86 loop。

本章结束状态
------------

* current executor：CPU0上的 ``start_kernel``，actual ``smp_prepare_boot_cpu`` hook已返回；
* precise next： ``early_numa_node_init()`` 尚未调用；
* CPU/mode：BSP/logical CPU0，x86-64 long mode，IF=0， ``init_task``；
* ``nr_cpu_ids``：ordinary SMP按highest possible ID+1收紧，FORCE build保持NR_CPUS；UP call为no-op；
* SMP per-CPU first chunk：embed/page实际成功路径已commit，失败则已panic而无出口；
* possible CPU units：offset、 ``this_cpu_off``、 ``cpu_number`` 与条件topology copies已写；
* CPU0：direct GDT/runtime ``MSR_GS_BASE`` 已装入，GS-relative access指向unit 0；
* early APIC/ACPI/NUMA pointers：对应build下已置NULL；
* node cpumasks：NUMA backing已分配但CPU membership不在此批量填充；
* sibling setup mask：backing已分配；
* boot-CPU hook：actual native/hypervisor implementation已执行，具体branch未固定；
* AP：只有storage，未收INIT/SIPI、未online/active；
* buddy ordinary RAM/slab/scheduler：仍未完成；command-line普通dispatch尚未开始。

关键边界
--------

#. ordinary runtime ``nr_cpu_ids`` 是highest possible ID的exclusive bound；FORCE build保持constant。
#. SMP与UP是不同compile paths；不能把SMP find-last/x86 first-chunk loop套到UP。
#. embed/page是actual allocator alternatives；first chunk既含static template也承载reserved/dynamic区。
#. unit/offset ready不等于对应AP已运行。
#. CPU0 switch改变GDT/GS base，不改变task、stack、CR3或调度状态。
#. 只有源码显式列出的early topology fields被迁移，其他early per-CPU mutation不保证保留。
#. node-to-cpumask allocation不等于membership填充；local-mask helper当前只分配sibling setup mask。
#. x86-64 ``sync_initial_page_table`` no-op；不应制造第二次page-table sync。
#. ``smp_ops`` 受hypervisor detection影响，QEMU q35不足以选定native/KVM hook。
#. 本章不启动AP，也不初始化boot CPU hotplug ledger。

下一入口
--------

第053章从：

.. code-block:: c

   early_numa_node_init();
   boot_cpu_hotplug_init();

开始。进入前CPU0已使用正式per-CPU base，但 ``cpuhp_state`` 尚未被登记为boot CPU的ONLINE账本。

资料
----

* `Linux 7.2-rc1固定提交：start_kernel的CPU ID/per-CPU/boot hook顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L994-L1008>`_；
* `Linux 7.2-rc1固定提交：setup_nr_cpu_ids与early SMP limits <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/smp.c#L970-L1002>`_；
* `Linux 7.2-rc1固定提交：x86 first chunk、offset、early maps与CPU0 switch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup_percpu.c#L111-L226>`_；
* `Linux 7.2-rc1固定提交：percpu allocator选择与generic UP path <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/percpu.c#L2735-L2765>`_；
* `Linux 7.2-rc1固定提交：direct GDT与x86-64 GS base switch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/cpu/common.c#L784-L823>`_；
* `Linux 7.2-rc1固定提交：x86 boot-CPU smp_ops dispatch <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/smpboot.c#L1198-L1201>`_；
* `Linux 7.2-rc1固定提交：native boot-CPU hook <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/smpboot.c#L1267-L1279>`_；
* `Linux 7.2-rc1固定提交：KVM对boot-CPU hook的替换示例 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/kvm.c#L708-L719>`_。
