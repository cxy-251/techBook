第六十七章：Linux 怎样建立控制组与记账基础，并到达 rest_init()？
====================================================================

第六十六章结束时，CPU0仍以 ``init_task``、 ``swapper/0``、PID 0的身份执行
``start_kernel()``。VFS对象缓存、初始挂载名字空间、可变 ``rootfs`` 和几个伪文件系统已经
建立，但系统仍只有一条启动执行流：没有动态PID，没有应用处理器，也没有普通工作线程。固定
源码中的下一组语句是：

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

本章跟踪前八个入口，到 ``kcsan_init()`` 返回为止。它们分别补上控制组根对象、早期任务记账、
ACPI模式切换和可选并发检查状态，却不创建任务，也不进入 ``rest_init()``。

``cpuset_init()`` 先建立顶层CPU与内存节点范围
------------------------------------------------

启用 ``CONFIG_CPUSETS`` 时， ``cpuset_init()`` 为 ``top_cpuset`` 分配允许CPU、有效CPU、
独占CPU等掩码，同时建立子分区和隔离CPU掩码。这些分配使用普通内核分配标志，但每次结果都由
``BUG_ON()`` 检查；只要关键掩码分配失败，当前启动路径就不会继续执行。

对象齐备后，函数把顶层允许、有效和独占CPU掩码设为全部可能CPU，把允许和有效内存节点掩码
设为全集，再调用 ``cpuset1_init()`` 完成顶层对象的第一阶段设置。若启动参数已经启用
``HK_TYPE_DOMAIN_BOOT`` 维护CPU隔离，它还用 ``cpu_possible_mask`` 减去维护CPU，得到启动期
隔离CPU集合。

这里建立的是控制组视角的根约束，不是SMP调度域。 ``cpuset_init_smp()`` 要等应用处理器和CPU
拓扑确定后才会运行，因此当前CPU0的运行队列和亲和关系没有因本入口重新组织。禁用
``CONFIG_CPUSETS`` 时，同名内联入口直接返回0，上述对象也不会建立。

``mem_cgroup_init()`` 准备内存控制器的共享设施
----------------------------------------------

启用 ``CONFIG_MEMCG`` 时， ``mem_cgroup_init()`` 首先登记CPU离线回调
``memcg_hotplug_cpu_dead``，再分配逐CPU ``memcg`` 工作队列。工作队列分配失败只触发
``WARN_ON()``，源码没有在这里补建替代对象；这与随后缓存分配的失败语义不同，不能概括成一个
统一的“初始化成功”状态。

函数随后为每个可能CPU初始化两项工作： ``memcg_stock.work`` 用于排空本地内存控制组库存，
``obj_stock.work`` 用于排空本地对象库存。最后，它按当前 ``nr_node_ids`` 计算
``struct mem_cgroup`` 的变长大小，并创建 ``mem_cgroup`` 与
``mem_cgroup_per_node`` 两个缓存。两个缓存都带有 ``SLAB_PANIC``，关键分配失败会停止启动。

此时只有内存控制器共享设施， ``root_mem_cgroup`` 还没有在这个函数中完成。源码特意把根内存
控制组留给紧接着的 ``cgroup_init()``，因为它依赖具体控制组根和控制器状态。禁用
``CONFIG_MEMCG`` 时，入口为空。

``cgroup_init()`` 把初始任务接入默认控制组根
---------------------------------------------

启用 ``CONFIG_CGROUPS`` 时， ``cgroup_init()`` 先建立控制组核心文件类型和资源统计状态，并为
初始控制组名字空间取得用户名字空间引用。持有 ``cgroup_lock`` 期间，它把静态
``init_css_set`` 放入散列表，建立BPF生命周期通知，再通过 ``cgroup_setup_root()`` 构造默认
层级 ``cgrp_dfl_root``。

随后，函数遍历编入内核的每个 ``cgroup_subsys``。已经在早期入口初始化的控制器获得正式ID；
其他控制器此时才执行 ``cgroup_init_subsys()``。对启用的控制器，函数计算默认层级掩码和
线程化属性，登记各自文件项，调用可选 ``bind`` 回调，并把控制器目录内容接到初始控制组。
``init_css_set.subsys[]`` 发生变化后，散列表键也随之重新计算。

