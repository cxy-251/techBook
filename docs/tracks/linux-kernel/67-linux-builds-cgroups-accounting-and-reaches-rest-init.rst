第六十七章：Linux 怎样建立 cgroup 与 accounting，并到达 rest_init？
=================================================================

第六十六章结束时，namespace、security、VFS、page cache、procfs、nsfs 和 pidfs 的核心基础已经建立。当前仍只有 PID 0 执行 ``start_kernel()``。

``rest_init()`` 之前只剩最后一组同步初始化：

.. code-block:: c

   cpuset_init();
   mem_cgroup_init();
   cgroup_init();
   taskstats_init_early();
   delayacct_init();

   acpi_subsystem_init();
   arch_post_acpi_subsys_init();
   kcsan_init();

   rest_init();

本章追踪到 ``kcsan_init()`` 返回，停在 ``rest_init()`` 调用之前。到这里 ``start_kernel()`` 的单线启动阶段即将结束。

为什么 ``cgroup_init_early()`` 后还需要 ``cgroup_init()``
------------------------------------------------------

``start_kernel()`` 最早阶段已经调用过：

.. code-block:: c

   cgroup_init_early();

那一步发生在 page allocator、scheduler 和普通 slab 可用之前，只能建立最小关系：

* 让静态 ``init_task`` 拥有合法的初始 cgroup membership；
* 初始化早期可用的 subsystem state；
* 保证 scheduler/accounting 读取 current cgroup 时不会遇到空指针。

现在 allocator、VFS、PID、namespace 和 security 都已建立，才可以构造完整的 cgroup core。

``cpuset_init()`` 建立 CPU 与 memory-node 约束根
-------------------------------------------

cpuset controller 用 mask 表达任务允许使用的：

* CPU；
* NUMA memory node；
* scheduler load-balance domain；
* memory migration 和 spread policy。

``cpuset_init()`` 初始化顶层 ``top_cpuset``，使它覆盖系统允许的 CPU 与 memory node，并准备 controller 的锁、mask 和有效状态。

当前只有 CPU0 online，但 possible/present CPU 拓扑已经存在。顶层 cpuset 的语义不是“只准 CPU0 永远运行”，而是根 cpuset 起始时代表系统可用资源集合；AP online 和 hotplug 时还会继续更新 effective mask。

cpuset 与 scheduler affinity 的区别
---------------------------------

任务自身有 ``cpus_mask`` / ``cpus_ptr``，cpuset 又提供层级约束。最终允许集合概念上来自：

.. code-block:: text

   task affinity
   ∩ cpuset effective CPUs
   ∩ online/active CPUs
   ∩ isolation and scheduler constraints

当前 ``init_task`` 仍固定在 CPU0 的启动上下文中。初始化 cpuset 不会唤醒 AP，也不会立刻迁移 PID 0。

``mem_cgroup_init()`` 建立 memory cgroup 核心
----------------------------------------

Memory cgroup（memcg）对 cgroup 中的内存使用进行：

* page/folio charging；
* slab/kernel-memory accounting；
* reclaim；
* limit 与 protection；
* OOM isolation；
* per-node statistics；
* swap accounting（按配置）。

``mem_cgroup_init()`` 准备根 memory cgroup、per-node state、统计与回收所需数据，使后续分配路径可以把内存 charge 到相应 memcg。

这不会给系统自动设置一个很小的内存上限。root memcg 表示未被子 hierarchy 限制的顶层归属；具体 ``memory.max``、``memory.high`` 等值要等 cgroup filesystem 和用户空间配置。

为什么进程创建前必须有 memcg
--------------------------

第六十五章建立的多个 slab cache 带有 ``SLAB_ACCOUNT``。新任务创建时会分配：

* ``task_struct``；
* kernel stack；
* credential；
* signal/files/fs/mm objects；
* page tables 和匿名页。

这些分配需要在一开始就能找到正确的 memory cgroup。若先创建 PID 1，再补 memcg，启动过程中产生的对象会缺少一致归属。

``cgroup_init()`` 构造完整 cgroup core
----------------------------------

``cgroup_init()`` 将早期最小状态扩展为正式 cgroup infrastructure，主要包括：

* root cgroup 与 hierarchy 基础；
* subsystem/controller state；
* ``css_set`` 和 task membership 索引；
* controller dependency 与 enable 状态；
* kernfs/cgroup filesystem 所需关系；
* task fork/attach/exit hooks 的正式运行条件；
* release、migration 和 synchronization 基础。

不同 controller 会按照构建配置参与，例如 cpuset、cpu、memory、pids、io、freezer、hugetlb、rdma 等。没有固定 ``.config`` 时不能把全部 controller 都写成已启用。

cgroup core 已建立不等于 cgroupfs 已挂载
------------------------------------

当前内核已经能把任务关联到 root cgroup，并能在 ``copy_process()`` 中执行 cgroup fork hooks。

