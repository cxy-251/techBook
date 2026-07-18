第五十五章：Linux 怎样把 memblock RAM 交给 buddy 并建立运行期 MM？
====================================================================

第五十四章结束时，CPU0仍在 ``start_kernel``、IF=0；command-line/init token dispatch已完成，zone与
``struct page`` containers存在，但普通free RAM仍由memblock掌握。当前连续入口是：

.. code-block:: c

   random_init_early(command_line);
   setup_log_buf(0);
   vfs_caches_init_early();
   sort_main_extable();
   trap_init();
   mm_core_init();

本章按fixed Linux 7.2-rc1追踪到 ``mm_core_init`` 返回。真正所有权交接发生在
``memblock_free_all``；其前后还必须固定debug metadata、KHO、x86 IOMMU/traps，随后bootstrap SLUB、
vmalloc、PTI与execmem。出口page/slab/vmap allocators已可用，但late SLUB、scheduler与IRQ仍未开始。

early RNG混入的是arch line而非saved/XBC完整文本
---------------------------------------------

``random_init_early(command_line)`` 在timekeeping与IRQ前，先按build混入latent compile seed，再反复
尝试 ``arch_get_random_seed_longs``、fallback ``arch_get_random_longs``，统计实际获得的arch bits；
最后混入 ``init_utsname`` 与传入字符串。这里的pointer是041由 ``setup_arch`` 返回的arch effective
``command_line``，不含051后来单独前置/附加的bootconfig extras。

若CRNG已由更早阶段ready就reseed；否则只有 ``trust_cpu`` policy才credit arch bits。调用结束不保证
CRNG ready，也不等于later ``random_init`` 已执行；没有hardware seed的slots只减少可credit bit count，
不制造entropy。

通用log call先发布per-CPU readiness再决定是否迁移ring
---------------------------------------------------

``setup_log_buf(0)`` 首先 ``set_percpu_data_ready``，允许printk使用052正式per-CPU data。若049/arch
early call已把 ``log_buf`` 切到dynamic buffer，本次立即return。仍使用static ring时，若没有explicit
new length就按possible CPU数补算需求；size仍为0只打印一次usage stats。

需要扩展时从memblock依次分配text、descriptor与info arrays，任一步失败便释放本次已取对象并保留旧
ring；全部成功才初始化dynamic ring，在IRQ-save区迁移static records、切换global pointer，再补copy
可能来自NMI的尾部records。它不注册console，allocation failure也不是panic。

VFS early call只建hash backing，不建inode/dentry caches
-----------------------------------------------

``vfs_caches_init_early`` 先初始化fixed ``in_lookup_hashtable`` heads，再调用 ``dcache_init_early`` 与
``inode_init_early``，按memory/hashdist policy通过large-system-hash early allocator建立dentry/inode
hash backing。真正 ``KMEM_CACHE(dentry/inode)``、mount/bdev/chrdev等在later ``vfs_caches_init``；当前
没有VFS object、root mount或initramfs extraction。

exception table只在linker没有预排序时sort
------------------------------------------

``sort_main_extable`` 检查build tool留下的 ``main_extable_sort_needed`` 和非空
``__start___ex_table..__stop___ex_table``；满足才按faulting instruction address排序vmlinux table。
已经sorted或empty就是no-op。module/BPF exception tables有各自life cycle，本call不处理，也不触发
fault。

x86 trap收尾先建立CPU entry areas与正式exception state
--------------------------------------------------

``trap_init`` 依次 ``setup_cpu_entry_areas``、条件SEV-ES GHCB/VC handling、
``cpu_init_exception_handling(true)``；非FRED CPU再 ``idt_setup_traps``，最后 ``cpu_init``。early IDT
此前已支撑启动fault，这里建立per-CPU entry/TSS/IST与actual FRED-or-IDT runtime foundation。

它不执行 ``init_IRQ``、不打开IF，也不让device IRQ到达；hypervisor/SEV/FRED branch由actual CPU/build
决定。