核心对象连接完成后，函数尝试创建 ``/sys/fs/cgroup`` 挂载点对象，登记控制组v1、控制组v2和
可选的旧式CPU集合文件系统，并按条件建立 ``/proc/cgroups``。这些外围操作使用 ``WARN_ON()``
记录失败，却不把错误传播回 ``start_kernel()``；最后，初始控制组名字空间加入名字空间树。

这里的结果是“文件系统类型已经登记、默认根和初始成员关系已经建立”，不是“控制组文件系统
已经挂载”。控制组自己的销毁工作队列也由稍后的初始化调用建立。禁用
``CONFIG_CGROUPS`` 时，同名入口不构造这些对象。

任务统计先有缓存和监听表，稍后才有通信接口
------------------------------------------

启用 ``CONFIG_TASKSTATS`` 时， ``taskstats_init_early()`` 创建 ``taskstats`` 对象缓存。该
缓存使用 ``SLAB_PANIC``，然后函数为每个可能CPU初始化 ``listener_array`` 的链表和读写信号
量。这样，后续任务退出和控制组统计路径已有保存对象及逐CPU监听容器。

本入口没有调用 ``genl_register_family()``。Generic Netlink族由稍后的
``taskstats_init()`` 登记，所以当前不能从“早期对象存在”推导出用户空间已经能够请求任务
统计。禁用 ``CONFIG_TASKSTATS`` 时，该入口为空。

延迟记账是否启用由构建和启动参数共同决定
----------------------------------------

启用 ``CONFIG_TASK_DELAY_ACCT`` 时， ``delayacct_init()`` 创建
``task_delay_info`` 缓存，然后调用 ``delayacct_tsk_init(&init_task)``。该辅助函数先把
``init_task.delays`` 清空；只有 ``delayacct_on`` 已经为真时，才为PID 0分配具体延迟记账
对象。

``delayacct_on`` 可以由 ``delayacct`` 启动参数预先置位。函数最后用该值设置
``delayacct_key`` 静态键。因此，本入口保证缓存和开关状态一致，却不保证延迟采集一定打开；
没有相应构建选项时，它完全为空。

ACPI入口此时只尝试切换固件模式
------------------------------

若ACPI已经被禁用， ``acpi_subsystem_init()`` 立即结束。否则，它调用：

.. code-block:: c

   acpi_enable_subsystem(~ACPI_NO_ACPI_ENABLE);

这一位掩码保留“允许进入ACPI模式”，同时设置其他 ``ACPI_NO_*`` 位。因此，ACPICA在这里跳过
FACS映射、固定事件和GPE初始化，也跳过SCI与全局锁处理器安装；这些工作要等后续ACPI总线入口
再次调用 ``acpi_enable_subsystem()``。本章不能把ACPI模式切换写成ACPI事件系统已经可用。

模式切换失败时，内核打印错误并调用 ``disable_acpi()``，随后仍沿启动链继续。成功时，
``regulator_has_full_constraints()`` 告诉稳压器核心：使用ACPI的系统可认为固件已经描述
了所需约束。固定平台采用SeaBIOS，但最终ACPI表内容、启动参数和失败结果仍由实际配置控制，
不能预先断言这个分支必定成功。

x86只在确认AMD E400后发布对应修正
---------------------------------

``arch_post_acpi_subsys_init()`` 是体系结构在ACPI模式切换后的修正入口。固定x86实现先检查启动
CPU是否带有 ``X86_BUG_AMD_E400``；没有该标记便立即结束。有该标记时，它读取
``MSR_K8_INT_PENDING_MSG``，还要看到 ``K8_INTP_C1E_ACTIVE_MASK`` 才设置
``X86_BUG_AMD_APIC_C1E``。

确认修正条件后，缺少 ``X86_FEATURE_NONSTOP_TSC`` 的CPU会把TSC标记为不稳定；启用通用空闲
时钟事件广播时，内核还打开 ``arch_needs_tick_broadcast`` 静态分支。这个入口不会为普通CPU
统一重配时钟，也不能用固定QEMU平台名称推导所模拟CPU一定具有或不具有该问题。

KCSAN在任务并发出现前完成可选启用
---------------------------------