用户可见的层级还需要：

.. code-block:: text

   cgroup filesystem type available
   → mount cgroup2 or cgroup v1
   → create directories
   → enable controllers
   → write limits and task membership

这些动作通常由 initramfs、systemd 或其他 PID 1 用户空间完成。当前没有 ``/sys/fs/cgroup`` mount point。

``taskstats_init_early()`` 准备任务统计对象
--------------------------------------

Taskstats 向用户空间提供任务和 thread-group 的统计，例如：

* CPU runtime；
* context switches；
* I/O accounting；
* delay accounting；
* exit information。

``taskstats_init_early()`` 建立早期 cache、per-CPU 或 family 基础，使新任务从创建开始就能拥有一致的统计对象。

完整 Generic Netlink interface 和用户请求处理仍可能由后续 initcall 接通。当前没有用户程序订阅 taskstats。

``delayacct_init()`` 建立等待时间记账
--------------------------------

Delay accounting 记录任务因为资源不可用而等待的时间，例如：

* block I/O delay；
* swap-in delay；
* memory reclaim/compaction delay；
* CPU runnable delay；
* IRQ/SOFTIRQ interference（按配置与版本）。

``delayacct_init()`` 创建 delay-accounting cache，并为 ``init_task`` 准备基础状态。后面 ``copy_process()`` 才会给新任务分配或复制对应对象。

Delay accounting 与 scheduler runtime 不同
---------------------------------------

scheduler runtime 回答“任务实际在 CPU 上执行了多久”；delay accounting 回答“任务想继续执行，却因某类资源等待了多久”。

两者都依赖前面已经初始化的 sched clock，但采集点和语义不同。

``acpi_subsystem_init()`` 真正请求进入 ACPI mode
--------------------------------------------

第六十三章的 ``acpi_early_init()`` 已经：

* 重新安置 ACPI root table；
* 初始化 ACPICA subsystem；
* 准备 FADT/SCI 等早期事实；
* 让 ACPI tables 可访问。

它明确没有完成完整 event handling 和 device scan。

现在 ``acpi_subsystem_init()`` 调用 ACPICA 的 subsystem-enable 路径，请求平台进入 ACPI mode，并启用当前阶段安全的 ACPI hardware/event 基础。成功后，内核可以把 firmware power-management control 从传统兼容状态推进到 ACPI 管理模式。

ACPI subsystem enabled 不等于 ACPI bus scan 完成
---------------------------------------------

完整 ACPI interpreter object initialization、``_PIC``、device enumeration、driver binding 和通知 handler 仍在后面的 ``acpi_init()`` subsys initcall 中进行。

当前不能声称：

* 所有 AML method 已执行；
* EC driver 已完成 probe；
* ACPI device 已全部出现在 sysfs；
* PCI root bridge 已完成 Linux driver-model enumeration；
* sleep/wakeup device 已全部配置。

这一章只跨过“允许平台切到 ACPI mode”的边界。

``arch_post_acpi_subsys_init()`` 检查 AMD E400
------------------------------------------

在 x86 固定实现中，这个架构钩子主要处理 AMD E400/C1E erratum。

只有 boot CPU 已标记 ``X86_BUG_AMD_E400`` 时，函数才读取 ``MSR_K8_INT_PENDING_MSG``，检查 C1E active bits。受影响的平台会：

* 标记 ``X86_BUG_AMD_APIC_C1E``；
* 在缺少 nonstop TSC 时把 TSC 标记为 unstable；
* 按配置要求 tick broadcast；
* 启用对应 workaround。

为什么必须等 ACPI enable 后检查
-----------------------------

该 erratum 的状态与 firmware/ACPI power-management 行为有关。过早读取可能看不到平台进入 ACPI mode 后才出现的 C1E 状态，因此钩子被放在 ``acpi_subsystem_init()`` 之后。

普通非受影响 CPU 会立即返回。固定 QEMU q35 没有限定模拟 CPU model，正文不能提前断言该分支必定命中或跳过。

``kcsan_init()`` 准备并发数据竞争检测
---------------------------------

KCSAN（Kernel Concurrency Sanitizer）通过采样 watchpoint 检测未同步的并发内存访问。

启用 ``CONFIG_KCSAN`` 时，``kcsan_init()`` 建立运行时状态、watchpoint 和报告基础，使后续并发内核线程、interrupt 和 AP 执行时可以发现 data race。

未启用 KCSAN 时，该入口编译为空。即使启用，当前只有 CPU0 和 PID 0，真正高并发访问尚未开始；此处只是把检测器放到即将出现并发之前。

为什么 KCSAN 放在 ``rest_init()`` 前
--------------------------------

``rest_init()`` 会创建 PID 1 与 PID 2，随后第一次进入 scheduler，workqueue、kthread 和 AP bring-up 会逐步产生大量并发路径。