``mm_core_init`` 先完成仍依赖memblock的准备
-------------------------------------------

x86-64 ``arch_mm_preinit`` 调用 ``pci_iommu_alloc``，按detected IOMMU policy预留/建立early backing；
结果不能仅凭q35写死。 ``init_zero_page_pfn`` 令arch选择 ``ZERO_PAGE(0)`` 并发布其PFN，给later shared
read-only zero mappings使用，不创建user mapping。

``build_all_zonelists(NULL)`` 在 ``SYSTEM_BOOTING`` 为所有nodes建立zone fallback lists，为possible CPUs
初始化boot pageset/zonestat，并设置current mems-allowed；这只建立allocation search与bootstrap local
caches，普通页尚未进入free lists。 ``page_alloc_init_cpuhp`` 以 ``cpuhp_setup_state_nocalls`` 注册
page allocator online/dead callbacks，不为已online CPU0补调用callback。

随后 ``alloc_tag_sec_init``、flatmem ``page_ext`` early backing、page poisoning/debug/
``init_on_alloc/free`` static-key policy、KFENCE pool/metadata、meminit report、KMSAN shadow与stack-depot
early backing都按build/options执行或no-op。这些必须在first ordinary allocation前确定；正文不把
conditional facility写成fixed enabled。

KHO是7.2-rc1新增的memblock-before-buddy边界
--------------------------------------------

``kho_memory_init`` 必须在memblock active且尽量靠近buddy handoff时处理kexec handover preserved/
scratch memory；feature-disabled build是inline no-op。紧接着 ``memblock_free_all`` 先
``free_unused_memmap``、归零zone managed counts并清KHO scratch-only reservation，再初始化reserved
page metadata，遍历 ``memory - reserved`` free ranges按合法最大orders交给buddy。

每个实际释放block更新zone managed/free state，返回pages总数再加到 ``totalram_pages``。kernel image、
page tables、initrd、ACPI、per-CPU/log/VFS/debug backing等仍在reserved ranges，不被释放；E820 RAM也不
等于全可分配。memblock records可暂存，但ordinary free-page ownership在这一call后属于buddy。

x86 ``mem_init`` 明确跨过bootmem时代
------------------------------------

紧随handoff，x86-64 ``mem_init`` 设置 ``after_bootmem=1``，执行actual hypervisor
``init_after_bootmem`` hook；再为deferred/reserved boot pages登记信息，条件把vsyscall加入kcore list，
并 ``preallocate_vmalloc_pages``。后者为所有process page tables必须共享的vmalloc upper levels预分配，
失败panic；它还不是通用vmap-area allocator。

SLUB bootstrap现在可以从buddy取得pages
------------------------------------

``kmem_cache_init`` 建boot ``kmem_cache_node`` 与 ``kmem_cache``，把slab state推进到PARTIAL，bootstrap
两者后建立kmalloc caches/sheaves、freelist randomization并以nocalls注册SLUB CPU-dead state。此后
``kmalloc/kmem_cache_alloc`` 基础可用； ``kmem_cache_init_late`` 的workqueue等仍要later执行。

buddy/slab ready后才完成page owner、leak与page-table caches
--------------------------------------------------------

``page_ext_init_flatmem_late`` 让page-owner等需要stack depot/slab的flatmem client完成late work；随后
``kmemleak_init``、 ``ptlock_cache_init``、arch ``pgtable_cache_init`` 与
``debug_objects_mem_init`` 依次接管early objects。具体feature-disabled stubs保持no-op。

``vmalloc_init`` 创建 ``vmap_area`` cache，初始化每个possible CPU的vmap block/deferred-free state与
vmap nodes，导入earlier ``vmlist`` entries，再建立free virtual space并发布
``vmap_initialized=true``。shrinker allocation失败只缺shrinker而不撤销已发布vmap allocator。

最后的x86与MM尾部仍有严格顺序
------------------------------

