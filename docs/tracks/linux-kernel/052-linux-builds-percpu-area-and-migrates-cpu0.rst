第五十二章：Linux 怎样确定 CPU 编号上限并把 CPU0 迁入正式 per-CPU area？
===========================================================================

第五十一章结束时，Linux 已经得到两份持久命令行，但当前 CPU0 仍在使用启动早期的 per-CPU 基础。

``start_kernel()`` 接下来执行：

.. code-block:: c

   setup_nr_cpu_ids();
   setup_per_cpu_areas();
   smp_prepare_boot_cpu();

本章追踪到 ``smp_prepare_boot_cpu()`` 返回。

这一阶段不会唤醒 AP。它先解决另一个问题：内核源码里大量 ``DEFINE_PER_CPU`` 变量，怎样为每个 possible CPU 变成彼此独立、可通过固定偏移访问的真实内存。

四种 CPU mask 不是一回事
-----------------------

Linux 同时维护多种 CPU 集合：

``possible``
   这个 CPU 编号在本次内核生命周期中可能存在。per-CPU area、cpumask 和许多数组按 possible CPU 准备。

``present``
   固件当前描述为物理存在，或者可以参与本次启动的 CPU。

``online``
   已完成启动、可以执行普通内核任务和处理中断的 CPU。

``active``
   调度器可以向其放置普通任务的 CPU。CPU online/offline 过程中，active 状态可能晚于 online 建立或早于 online 清除。

当前只有 CPU0 online。MADT 阶段发现的其他逻辑 CPU 已可能进入 possible/present mask，但还没有收到 Linux 的 INIT/SIPI。

``NR_CPUS`` 为什么不是当前机器 CPU 数量
------------------------------------

``NR_CPUS`` 是构建时允许支持的最大 CPU 数量。

例如一个内核可能以较大的 ``CONFIG_NR_CPUS`` 编译，以便同一二进制在不同机器上运行。若本次 QEMU 只提供少量 vCPU，为每个算法都遍历完整 ``NR_CPUS`` 会浪费空间和时间。

运行时变量 ``nr_cpu_ids`` 给出当前内核需要考虑的 CPU 编号上界。

它也不是 online CPU 数量。

``setup_nr_cpu_ids()`` 怎样收缩上界
---------------------------------

函数实现只有一行核心逻辑：

.. code-block:: c

   set_nr_cpu_ids(find_last_bit(cpumask_bits(cpu_possible_mask), NR_CPUS) + 1);

它找到 ``cpu_possible_mask`` 中最高的置位编号，再加一。

假设 possible CPU 是：

.. code-block:: text

   CPU 0, 1, 2, 3

那么：

.. code-block:: text

   nr_cpu_ids = 4

若 possible mask 只有 CPU0，则 ``nr_cpu_ids = 1``。

之前的 ``nr_cpus=``、``possible_cpus=``、``nosmp``、``maxcpus=`` 和架构拓扑限制已经影响 possible mask 或允许启动的 CPU 数量。这里不重新读取 MADT，只把已形成的 mask 转换成紧凑运行时上界。

``nr_cpus`` 与 ``maxcpus`` 的限制对象不同
---------------------------------------

``nr_cpus=N`` 是硬上限，会收缩 ``nr_cpu_ids``，影响 possible CPU 编号空间和 per-CPU 资源规模。

``maxcpus=N`` 主要限制启动阶段实际 bring-up 的 CPU 数量。某些被保留为 possible/present 的 CPU 后面仍可能通过 hotplug 上线。

``maxcpus=0`` 或 ``nosmp`` 还会触发架构关闭 SMP 支持的路径。

固定命令行没有这些限制参数，因此 ``nr_cpu_ids`` 来自前面 ACPI/APIC 枚举得到的 possible mask。

per-CPU 变量解决什么问题
-----------------------

内核中常见：

.. code-block:: c

   DEFINE_PER_CPU(unsigned long, irq_count);

