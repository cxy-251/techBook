第080章：Per-CPU 内存与可扩展分配模式
=====================================

本章必须记住
------------

#. Per-CPU 内存为每个 possible CPU 保存一份同类型数据，把高频共享写转换成高频本地写和低频聚合读。
#. Per-CPU 适合统计计数器、本地缓存、临时队列和每 CPU 快路径状态，不适合必须实时强一致的单一全局状态。
#. 多 CPU 写同一全局变量会造成锁竞争、原子 RMW 成本和 cache line bouncing。
#. 即使两个 CPU 更新不同字段，只要字段落在同一 cache line，也可能发生 false sharing。
#. Per-CPU 副本让各 CPU 主要写自己的 cache line，降低共享写入和一致性流量。
#. ``DEFINE_PER_CPU(type, name)`` 定义静态 per-CPU 变量，``DECLARE_PER_CPU`` 用于跨文件声明。
#. 静态 per-CPU 变量位于特殊 section，链接和启动阶段为每个 possible CPU 建立实例布局。
#. ``alloc_percpu(type)`` 或 ``__alloc_percpu()`` 动态分配每 CPU 副本，返回带 ``__percpu`` 语义的指针。
#. 动态 per-CPU 分配的内存开销大致随 possible CPU 数量增长，不只随 online CPU 数量增长。
#. 大型结构或过度对齐的 per-CPU 对象会显著放大内存占用，不能把普通大对象无条件复制到每个 CPU。
#. 动态 per-CPU 内存使用完成后由 ``free_percpu()`` 释放，不能交给 ``kfree()`` 或 ``vfree()``。
#. ``__percpu`` 指针不是普通可直接解引用的内核指针，必须先转换为当前 CPU 或指定 CPU 的真实地址。
#. ``this_cpu_ptr(p)`` 取得当前 CPU 的副本地址，``per_cpu_ptr(p, cpu)`` 取得指定 CPU 的副本地址。
#. 单个 ``this_cpu_inc()``、``this_cpu_add()`` 等操作表达“在执行该指令的当前 CPU 上更新本地副本”。
#. 单次 ``this_cpu_*`` 操作通常不要求调用者为了地址计算单独长期关闭抢占，但必须遵守该操作对中断和并发访问的具体规则。
#. ``this_cpu_ptr()`` 返回普通指针后，如果跨多个指令保存和使用，task 迁移可能使该指针不再对应新的当前 CPU。
#. 在进程上下文中长期使用当前 CPU 指针，应使用 ``get_cpu_ptr()``/``put_cpu_ptr()`` 或明确的 ``preempt_disable()``/``preempt_enable()`` 配对固定 CPU。
#. 关闭抢占只阻止 task 迁移，不能阻止同 CPU 的硬中断、softirq 或 NMI 访问同一副本。
#. 若同一 per-CPU 数据会被进程、IRQ、softirq 或 NMI 路径共同访问，还要使用适合该上下文的 local lock、IRQ 控制、原子操作或序列协议。
#. Per-CPU 消除了大部分跨 CPU 写竞争，不自动消除同 CPU 上下文嵌套和重入。
#. ``this_cpu_*``、``raw_cpu_*`` 和 ``__this_cpu_*`` 的抢占检查与原子保证不同，不能只按名字互换。
#. ``raw_cpu_*`` 允许操作当前 CPU 偏移而不要求常规抢占保护，常用于底层场景；调用者必须自行证明迁移和并发语义。
#. ``__this_cpu_*`` 通常假设调用者已建立必要的本 CPU 稳定性，错误使用可能在调试配置下告警或产生竞争。
#. 远程 CPU 读取通过 ``per_cpu()``、``per_cpu_ptr()`` 等接口完成，读取方必须接受目标 CPU 同时修改数据的可能。
#. 远程写 per-CPU 数据会破坏本地性，并可能和目标 CPU 的无锁本地更新竞争，应尽量避免。
#. 聚合所有 CPU 副本得到的是读取期间各时刻值的组合，不自动形成全局原子快照。
#. 只要统计允许轻微时间偏差，逐 CPU 聚合通常比每次热路径更新全局原子计数更可扩展。
#. 多字段统计必须防止读者看到字段之间的不一致组合，可使用 ``u64_stats_sync``、seqcount、锁或子系统专用同步。
#. 在 32 位架构上读取并发更新的 64 位计数可能发生 tearing，应使用合适的统计同步 helper。
#. ``percpu_counter`` 使用每 CPU 批量计数与全局基值组合，适合允许近似读取、偶尔要求精确汇总的计数场景。
#. Per-CPU 计数的近似值与精确值语义不同，API 调用者必须知道当前读取要求。
#. 遍历 ``for_each_possible_cpu`` 能覆盖所有已分配副本；``for_each_online_cpu`` 只覆盖当前在线 CPU。
#. 离线 CPU 的副本可能仍保存历史数据，统计是否包含它们取决于对象和 hotplug 语义。
#. CPU hotplug 会改变在线集合，遍历和初始化/销毁需要使用 CPU hotplug 锁或子系统提供的稳定机制。
#. 动态 per-CPU 对象创建后，必要时应为每个 possible CPU 显式初始化复杂字段。
#. CPU 上线回调负责建立在线期资源，CPU 下线回调负责排空队列、迁移状态或归并统计。
#. Per-CPU 队列在 CPU 下线前必须停止新入队并处理剩余对象，不能只释放 per-CPU 存储。
#. ``DEFINE_PER_CPU_SHARED_ALIGNED`` 等对齐变体可减少副本之间或字段之间的 false sharing，同时增加内存开销。
#. 对齐选择应依据真实访问模式和 cacheline 争用证据，不能无条件给所有变量 cacheline 对齐。
#. Per-CPU 数据的 NUMA 位置、first chunk 和动态 chunk 布局由 per-CPU allocator 管理，具体物理布局不应由调用者推断。
#. 调用者依赖的是“每 CPU 可寻址副本”语义，不是所有副本物理连续或彼此相邻。
#. Per-CPU 指针不能直接传给 DMA、用户空间或要求普通线性对象地址的接口。
#. 若需要把 per-CPU 状态导出到 procfs、debugfs 或 netlink，导出路径必须明确聚合、一致性和 CPU hotplug 规则。
#. 统计聚合本身可能很重，频繁读取所有 CPU 会把成本从写路径转移到读路径，仍需控制采样频率。
#. Per-CPU 缓存可减少全局分配锁竞争，但缓存过大可能导致内存滞留、不均衡和全局资源不足。
#. 本地批量积累到阈值后再归并全局，是常见可扩展模式；阈值决定局部性、精度和内存滞留的权衡。
#. 调试 per-CPU bug 时，应记录当前 CPU、抢占状态、IRQ/softirq/NMI 上下文、目标副本、CPU hotplug 和远程访问。
#. 数据竞争检测报告必须先判断访问的是同一 CPU 副本还是不同副本，地址相同概念不等于实际存储相同。
#. 正确的 per-CPU 设计必须同时定义本地更新规则、远程读取规则、聚合一致性和 CPU 上下线生命周期。