无deferred struct pages时现在执行generic ``page_ext_init``；随后 ``init_espfix_bsp`` 必须在第一个
non-init thread前建立CPU0 espfix， ``pti_init`` 又必须在espfix之后。接着完成KMSAN runtime、
``mm_cache_init`` 与 ``execmem_init``。这些calls按build/CPU policy可部分no-op，但
``mm_core_init`` 的真实出口在 ``execmem_init`` 之后，不能提前截到vmalloc。

本章结束状态
------------

* current executor：CPU0上的 ``start_kernel``； ``mm_core_init`` 已返回；
* precise next： ``maple_tree_init()`` 尚未调用；
* CPU/mode：CPU0，x86-64 CPL0，IF=0， ``init_task``，无schedule/AP；
* RNG：arch/UTS/arch-command-line已mix；CRNG readiness只按actual seed/trust policy；
* printk：per-CPU data ready，dynamic ring已存在或本次成功迁移/失败保留static；console未初始化；
* VFS：early dentry/inode hash backing已建，object caches/filesystems未建；
* exception/traps：main extable条件排序，x86 CPU entry/TSS/IST与FRED-or-IDT trap foundation完成；
* zonelists/boot pagesets/page-allocator CPUHP callbacks：已建立/初始化/nocalls注册；
* ordinary free RAM：已从memblock交给buddy，reserved ranges仍保留；
* ``after_bootmem/totalram_pages``：已发布/按actual released pages更新；
* slab：bootstrap/kmalloc基础可用，late init未执行；
* vmalloc：early entries已导入且free vmap space已发布；
* espfix/PTI/KMSAN/MM caches/execmem：按build/actual policy完成；
* scheduler/IRQ/console/initramfs/PID1：均未初始化、启用、解包或创建。

关键边界
--------

#. early RNG mix的 ``command_line`` 不含late bootconfig extras，也不保证CRNG ready。
#. log buffer migration可失败并保留static ring； ``setup_log_buf(0)`` 仍先发布per-CPU readiness。
#. VFS early hash、VFS slab object caches与filesystem mount是三个阶段。
#. trap foundation不等于device IRQ init或IF enable。
#. zonelists/pagesets存在不等于free RAM已交付；handoff点严格是 ``memblock_free_all``。
#. free range是memblock memory减reserved，不是所有E820 RAM。
#. KHO处理在memblock active时完成；feature disabled才是no-op。
#. ``mem_init`` 的vmalloc page-table preallocation与 ``vmalloc_init`` area allocator不同。
#. SLUB基础可用不等于 ``kmem_cache_init_late`` 已完成。
#. ``mm_core_init`` 出口在espfix→PTI→KMSAN/MM cache→execmem之后。

下一入口
--------

第056章从：

.. code-block:: c

   maple_tree_init();

开始，随后建立x86 text-poke mm、dynamic ftrace records与early trace buffers； ``sched_init`` 留到057。

资料
----

* `Linux 7.2-rc1固定提交：random到mm_core_init的start_kernel顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1023-L1041>`_；
* `Linux 7.2-rc1固定提交：early RNG实际mix与credit规则 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/char/random.c#L849-L888>`_；
* `Linux 7.2-rc1固定提交：mm_core_init完整顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/mm_init.c#L2696-L2749>`_；
* `Linux 7.2-rc1固定提交：memblock到buddy的交接 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memblock.c#L2351-L2409>`_；
* `Linux 7.2-rc1固定提交：x86 trap runtime foundation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/traps.c#L1661-L1677>`_；
* `Linux 7.2-rc1固定提交：x86-64 mem_init与vmalloc page-table preallocation <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/mm/init_64.c#L1376-L1401>`_；
* `Linux 7.2-rc1固定提交：SLUB bootstrap <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/slub.c#L8559-L8617>`_；
* `Linux 7.2-rc1固定提交：vmap area allocator publication <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/vmalloc.c#L5510-L5569>`_。