这不表示全系统只有一个 ``irq_count``。最终每个 possible CPU 都有自己的副本：

.. code-block:: text

   CPU0 irq_count
   CPU1 irq_count
   CPU2 irq_count
   ...

每个 CPU 高频修改自己的副本，可以减少共享 cache line 争用，也能让中断、调度、统计和当前任务指针天然绑定到本地 CPU。

链接时只有一份模板
----------------

编译器和链接器先把静态 per-CPU 变量集中到：

.. code-block:: text

   __per_cpu_start
   ...
   __per_cpu_end

这是一份模板，不是所有 CPU 的最终副本。

模板中保存变量的初始值和相对布局。例如：

.. code-block:: text

   offset +0x0000  current_task
   offset +0x0040  cpu_number
   offset +0x0080  numa_node
   ...

``setup_per_cpu_areas()`` 要为每个 possible CPU 分配一个 unit，并把模板复制进去。

first chunk 是什么
-----------------

per-CPU allocator 后面可以动态分配 ``alloc_percpu()`` 对象，但在 allocator 本身出现前，必须先有一块最早的静态区域。

这就是 per-CPU first chunk。它同时容纳：

* vmlinux 静态 per-CPU 模板；
* 架构保留空间；
* 模块静态 per-CPU 变量的预留；
* 一部分早期动态 per-CPU 空间。

x86-64 还必须为模块预留 first-chunk 空间，因为内核 text 对 per-CPU 符号通常使用 32 位重定位，需要让这些地址保持在可达范围内。

为什么优先使用 embedded first chunk
---------------------------------

x86 的 ``setup_per_cpu_areas()`` 优先调用：

.. code-block:: c

   pcpu_embed_first_chunk(...)

embedded allocator 会从启动期物理内存中取得较大的连续 backing，再把各 CPU unit 和必要空洞排布在其中。

它的优点包括：

* unit 映射紧凑；
* 页表数量较少；
* 静态 per-CPU 地址关系简单；
* 后续动态分配可直接使用 first chunk 剩余空间。

x86-64 把 ``atom_size`` 设为 ``PMD_SIZE``，使大块布局按 PMD 粒度对齐，为更高效映射留下空间。

若 embedded allocator 因内存布局、NUMA 距离或地址空间约束失败，源码回退到：

.. code-block:: c

   pcpu_page_first_chunk(...)

按 page 为各 unit 建立 backing。

两种方式都失败时，内核无法继续，因为大量基础设施依赖 per-CPU 变量，函数会 panic。

per-CPU unit 尽量靠近对应 NUMA node
----------------------------------

分配器接收两个 x86 回调：

.. code-block:: text

   pcpu_cpu_to_node(cpu)
   pcpu_cpu_distance(from, to)

前者返回第四十五至四十八章建立的 CPU-to-node 结果，后者区分 local/remote node 距离。

因此多 node 机器可以让 CPU 的 per-CPU unit 尽量落在本地 node 内存中。

固定 QEMU 未配置 NUMA 时通常全部归 node 0，所有 unit 从同一 memory node 获取。

``__per_cpu_offset`` 怎样把同一个符号变成不同副本
------------------------------------------------

first chunk 建立后，内核计算：

.. code-block:: c

   delta = pcpu_base_addr - __per_cpu_start;

然后为每个 possible CPU 写入：

.. code-block:: c

   per_cpu_offset(cpu) = delta + pcpu_unit_offsets[cpu];

所以一个 per-CPU 符号的 CPU N 地址近似是：

.. code-block:: text

   address(symbol for CPU N)
   = link-time symbol address
   + __per_cpu_offset[N]

``per_cpu(var, cpu)`` 使用指定 CPU 的 offset。

``this_cpu_*`` 操作访问当前 CPU 的 base，避免每次显式索引数组。

三个最早写入的 per-CPU 值
------------------------

x86 为每个 possible CPU 设置：

