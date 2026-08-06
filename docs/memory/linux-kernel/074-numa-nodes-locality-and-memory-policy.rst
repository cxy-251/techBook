第074章：NUMA 节点、局部性与内存策略
====================================

本章必须记住
------------

#. NUMA 表示 CPU 访问不同物理内存节点的延迟和带宽并不均匀。
#. CPU 访问本地 node 内存通常成本较低，访问远端 node 需要经过互连，延迟和带宽竞争更明显。
#. NUMA node 是拓扑和物理内存管理对象，不应简单等同于 CPU 插槽编号。
#. 系统可能存在 memory-only node、无内存 CPU node、热插拔内存或具有特殊性能属性的设备内存节点。
#. 每个内存 node 通常由 ``pg_data_t`` 或 ``pgdat`` 描述，并包含若干 zone、PFN 范围、回收和统计状态。
#. Node 表示距离与容量，zone 表示硬件寻址和迁移约束；一次分配会同时受到两者限制。
#. NUMA 问题必须同时记录四个位置：线程在哪个 CPU、CPU 属于哪个 node、页面位于哪个 node、允许使用哪些 node。
#. 线程迁移不会自动搬迁已有物理页；同一虚拟地址在任务迁移后可能从本地访问变成远端访问。
#. 页面迁移不会改变用户虚拟地址，内核更新页表和反向映射后，物理页可以移动到另一 node。
#. 默认匿名页分配常遵循 first-touch：哪一个 CPU 首次触发缺页，页面倾向分配到该 CPU 的本地 node。
#. ``malloc`` 或 ``mmap`` 只建立虚拟范围时不决定全部物理页位置，真正首次触页的线程位置非常重要。
#. 单线程在 node 0 初始化大块内存，随后多线程分散到其它 node，容易形成大量远端访问。
#. 默认本地分配只是偏好，不是成功保证；本地 node 在 zone、水位或碎片约束下不足时可以回退到远端允许 node。
#. 远端 fallback 提高可用性，但可能增加访问延迟、互连流量和尾延迟波动。
#. ``cpu_to_node()``、``numa_node_id()`` 一类接口说明执行 CPU 的 node；``page_to_nid()`` 或 folio helper 说明页面所在 node。
#. 内存策略把用户或内核放置意图转换成页分配时的候选节点规则。
#. ``MPOL_DEFAULT`` 使用默认局部策略和系统 zonelist，结果仍受 cpuset 和运行 CPU 影响。
#. ``MPOL_PREFERRED`` 优先指定 node，受压时通常允许在其它允许节点中 fallback。
#. ``MPOL_BIND`` 把候选范围限制在指定 nodemask 内，提高放置确定性，也增加局部容量不足时的失败风险。
#. ``MPOL_INTERLEAVE`` 在允许节点间按页分散分配，常用于提高聚合带宽和避免单 node 容量热点。
#. ``MPOL_PREFERRED_MANY`` 表示一组优先节点，具体可用性依赖目标内核版本。
#. Weighted interleave 等新策略具有版本边界，部署和工具必须与目标内核能力一致。
#. 策略可以作用于 task、VMA 或共享内存对象，读取策略时必须确认作用范围。
#. ``mbind()`` 主要设置指定虚拟范围的内存策略；已有页面是否迁移取决于 flags、权限和页面可迁移性。
#. ``set_mempolicy()`` 影响调用线程后续分配的策略，不等于立即重新放置全部既有页面。
#. ``get_mempolicy()`` 用于读取策略或地址相关节点信息，返回语义受 flags 影响。
#. Cpuset 的 ``mems`` 限制 task 可以从哪些内存 node 分配，是内存策略外面的硬允许集合。
#. 实际候选节点通常是 mempolicy nodemask 与 cpuset allowed mems 的交集。
#. CPU affinity 与 memory policy 必须共同设计；只绑 CPU 不绑内存，或只绑内存不绑 CPU，都可能形成远端访问。
#. Cgroup/cpuset 配置变化可能重建允许节点集合，并改变后续分配和页面迁移行为。
#. 自动 NUMA balancing 通过采样访问、NUMA hinting fault 和迁移决策，尝试让热页靠近访问 CPU 或让任务靠近页面。
#. Hinting fault 是内核主动建立的观察机制，不表示页面内容丢失或普通非法访问。
#. 自动 balancing 的目标是改善长期局部性，它会增加 fault、扫描、迁移和页表更新开销。
#. 页面被多个 node 上线程共同访问时，没有唯一完美位置；迁移可能在读者之间来回摆动或选择折中位置。
#. 共享页、文件页、THP、长期 pin 页面、设备映射和不可迁移页会限制自动迁移效果。
#. 透明大页迁移成本高于普通页，NUMA 策略和 THP 可能共同影响延迟与带宽。
#. 任务迁移和页面迁移属于不同控制路径；调度器优化 CPU 放置，内存管理优化页放置。
#. ``/sys/devices/system/node/`` 展示 node、CPU 列表、内存信息和部分距离矩阵。
#. ``/proc/<pid>/numa_maps`` 按映射展示已驻留页面在各 node 的分布和策略，是进程页位置证据。
#. ``numastat`` 和 ``/proc/vmstat`` 的 numa_hit、numa_miss、numa_foreign、local_node、other_node 等指标提供分配结果线索。
#. NUMA 统计含义和字段会随版本变化，必须以目标内核文档为准。
#. ``numactl --hardware`` 展示用户态看到的拓扑；``numactl --show`` 展示当前策略与绑定，不证明既有页实际位置。
#. 诊断远端访问不能只看 CPU 使用率，应同时比较线程 CPU、numa_maps、node bandwidth、迁移和 fault 事件。
#. 本地 node 空闲不足、cpuset 限制过窄、错误 first-touch 和线程频繁跨 node 迁移都可能造成 NUMA 性能问题。
#. NUMA 调优必须用相同负载比较吞吐、P99 延迟、远端访问比例、迁移开销和 node 内存压力。
#. 一次策略修改可能改善局部性，也可能造成单 node 容量热点、回收压力或负载不均。
#. 内存位置是性能属性，不是程序正确性的唯一条件；远端页仍然有效，只是访问代价不同。