启用 ``CONFIG_KCSAN`` 时， ``kcsan_init()`` 先用 ``BUG_ON(!in_task())`` 确认当前仍在任务
上下文，然后以 ``get_cycles()`` 为每个可能CPU的 ``kcsan_rand_state`` 播种。当前仍只有PID 0
运行，因此写入这些逐CPU状态时不需要与其他任务竞争。

只有 ``kcsan_early_enable`` 为真时，函数才把 ``kcsan_enabled`` 置为真。随后日志说明当前
构建采用严格或非严格检测方式。该入口没有在这里创建报告线程，也没有改变控制流的任务数量；
禁用 ``CONFIG_KCSAN`` 时，它为空。

本章结束状态
------------

::

   当前执行者          = CPU0上的start_kernel()；kcsan_init()已返回
   下一入口            = rest_init()
   CPU模式             = x86-64长模式，CPL0
   IF                  = 1
   当前任务            = init_task / swapper/0 / PID 0
   system_state        = SYSTEM_BOOTING
   CPU在线且活动       = 仅CPU0
   应用处理器          = 尚未启动
   动态PID             = 尚未分配
   cpuset根            = 按CONFIG_CPUSETS建立或采用空入口
   内存控制组基础      = 按CONFIG_MEMCG建立共享设施；根状态由cgroup核心连接
   控制组核心          = 按CONFIG_CGROUPS建立默认根、初始成员关系与文件系统登记
   cgroupfs            = 尚未挂载
   taskstats           = 早期缓存与监听表按配置建立；Generic Netlink族尚未登记
   延迟记账            = 按构建和delayacct启动参数建立或关闭
   ACPI                = 未禁用时只尝试切换模式；事件与SCI处理器尚未在本入口建立
   KCSAN               = 按构建和早期启用选择播种并打开，或采用空入口
   普通工作线程        = 尚未开始执行
   PID1/PID2           = 尚未创建
   初始根              = 仍为可变rootfs；最终ext4磁盘根尚未挂载

关键边界
--------

* ``cpuset_init()`` 建立顶层约束掩码，不建立SMP调度域；
* ``mem_cgroup_init()`` 建立共享设施，根内存控制组由随后 ``cgroup_init()`` 连接；
* ``cgroup_init()`` 登记文件系统并建立默认根，不等于控制组文件系统已经挂载；
* ``taskstats_init_early()`` 没有登记Generic Netlink族， ``delayacct_init()`` 也不保证采集已
  启用；
* ``acpi_subsystem_init()`` 本次只允许切换ACPI模式，FACS、事件、SCI与全局锁处理器仍留给
  后续入口；
* ``arch_post_acpi_subsys_init()`` 和 ``kcsan_init()`` 都受CPU能力、构建或启动选择控制；
* 本章没有创建任务、启动应用处理器或发生任务切换。

下一入口
--------

下一章进入 ``rest_init()``。PID 0将先推进RCU启动阶段，再依次创建PID 1和PID 2，发布
``kthreadd_done``，执行第一次显式调度并永久转入CPU0空闲循环。

资料
----

* `start_kernel()的本章调用区间
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/init/main.c#L1164-L1175>`_
* `cpuset_init()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cgroup/cpuset.c#L3687-L3712>`_
* `mem_cgroup_init()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/mm/memcontrol.c#L5529-L5570>`_
* `cgroup_init()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/cgroup/cgroup.c#L6417-L6522>`_
* `taskstats早期对象与稍后的通信族登记
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/taskstats.c#L693-L711>`_
* `delayacct_init()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/delayacct.c#L28-L55>`_
* `delayacct_tsk_init()按开关分配任务状态
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/include/linux/delayacct.h#L111-L117>`_
* `ACPI模式切换入口
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/acpi/bus.c#L1435-L1462>`_
* `ACPICA对FACS、模式、事件和处理器的分阶段执行
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/drivers/acpi/acpica/utxfinit.c#L110-L192>`_
* `x86的ACPI后修正
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/arch/x86/kernel/process.c#L971-L995>`_
* `kcsan_init()
  <https://github.com/gregkh/linux/blob/7404ce51637231382873d0b55edabc2f3b841a9d/kernel/kcsan/core.c#L794-L820>`_