.. code-block:: c

   per_cpu_offset(cpu)
   per_cpu(this_cpu_off, cpu)
   per_cpu(cpu_number, cpu)

``this_cpu_off`` 保存当前 unit 偏移，``cpu_number`` 保存逻辑 CPU 编号。

这些值使早期汇编和 C 代码能够从当前 CPU 的 base 反推出自己的编号和其他 per-CPU 对象。

早期 APIC、ACPI、NUMA 数组为什么要迁移
------------------------------------

在正式 per-CPU area 出现前，内核不能使用普通动态 per-CPU backing，所以早期拓扑阶段把数据暂存在静态 early arrays 中，例如：

.. code-block:: text

   x86_cpu_to_apicid
   x86_cpu_to_acpiid
   x86_cpu_to_node_map

现在函数逐 CPU 把这些值复制到真实 per-CPU unit：

.. code-block:: c

   per_cpu(x86_cpu_to_apicid, cpu) = early value;
   per_cpu(x86_cpu_to_acpiid, cpu) = early value;
   per_cpu(x86_cpu_to_node_map, cpu) = early value;

并调用：

.. code-block:: c

   set_cpu_numa_node(cpu, early_cpu_to_node(cpu));

完成后，early pointer 被置为 ``NULL``，表示后续代码必须使用正式 per-CPU 数据，不能继续依赖将来会被回收的 init arrays。

CPU0 为什么必须在循环中切换 base
------------------------------

AP 尚未启动，所以只有 CPU0 正在执行。

此前 CPU0 使用的是 ``.init.data`` 中的早期 per-CPU 区。它在启动过程中已经修改过一些本地状态，这些状态不能在切换到新 unit 时丢失。

源码完成复制后，对 CPU0 调用：

.. code-block:: c

   switch_gdt_and_percpu_base(0);

在 x86-64 上，这一步把 CPU0 切到正式 per-CPU unit，并重新建立与该 CPU 对应的 GDT/per-CPU base。之后 ``%gs`` 相对的内核 per-CPU 访问会落到新的 CPU0 unit。

这是运行环境的真实变化：

.. code-block:: text

   before
   CPU0 → early static per-CPU area

   after
   CPU0 → allocated first-chunk unit 0

函数调用栈和当前任务没有切换，变化的是 per-CPU 寻址基址。

为什么 AP 现在还不需要执行切换
---------------------------

每个 AP 的 unit 已经分配，offset 和拓扑数据也已填好。

AP 后面从 trampoline 启动时，会在自己的低级 CPU 初始化路径中加载对应 GDT、stack 和 per-CPU base，然后进入 ``start_secondary()``。

当前阶段只为它们准备内存，不发送任何启动 IPI。

node-to-cpumask 与本地 CPU mask
-----------------------------

早期数据迁移后，函数调用：

.. code-block:: c

   setup_node_to_cpumask_map();
   setup_cpu_local_masks();

前者建立 node 到 CPU 集合的反向关系，让代码可以查询“这个 NUMA node 上有哪些 CPU”。

后者准备 CPU initialized/callin/callout 等 x86 SMP 启动 mask 的基础状态。

这些 mask 会在后续 AP bring-up handshake 中跟踪：

* AP 是否进入启动代码；
* BSP 是否允许它继续；
* AP 是否完成 call-in；
* CPU 是否完成架构初始化。

现在这些数据结构已经存在，仍只有 CPU0 完成启动。

再次出现的 ``sync_initial_page_table()``
-------------------------------------

``setup_per_cpu_areas()`` 最后调用：

.. code-block:: c

   sync_initial_page_table();

注释说明 per-CPU 映射必须能被 SMP boot assembly 使用。

在 x86-32 上可能需要把 kernel address range 同步回 initial page table。

固定 x86-64 路径中，前文已经确认：

.. code-block:: c

   #define swapper_pg_dir init_top_pgt
   static inline void sync_initial_page_table(void) { }

