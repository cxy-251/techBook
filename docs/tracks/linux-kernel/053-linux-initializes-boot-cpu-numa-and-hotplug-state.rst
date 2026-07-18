第五十三章：Linux 怎样补齐 NUMA node 并把 CPU0 登记为 hotplug ONLINE？
=======================================================================

第五十二章结束时，SMP路径中的CPU0已经使用正式per-CPU unit，其他possible CPUs也有unit/offset但尚未
运行；UP路径则已建立single-unit dynamic per-CPU allocator。 ``start_kernel`` 紧接着执行：

.. code-block:: c

   early_numa_node_init();
   boot_cpu_hotplug_init();

本章追踪两项返回。第一项是generic per-CPU NUMA compatibility checkpoint，x86可能skip或重写已经
迁移的数据；第二项把早已运行且已在global masks中online的CPU0，直接记入per-CPU hotplug ledger的
完成态。这里没有CPU-up transaction、hotplug callbacks或AP wakeup。

generic NUMA checkpoint受两层compile guard控制
-----------------------------------------------

``early_numa_node_init`` 只在 ``CONFIG_USE_PERCPU_NUMA_NODE_ID`` 下存在工作；若arch还以macro形式
自定义 ``cpu_to_node``，内层 ``#ifndef cpu_to_node`` 又会把loop编译掉。实际包含loop时，它遍历
``for_each_possible_cpu``，执行：

.. code-block:: c

   set_cpu_numa_node(cpu, early_cpu_to_node(cpu));

possible而非online是正确范围：future AP在启动前就需要自己的node identity。loop不分配node，不读
SRAT/MADT，也不更改possible mask，只把arch early lookup的结果写进generic per-CPU ``numa_node``。

x86 NUMA path在052 ``setup_per_cpu_areas`` 已经为每个possible CPU执行同一方向的
``set_cpu_numa_node``。因此normal generic-accessor build即使包含本loop，也只是把同一early result
再次写入； ``CONFIG_DEBUG_PER_CPU_MAPS`` 等x86 macro override可让它compile out；non-NUMA build也
skip。build ``.config`` 未固定，所以正文记录这三种条件，不制造一次“重新发现NUMA topology”。

global CPU masks早在hotplug ledger之前成立
------------------------------------------

040的 ``boot_cpu_init`` 已把当前boot CPU依次加入online、active、present与possible masks，并在SMP
build记录 ``__boot_cpu_id``。048随后扩展possible/present topology，但online/active始终只有CPU0。

``boot_cpu_hotplug_init`` 不再改这些global masks。它解决的是另一份state：
``DEFINE_PER_CPU(struct cpuhp_cpu_state, cpuhp_state)``。这个struct的template只把 ``fail`` 初始化为
``CPUHP_INVALID``；CPU0的runtime copy直到正式per-CPU base可用后才能安全写入。

SMP ledger先记录“至少成功启动过一次”
-----------------------------------

``CONFIG_SMP`` 下，函数把 ``smp_processor_id()`` 加入 ``cpus_booted_once_mask``。它是历史集合而非
当前online mask：CPU以后offline时仍可保留“曾完成low-level boot”的事实，供后续bring-up、IPI或
microcode policy判断。当前写入的是CPU0，因为没有调度、迁移或AP executor。

紧接着对CPU0的 ``cpuhp_state.ap_sync_state`` 执行 ``atomic_set(..., SYNC_STATE_ONLINE)``。普通AP
bring-up会用DEAD/KICKED/ALIVE/SHOULD_ONLINE/ONLINE等同步值协调control CPU与AP；BSP没有经历
INIT/SIPI handshake，故直接把现实映射为ONLINE。这个field和write在fixed源码中由 ``CONFIG_SMP``
guard，不需要再假设 ``CONFIG_HOTPLUG_CORE_SYNC`` 才存在。

``state`` 与 ``target`` 也直接跳到 ``CPUHP_ONLINE``
----------------------------------------------------

无论SMP还是UP，最后两条都是：

.. code-block:: c

   this_cpu_write(cpuhp_state.state, CPUHP_ONLINE);
   this_cpu_write(cpuhp_state.target, CPUHP_ONLINE);

``state`` 表示当前ledger position， ``target`` 表示此次transition希望到达的位置。两者相等说明
CPU0没有pending up/down operation。write通过052已经就绪的current per-CPU addressing落到CPU0 unit。

