第五十三章：Linux 为什么再次确认 CPU NUMA node，并把 CPU0 放入 hotplug ONLINE 状态？
====================================================================================

第五十二章结束时，CPU0 已经切换到正式的 per-CPU unit，其他 possible CPU 也已经拥有各自的 unit 和 offset。

``start_kernel()`` 接下来执行：

.. code-block:: c

   early_numa_node_init();
   boot_cpu_hotplug_init();

本章追踪到 ``boot_cpu_hotplug_init()`` 返回。

这两步都不会启动 AP。它们解决的是另一类问题：现在正式 per-CPU 存储已经可用，通用 NUMA 查询和 CPU hotplug 状态机必须能够把正在执行启动代码的 CPU0 视为一个状态完整的 online CPU。

为什么 per-CPU area 建立后还要处理 NUMA node
--------------------------------------------

前面的 ACPI SRAT、MADT 和 x86 topology 代码已经得到 CPU 到 NUMA node 的对应关系。

在正式 per-CPU area 出现前，这些关系只能暂存在 early arrays 或架构私有映射中。第五十二章的 x86 ``setup_per_cpu_areas()`` 已把 ``x86_cpu_to_node_map`` 等早期数据复制到正式 per-CPU unit，并调用：

.. code-block:: c

   set_cpu_numa_node(cpu, early_cpu_to_node(cpu));

因此，在固定 x86-64 路径上，CPU-to-node 数据实际上已经写入正式 per-CPU 区域。

``early_numa_node_init()`` 仍然存在，因为 ``start_kernel()`` 是跨架构的通用入口。不同架构建立 per-CPU area 和 NUMA 映射的顺序并不完全相同，通用代码需要一个明确的位置，保证后续代码可以通过正式接口取得当前 CPU 的 node。

``early_numa_node_init()`` 的条件路径
-----------------------------------

函数实现为：

.. code-block:: c

   static void __init early_numa_node_init(void)
   {
   #ifdef CONFIG_USE_PERCPU_NUMA_NODE_ID
   #ifndef cpu_to_node
       int cpu;

       for_each_possible_cpu(cpu)
           set_cpu_numa_node(cpu, early_cpu_to_node(cpu));
   #endif
   #endif
   }

只有同时满足以下条件时，循环才会编译进内核：

* 配置启用了 ``CONFIG_USE_PERCPU_NUMA_NODE_ID``；
* 架构没有自行提供 ``cpu_to_node`` 实现。

循环遍历的是 ``possible`` CPU，而不是 ``online`` CPU。

原因是 NUMA node 是未来启动 AP 时也必须立即可用的基础属性。即使 CPU1 尚未运行，它的 per-CPU unit 中也应当提前保存 CPU1 属于哪个 node。

为什么这里可能只是重复写入
------------------------

固定 x86-64 路径在 ``setup_per_cpu_areas()`` 中已经完成相同方向的迁移。

所以 ``early_numa_node_init()`` 在本路径上可能表现为：

* 条件编译后成为空函数；或者
* 再次把相同的 early CPU-to-node 结果写入正式 per-CPU 变量。

这不是重新解析 SRAT，也不是重新建立 NUMA topology。

它是通用启动序列中的一致性检查点：从这里以后，通用代码不应再依赖尚未迁移的早期 node 表。

CPU0 早已 online，为什么还需要 hotplug 初始化
--------------------------------------------

``start_kernel()`` 很早以前已经调用过：

.. code-block:: c

   boot_cpu_init();

它把当前 CPU 设置进：

.. code-block:: text

   cpu_possible_mask
   cpu_present_mask
   cpu_online_mask
   cpu_active_mask

因此 CPU0 早已被全局 CPU mask 视为 possible、present、online 和 active。

然而 CPU hotplug 子系统还有自己的 per-CPU 状态：

.. code-block:: c

   struct cpuhp_cpu_state {
       enum cpuhp_state state;
       enum cpuhp_state target;
       ...
       atomic_t ap_sync_state;
       ...
   };

这些字段位于正式 per-CPU area 中。此前正式 area 尚未建立，不能在 ``boot_cpu_init()`` 时完成这里的初始化。

这形成了两个不同层次：

``CPU masks``
   描述 CPU 是否 possible、present、online、active。

``CPU hotplug state``
   描述 CPU 在 hotplug 状态机中已经走到哪个阶段、目标阶段是什么，以及 BSP/AP 同步握手处于什么状态。

``boot_cpu_hotplug_init()`` 的前置条件
------------------------------------

源码在函数前明确写着：

.. code-block:: c

   /* Must be called _AFTER_ setting up the per_cpu areas */

这是因为函数使用：

.. code-block:: c

   this_cpu_write(...)
   this_cpu_ptr(...)

这些操作必须落到 CPU0 的正式 per-CPU unit。

若在 ``setup_per_cpu_areas()`` 之前调用，它可能写入 early template、临时 base，或者根本无法满足后续 hotplug 代码对正式 per-CPU 地址的假设。

CPU0 被记为已经启动过
------------------

在 SMP 构建中，函数先执行：

.. code-block:: c

   cpumask_set_cpu(smp_processor_id(), &cpus_booted_once_mask);

``cpus_booted_once_mask`` 记录哪些逻辑 CPU 至少成功启动过一次。