所以这里仍是公共调用点，在当前架构编译为空操作。per-CPU first chunk 的映射已经存在于正式 ``init_top_pgt`` 中。

``smp_prepare_boot_cpu()`` 为什么名字容易误解
------------------------------------------

下一条调用：

.. code-block:: c

   smp_prepare_boot_cpu();

它只是通过：

.. code-block:: c

   smp_ops.smp_prepare_boot_cpu();

进入当前平台提供的 boot-CPU hook。

普通 x86 native 实现是：

.. code-block:: c

   void __init native_smp_prepare_boot_cpu(void)
   {
       int me = smp_processor_id();

       if (!IS_ENABLED(CONFIG_SMP))
           switch_gdt_and_percpu_base(me);

       native_pv_lock_init();
   }

在 SMP x86-64 固定路径中，CPU0 已经由 ``setup_per_cpu_areas()`` 切换 GDT/per-CPU base，因此不会再次切换。

主要剩余动作是 ``native_pv_lock_init()``，让 native/paravirtualized queued spinlock 基础按当前环境就绪。

若构建的是非 SMP 内核，则没有前面 SMP per-CPU 切换路径，这个 hook 会在此为 boot CPU 完成 base 切换。

“prepare boot CPU” 不等于启动其他 CPU
----------------------------------

此时没有执行：

.. code-block:: text

   smp_prepare_cpus()
   smp_init()
   bringup_nonboot_cpus()
   wakeup_secondary_cpu_via_init()

因此没有 INIT IPI、SIPI、AP trampoline 或 ``start_secondary()``。

函数只是让已经运行的 BSP 使用正式 per-CPU 环境，并准备后续 SMP/locking 基础。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``smp_prepare_boot_cpu()`` 已返回，``early_numa_node_init()`` 尚未调用；
* CPU：只有 BSP / Linux CPU 0 online；
* interrupts：关闭；
* ``nr_cpu_ids``：已根据 ``cpu_possible_mask`` 的最高编号最终收缩；
* possible/present CPU：来自前面的 ACPI/APIC 拓扑；
* per-CPU first chunk：已建立；
* 每个 possible CPU：已有 unit offset、CPU number 和拓扑副本；
* CPU0：已切换到正式 GDT/per-CPU base；
* early APIC/ACPI/NUMA arrays：数据已迁移，early pointers 已撤销；
* node-to-cpumask 与 x86 SMP local masks：已建立；
* ``smp_prepare_boot_cpu()``：native boot-CPU hook 已执行；
* AP：尚未收到 INIT/SIPI，仍未运行 Linux；
* CPU hotplug state：尚未在下一入口完成 boot CPU 初始化；
* 普通命令行参数：尚未开始通用 ``parse_args()``；
* buddy/slab/scheduler：仍未完成；
* initramfs：尚未解包。

下一条控制流是：

.. code-block:: c

   early_numa_node_init();

随后才是 ``boot_cpu_hotplug_init()``、命令行打印和通用参数解析。

资料
----

* `Linux 6.12.95 init/main.c：CPU 数量、per-CPU 与 boot CPU 调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 kernel/smp.c：setup_nr_cpu_ids 与 SMP 启动参数 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/smp.c>`_
* `Linux 6.12.95 x86 setup_percpu.c：first chunk、offset 和 early map 迁移 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/setup_percpu.c>`_
* `Linux 6.12.95 percpu.c：embedded/page first-chunk allocator <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/percpu.c>`_
* `Linux 6.12.95 x86 smpboot.c：smp_prepare_boot_cpu 与 native boot-CPU hook <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/smpboot.c>`_
* `Linux 6.12.95 x86 percpu.h：GS-relative per-CPU 寻址基础 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/include/asm/percpu.h>`_
* `Linux CPU hotplug 文档：possible、present、online 与 hotplug 状态 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/Documentation/core-api/cpu_hotplug.rst>`_