必背路径
--------

静态 per-CPU 统计：

::

   DEFINE_PER_CPU 定义每 CPU 副本
   → 热路径使用 this_cpu_* 更新当前 CPU
   → 避免全局共享写
   → 管理路径遍历目标 CPU 集合
   → 使用适当同步读取每个副本
   → 聚合为近似或精确结果
   → 明确 CPU hotplug 是否包含离线历史值

动态 per-CPU 对象：

::

   alloc_percpu 分配 __percpu 指针
   → 检查 NULL
   → 初始化每个 possible CPU 的复杂字段
   → 上线 CPU 启用本地资源
   → 运行路径通过 this_cpu_ptr / per_cpu_ptr 访问
   → 下线 CPU 排空队列并归并状态
   → 停止所有访问
   → free_percpu

安全使用当前 CPU 指针：

::

   进入进程上下文多步操作
   → get_cpu_ptr 或 preempt_disable 固定当前 CPU
   → 取得本 CPU 普通指针
   → 完成不允许迁移的连续访问
   → 处理同 CPU IRQ / softirq 并发规则
   → put_cpu_ptr 或 preempt_enable
   → 不在保护外保存该本地指针

一致聚合多字段统计：

::

   写者在本 CPU 更新字段组
   → 使用 u64_stats_sync / seqcount / local lock
   → 读者读取序列起点
   → 复制该 CPU 的全部字段
   → 检查序列是否变化
   → 变化时重试
   → 对所有 CPU 重复并聚合

CPU 下线：

::

   CPU hotplug 开始下线
   → 阻止该 CPU 新建本地工作
   → 排空 per-CPU 队列和缓存
   → 归并或迁移统计与对象
   → 注销 IRQ / timer / worker 关联
   → CPU 离线
   → 根据对象语义保留或清理该副本

必须区分
--------

* Per-CPU 副本与全局对象：前者每个 CPU 一份并需聚合；后者只有一份并要求共享同步。
* 单次 ``this_cpu_*`` 操作与长期本地指针：单次操作在执行 CPU 上完成；跨多步使用普通指针必须固定 CPU，防止 task 迁移。
* 关闭抢占与关闭中断：关闭抢占阻止 task 换 CPU；不能阻止同 CPU IRQ、softirq 或 NMI 重入。
* 近似聚合与一致快照：普通逐 CPU 求和可能混合不同时刻；一致字段组需要序列计数、锁或专用统计协议。
* Possible CPU 与 Online CPU：Possible 决定副本分配范围；online 表示当前可执行 CPU 集合，两者不相等。
* 本地更新与远程访问：本地写是 per-CPU 的主要性能收益；远程写会重新引入一致性和竞争问题。

一句话结论
----------

Per-CPU 内存用每 CPU 独立副本换取热路径本地更新，但必须显式处理 task 迁移、同 CPU 上下文并发、聚合一致性和 CPU hotplug 生命周期。