这个集合不等同于 ``cpu_online_mask``：

* online 表示此刻正在运行；
* booted once 表示历史上至少完成过一次低级启动。

这种区分对 SMT 控制和 CPU hotplug 很重要。

x86 可能要求某些 SMT sibling 至少启动一次，以便每个逻辑 CPU 完成必要的 CR4、MCE 和架构状态初始化。之后即使策略不允许它保持 online，内核也知道它已经走过最低限度的启动路径。

CPU0 从机器复位后一直运行，当然已经满足“启动过一次”，所以这里把它加入该 mask。

BSP/AP 同步状态直接设为 ONLINE
-----------------------------

若启用了完整 hotplug 同步，函数执行：

.. code-block:: c

   atomic_set(this_cpu_ptr(&cpuhp_state.ap_sync_state),
              SYNC_STATE_ONLINE);

普通 AP 后续启动时会经历类似状态：

.. code-block:: text

   DEAD
   → KICKED
   → ALIVE
   → SHOULD_ONLINE
   → ONLINE

这些状态用于协调：

* BSP 已经发送启动请求；
* AP 已进入低级启动代码；
* BSP 是否允许 AP 继续；
* AP 是否最终到达 online idle 状态。

CPU0 不需要走 INIT/SIPI，也没有另一个控制 CPU 等待它报告 ``ALIVE``。它本来就是启动执行者，因此直接把同步状态设为 ``SYNC_STATE_ONLINE``。

hotplug ``state`` 与 ``target`` 都设为 ONLINE
------------------------------------------

函数最后执行：

.. code-block:: c

   this_cpu_write(cpuhp_state.state, CPUHP_ONLINE);
   this_cpu_write(cpuhp_state.target, CPUHP_ONLINE);

``state`` 表示 CPU0 当前已经到达的 hotplug 状态。

``target`` 表示当前操作希望它最终到达的状态。

两者都为 ``CPUHP_ONLINE`` 表示：

.. code-block:: text

   CPU0 当前状态：ONLINE
   CPU0 目标状态：ONLINE
   没有正在进行的 bring-up 或 teardown

这里不会从 ``CPUHP_OFFLINE`` 开始逐级调用所有 startup callback。

原因是 CPU0 在 hotplug 状态机完整运行前就已经承担了启动工作。许多早期子系统会在后面的 ``start_kernel()`` 中直接初始化，而不是通过“把 CPU0 从 offline 热插拔上线”的方式初始化。

``boot_cpu_hotplug_init()`` 只把状态机账本补到与现实一致的位置。

为什么不能把它理解为启动 CPU0
---------------------------

CPU0 从进入 Linux 入口开始就一直在执行当前调用栈。

此处没有：

.. code-block:: text

   INIT IPI
   SIPI
   AP trampoline
   start_secondary()
   cpu_up()
   cpuhp_up_callbacks()

所以这不是“启动 CPU0”，也不是“启动其他 CPU”。

它是在正式 per-CPU area 建立后，把已经运行的 CPU0 登记为 hotplug 状态机中的完成态。

此时 CPU hotplug thread 仍未建立
-----------------------------

``cpuhp_threads_init()`` 要到后面的 ``smp_init()`` 路径中才会注册 per-CPU hotplug thread。

当前：

* CPU0 的 ``state`` 和 ``target`` 已为 ``CPUHP_ONLINE``；
* AP 的 per-CPU hotplug storage 已存在，但它们尚未启动；
* completion、hotplug thread 和各子系统 callback 还会在后续阶段继续准备。

因此这里建立的是初始状态，不是完整运行时 hotplug 基础设施。

当前机器状态
------------

本章结束时：

* 当前执行者：Linux 6.12.95 ``init/main.c:start_kernel()``；
* 精确位置：``boot_cpu_hotplug_init()`` 已返回，``print_kernel_cmdline()`` 尚未调用；
* CPU：只有 BSP / Linux CPU0 online；
* mode：64 位 long mode；
* current task：``init_task``；
* interrupts：关闭，``early_boot_irqs_disabled = true``；
* per-CPU area：正式 first chunk 已建立；
* CPU-to-node：后续代码可通过正式 per-CPU NUMA 接口读取；
* CPU0 hotplug state：``state = target = CPUHP_ONLINE``；
* CPU0 AP sync state：在相应配置下为 ``SYNC_STATE_ONLINE``；
* ``cpus_booted_once_mask``：已包含 CPU0；
* AP：尚未收到 INIT/SIPI；
* hotplug threads：尚未建立；
* 正式命令行：已保存，尚未打印和通用解析；
* buddy：尚未接收全部可分配 RAM；
* slab、scheduler：尚未初始化；
* initramfs：尚未解包。

下一条控制流是：

.. code-block:: c

   print_kernel_cmdline(saved_command_line);

资料
----

* `Linux 6.12.95 init/main.c：early NUMA、boot CPU hotplug 与命令行调用顺序 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c>`_
* `Linux 6.12.95 kernel/cpu.c：boot_cpu_init 与 boot_cpu_hotplug_init <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cpu.c>`_
* `Linux 6.12.95 include/linux/cpuhotplug.h：CPU hotplug 状态空间 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/cpuhotplug.h>`_
* `Linux 6.12.95 include/linux/topology.h：per-CPU NUMA node 接口 <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/topology.h>`_