若 KCSAN 等到这些任务已经运行后才初始化，会漏掉最早一批共享状态访问。现在完成初始化，可以覆盖从第一次任务切换开始的并发执行。

``start_kernel()`` 的同步阶段已经准备了什么
---------------------------------------

从 PID 0 进入 ``start_kernel()`` 到当前，Linux 已经建立：

.. code-block:: text

   architecture and memory
   → buddy/slab/vmalloc
   → scheduler runqueue
   → workqueue/RCU/trace foundations
   → IRQ/IDT/timer/timekeeping
   → external interrupts enabled
   → console/ACPI early/x86 timer/boot CPU finalize
   → PID/fork/cred objects
   → namespaces/security/VFS/proc/pidfs
   → cpuset/memcg/cgroup/accounting
   → ACPI subsystem mode
   → concurrency sanitizer

现在内核不再只是“能够在 PID 0 中继续初始化”，而是已经具备创建和调度其他任务的通用对象基础。

仍然没有发生第一次正常任务切换
----------------------------

尽管 timer interrupt、scheduler、PID allocator 和 task caches 都已存在，当前控制流仍是：

.. code-block:: text

   CPU0
   → init_task / PID 0
   → start_kernel()
   → kcsan_init() returned

没有调用 ``schedule()``，没有 runnable PID 1，也没有 kthreadd。

``rest_init()`` 是下一个执行环境边界
---------------------------------

源码在调用前写着：

.. code-block:: c

   /* Do the rest non-__init'ed, we're now alive */
   rest_init();

``rest_init()`` 本身不是普通 ``__init`` 函数。原因是它会同时启动新的 root/init thread；后续 ``free_initmem()`` 可能释放 ``__init`` section，必须避免 PID 0 的返回路径仍依赖已被回收的启动代码。

下一阶段将按固定顺序：

.. code-block:: text

   rcu_scheduler_starting()
   → user_mode_thread(kernel_init)  创建 PID 1
   → 把 PID 1 暂时 pin 在 CPU0
   → kernel_thread(kthreadd)        创建 PID 2
   → system_state = SYSTEM_SCHEDULING
   → complete(kthreadd_done)
   → schedule_preempt_disabled()
   → PID 0 第一次进入 scheduler
   → cpu_startup_entry()

这些动作尚未发生，留给下一章。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 7.2-rc1 ``init/main.c:start_kernel()``；
* 精确位置：``kcsan_init()`` 已返回，``rest_init()`` 尚未调用；
* current：``init_task`` / ``swapper/0`` / PID 0；
* CPU：只有 CPU0 online；
* interrupts：CPU0 IF=1，timer interrupt 已具备正常投递条件；
* scheduler：runqueue 和 idle task 已建立，尚未进行第一次正常 schedule；
* cpuset：root cpuset 基础已建立；
* memcg：root memory cgroup 与 accounting 基础已建立；
* cgroup：core hierarchy、controller 和 task membership 基础已建立，cgroupfs 未断言已挂载；
* taskstats/delayacct：新任务统计基础已准备；
* ACPI：subsystem enable 已执行，完整 ACPI bus/device scan 尚未进行；
* x86 post-ACPI：AMD E400 检查已按 CPU capability 执行；
* KCSAN：按配置完成初始化；
* AP：尚未收到 INIT/SIPI；
* PID 1 / PID 2：尚未创建；
* initramfs：尚未解包；
* VFS root：尚未切入真实 root filesystem。

下一条控制流是：

.. code-block:: c

   rest_init();

这是 PID 0 第一次创建其他任务、启动 scheduler 运行环境并最终进入 idle loop 的入口。

资料
----

* `Linux 7.2-rc1 init/main.c：cgroup、ACPI、KCSAN 与 rest_init 边界 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 7.2-rc1 kernel/cgroup/cpuset.c：cpuset_init 与 root cpuset <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cgroup/cpuset.c>`_
* `Linux 7.2-rc1 mm/memcontrol.c：mem_cgroup_init 与 root memcg <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memcontrol.c>`_
* `Linux 7.2-rc1 kernel/cgroup/cgroup.c：cgroup_init 与 task membership <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cgroup/cgroup.c>`_
* `Linux 7.2-rc1 kernel/taskstats.c：taskstats_init_early <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/taskstats.c>`_
* `Linux 7.2-rc1 kernel/delayacct.c：delayacct_init 与 task delay accounting <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/delayacct.c>`_
* `Linux 7.2-rc1 drivers/acpi/bus.c：acpi_subsystem_init 与后续 acpi_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/acpi/bus.c>`_
* `Linux 7.2-rc1 arch/x86/kernel/process.c：arch_post_acpi_subsys_init 与 AMD E400 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/process.c>`_
* `Linux 7.2-rc1 kernel/kcsan/core.c：KCSAN runtime initialization <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/kcsan/core.c>`_