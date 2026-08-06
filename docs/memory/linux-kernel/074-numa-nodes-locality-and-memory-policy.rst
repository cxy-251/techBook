第074章：NUMA 节点、局部性与内存策略
====================================

核心知识点
----------

NUMA 使内存访问成本依赖位置
   CPU 访问本地 node 内存通常延迟更低、带宽更稳定；访问远端 node 需要经过互连，成本和竞争更高。

Node 是拓扑对象，不等于插槽编号
   一个 node 可以包含 CPU 和内存，也可能是 memory-only node、无内存 CPU node 或特殊设备内存节点。

页面位置与线程位置必须同时观察
   NUMA 分析至少要记录线程在哪个 CPU、CPU 属于哪个 node、页面位于哪个 node，以及任务允许使用哪些 node。

任务迁移不会自动迁移页面
   调度器把线程移到另一 node 后，已有页面仍留在原位置，同一虚拟地址可能从本地访问变为远端访问。

页面迁移不会改变虚拟地址
   内核可以复制页面到另一 node，更新反向映射和页表后继续使用原虚拟地址。

First-touch 决定默认匿名页位置
   ``malloc`` 或 ``mmap`` 通常只建立虚拟范围，首次触发缺页的 CPU 所属 node 常成为匿名页的优先分配位置。

本地分配是偏好，不是保证
   本地 node 受 zone、水位、碎片和允许节点约束。无法满足时，默认策略可以向远端 node fallback。

内存策略定义候选节点规则
   ``MPOL_DEFAULT`` 使用默认局部策略；``MPOL_PREFERRED`` 优先某个节点；``MPOL_BIND`` 严格限制候选集合；``MPOL_INTERLEAVE`` 在多个节点间分散页面。

策略有作用范围
   策略可以属于线程、VMA 或共享内存对象。修改策略主要影响后续分配，既有页面是否迁移取决于 flags、权限和页面可迁移性。

Cpuset 是外层硬约束
   Cpuset 的 ``mems`` 限定任务可从哪些 node 分配。实际候选集合通常是内存策略与 cpuset allowed mems 的交集。

CPU affinity 与内存策略必须联合设计
   只绑定 CPU 不控制页面，或只绑定页面不控制线程，都可能长期形成远端访问。

自动 NUMA balancing 根据访问模式修正位置
   内核通过 hinting fault 采样页面访问，再选择迁移 task 或迁移页面。它改善长期局部性，也会增加 fault、扫描、迁移和页表更新成本。

共享页面不存在唯一最佳位置
   多个 node 上的线程共同访问同一页面时，迁移可能只在不同读者之间转移成本，需要在带宽、延迟和迁移开销之间取舍。

关键路径
--------

默认 first-touch 分配：

::

   用户建立匿名虚拟映射
   → 某线程在 CPU X 首次访问页面
   → CPU X 所属 node 成为默认优先节点
   → mempolicy 与 cpuset 限定候选节点
   → page allocator 检查本地 zone 与水位
   → 本地成功或向允许的远端 node fallback
   → 建立页表映射

分析远端访问：

::

   确认目标线程的 CPU 与 affinity
   → 确认 CPU 所属 NUMA node
   → 读取 mempolicy 与 mems_allowed
   → 用 numa_maps 查看页面 node 分布
   → 判断 first-touch、fallback、任务迁移或页面迁移
   → 对照远端访问比例与业务延迟

自动 NUMA balancing：

::

   内核选择地址范围采样
   → 建立 NUMA hinting fault
   → 记录访问 CPU 与页面 node
   → 评估迁移 task 或迁移页面
   → 可迁移时复制页面并更新页表
   → 后续访问重新评估局部性

策略与约束合成：

::

   task、VMA 或共享对象提供 mempolicy
   → 策略给出 preferred node 或 nodemask
   → cpuset mems_allowed 做硬限制
   → 当前 CPU 与 node distance 决定遍历偏好
   → zone、watermark 与 buddy 判断可分配性
   → 返回本地页、远端页或失败

概念辨析
--------

CPU 位置与页面位置
   线程在哪个 node 运行，不代表其访问页面位于同一 node。

任务迁移与页面迁移
   任务迁移改变执行位置；页面迁移改变物理内存位置，二者互不等价。

策略偏好与硬限制
   Preferred 通常允许 fallback；Bind 和 cpuset 更严格地限制候选节点。

Node 与 Zone
   Node 描述访问距离和容量；Zone 描述硬件寻址与迁移约束。

未来分配与既有页面
   修改策略主要影响后续缺页和分配；既有页是否移动需要单独迁移协议。

本地访问与正确访问
   远端内存仍然有效，差异主要体现在延迟、带宽和互连竞争。

本章结论
--------

NUMA 性能由线程位置与页面位置共同决定；可靠放置必须把 CPU affinity、first-touch、内存策略、cpuset 和页面迁移作为一套系统设计。