这里没有从 ``CPUHP_OFFLINE`` 逐级执行startup steps。boot CPU在hotplug core完整可用前就承担了
``start_kernel``，大量global/CPU0 init会沿主启动线完成；本函数只是把state machine账本直接对齐到
这项事实。也没有取得runtime CPU hotplug locks：IF=0且仍只有CPU0执行，hotplug concurrency尚不存在。

AP storage存在不等于AP state前进
------------------------------

SMP first chunk已给其他possible CPUs复制 ``cpuhp_state`` template，但本函数只使用 ``this_cpu``，不
遍历AP units。它们没有加入 ``cpus_booted_once_mask``，没有收到sync ONLINE，也没有运行callbacks。

``cpuhp_threads_init`` 要到later ``smp_init`` 才创建per-CPU hotplug threads并初始化其运行设施；本章
也不调用 ``cpuhp_up_callbacks``、completion wait/complete或 ``cpu_up``。因此CPU0 ledger为ONLINE与
“hotplug runtime已完整启动”仍是两个边界。

出口仍在命令行打印之前
----------------------

两项return后CPU0仍处于long mode CPL0、IF=0、 ``init_task``；没有schedule或AP activity。下一条
``print_kernel_cmdline(saved_command_line)`` 只会输出051保留的observable副本，之后才进入ordinary
parameter dispatch。

本章结束状态
------------

* current executor：CPU0上的 ``start_kernel``， ``boot_cpu_hotplug_init`` 已返回；
* precise next： ``print_kernel_cmdline(saved_command_line)`` 尚未调用；
* CPU/mode：logical CPU0，x86-64 CPL0，IF=0， ``init_task``；
* CPU-to-node：x86正式per-CPU identity已从052存在；generic loop按compile guards skip或幂等重写；
* CPU masks：CPU0 online/active，其他firmware CPUs只possible/present；本章不改mask；
* ``cpus_booted_once_mask``：SMP build已包含CPU0；
* CPU0 ``ap_sync_state``：SMP build为 ``SYNC_STATE_ONLINE``；
* CPU0 hotplug ``state/target``：均为 ``CPUHP_ONLINE``；
* AP hotplug units：只有template/storage，未推进、未启动；
* hotplug threads/callback transitions：尚未建立/未执行；
* command line：saved/static副本已存在，尚未打印和ordinary parse；
* ordinary buddy RAM/slab/scheduler/initramfs：仍未完成。

关键边界
--------

#. ``early_numa_node_init`` 是compile-conditional per-CPU write，不重新解析firmware topology。
#. x86 052已写generic NUMA node；053 loop即使存在也是幂等重写。
#. possible/present/online/active masks与 ``cpuhp_state`` 是不同账本。
#. ``cpus_booted_once_mask`` 保存历史启动事实，不等于当前online mask。
#. CPU0直接标ONLINE是boot-CPU bootstrap exception，不代表逐级运行了hotplug callbacks。
#. ``ap_sync_state`` 的write由SMP guard决定，不应误写成只在HOTPLUG_CORE_SYNC build出现。
#. 本函数只写 ``this_cpu``；AP state/storage不因CPU0登记而前进。
#. hotplug state threads、completion protocol与AP bring-up均在later路径。

下一入口
--------

第054章从：

.. code-block:: c

   print_kernel_cmdline(saved_command_line);

开始，随后复查early parameters、解析 ``static_command_line``，再把 ``--`` 后与bootconfig extra init
tokens送入 ``argv_init``；出口停在 ``random_init_early(command_line)`` call前。

资料
----

* `Linux 7.2-rc1固定提交：early NUMA与boot hotplug的start_kernel顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1002-L1011>`_；
* `Linux 7.2-rc1固定提交：early_numa_node_init compile guards与possible loop <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L863-L874>`_；
* `Linux 7.2-rc1固定提交：boot_cpu_init masks与boot_cpu_hotplug_init ledger <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cpu.c#L3153-L3182>`_；
* `Linux 7.2-rc1固定提交：cpuhp per-CPU struct与SMP booted-once mask <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cpu.c#L47-L92>`_；
* `Linux 7.2-rc1固定提交：generic per-CPU NUMA accessors <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/topology.h#L79-L109>`_；
* `Linux 7.2-rc1固定提交：x86在setup_per_cpu_areas迁移NUMA identity <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup_percpu.c#L174-L202>`_。