必背路径
--------

默认 first-touch 分配：

::

   用户建立匿名虚拟映射
   → 某线程在 CPU X 首次访问页面
   → CPU X 所属 node 成为默认优先节点
   → mempolicy 与 cpuset 限定候选节点
   → page allocator 检查本地 zone 和水位
   → 本地成功或向远端允许节点 fallback
   → 页表映射到得到的物理页

分析远端内存：

::

   确认线程当前 CPU 与 affinity
   → 确认 CPU 所属 NUMA node
   → 读取 task 的 mems_allowed 和 mempolicy
   → 用 numa_maps 查看页面 node 分布
   → 判断 first-touch、fallback、任务迁移或页迁移历史
   → 对照远端访问与业务延迟

自动 NUMA balancing：

::

   内核选择地址范围进行采样
   → 建立 NUMA hinting fault 观察访问
   → 记录访问 CPU 与页面 node
   → 判断迁移 task 还是迁移页面
   → 可迁移时更新物理页和页表
   → 后续访问重新评估局部性

策略与约束合成：

::

   task / VMA / shared object 提供 mempolicy
   → 策略给出 preferred 或 nodemask
   → cpuset mems_allowed 做硬限制
   → 当前 CPU 和 node distance 决定遍历偏好
   → zonelist、zone 和 watermarks 再判断可分配性
   → 返回本地页、远端页或失败

必须区分
--------

* CPU 位置与页面位置：Task 在哪个 node 的 CPU 上运行，不代表它访问的页面位于同一 node。
* Task 迁移与页面迁移：Task 迁移改变执行位置；页面迁移改变物理页位置，二者互不自动等价。
* 策略偏好与硬限制：Preferred 可以允许 fallback；bind 和 cpuset 会更严格限制候选节点集合。
* 拓扑与 Zone：Node 描述距离；zone 描述地址能力和迁移约束。
* 未来分配策略与既有页面位置：修改策略主要影响后续分配；既有页是否迁移需要单独动作和可迁移条件。
* 本地访问与正确访问：远端内存仍可正确访问，问题主要是延迟、带宽和互连竞争。

一句话结论
----------

NUMA 性能由线程位置和页面位置的组合决定；可靠调优必须同时控制 CPU affinity、first-touch、内存策略、cpuset 与页面迁移。
