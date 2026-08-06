第049章：CPU 亲和性、负载均衡与多核调度
========================================

本章必须记住
------------

#. 多核调度不仅决定“哪个 task 运行”，还决定“这个 task 在哪个 CPU 上运行”。
#. CPU affinity 是 task 可运行 CPU 集合的硬约束，调度器的放置和迁移只能在该集合内进行。
#. CPU 集合通常用 ``cpumask`` 表示，调度代码大量使用集合交集、筛选和遍历，而不是只比较单个 CPU 编号。
#. 用户设置的 affinity、cpuset/cgroup 限制、CPU online/active 状态和内核内部约束共同形成 task 的有效允许集合。
#. 一个简化关系是：有效 CPU 集合 = 用户 affinity ∩ cpuset 允许集合 ∩ 当前可用 CPU 集合。
#. 用户请求绑定某个 CPU，不保证该 CPU 永远在线，也不保证管理层 cpuset 允许该 task 使用它。
#. ``task_struct`` 中的 ``cpus_ptr`` 一类字段为调度器提供当前有效 CPU 集合；具体字段和更新路径随内核版本演进。
#. affinity 只规定 task 可以在哪里运行，不规定它此刻实际运行在哪个 CPU。
#. task 被唤醒时，``select_task_rq`` 一类路径会在允许集合中选择目标 ``rq``。
#. Wakeup placement 要在上次运行 CPU、唤醒者 CPU、空闲 CPU、缓存局部性和队列负载之间取舍。
#. 把 task 放回 previous CPU 可能保留缓存热数据，把它放到更空闲 CPU 可能减少排队时间。
#. task 迁移到另一 CPU 会带来缓存、TLB、NUMA 内存和锁数据重新变热的成本。
#. 调度器不会为了追求表面上的平均负载而无条件迁移每个 task。
#. 每个 CPU 有独立 ``rq``；负载均衡负责在多个 ``rq`` 之间发现失衡并迁移合法的可运行实体。
#. Scheduler domain 用层级结构表达 SMT、物理核心、共享缓存、NUMA 节点和更大 CPU 集合。
#. ``struct sched_domain`` 的 span 表示该层级参与负载均衡的 CPU 范围。
#. 调度器通常先在较近的拓扑层级寻找平衡机会，再逐步扩大到成本更高的层级。
#. 同一核心的 SMT sibling、同一 LLC 的 CPU 和跨 NUMA 节点 CPU 具有不同迁移成本。
#. ``struct sched_group`` 把一个调度域拆成可比较的组，负载均衡可先找 busiest group，再找 busiest runqueue。
#. 周期性均衡、idle balancing 和 wakeup placement 是不同入口；它们都可能改变 task 的 CPU 位置。
#. Wakeup placement 在 task 从睡眠变为 runnable 时决定初始落点；load balancing 在后续运行中纠正局部失衡。
#. CPU affinity、cpuset 和隔离设置可以阻止看似合理的迁移，因此“有空闲 CPU”不等于目标 task 能使用它。
#. CPU quota 限制的是一段时间内可消费的 CPU 预算，不等于 affinity；task 可能允许多个 CPU，却因配额被节流。
#. ``migration_disable()`` 一类机制可以临时禁止当前 task 被迁移，但不等于永久修改用户 affinity。
#. CPU hotplug 会改变可用 CPU 集合，并触发 task、IRQ 和 per-CPU 工作迁移或重建。
#. PELT 一类机制为调度器提供随时间衰减的 utilization/load 信号，帮助估计 task 与 CPU 的近期负载。
#. CPU utilization 描述需求，CPU capacity 描述某个 CPU 能提供的相对计算能力；二者不是同一量。
#. 在异构 CPU 系统中，相同 task 放在不同 CPU 上可能获得不同执行速度。
#. Capacity-aware scheduling 会避免把高需求 task 长期放到能力不足的 CPU，也会考虑过度集中造成的队列压力。
#. Energy-aware scheduling 使用能耗模型、utilization 与 CPU capacity 比较候选放置，目标是在性能约束内降低能耗。
#. EAS 依赖内核配置、Energy Model、拓扑和平台支持，不是所有机器都会启用或走同一分支。
#. 能耗最低的 CPU 不一定是最低延迟的 CPU；调度器要在性能、能耗、缓存和迁移成本之间权衡。
#. NUMA 自动平衡和内存位置会反向影响 task 放置；CPU 空闲但访问远端内存，整体性能仍可能更差。
#. 中断 affinity 会影响哪个 CPU 承担 IRQ 和 softirq；用户 task affinity 不能单独决定完整 CPU 干扰。
#. 排查多核调度时，应先确认允许集合，再看实际 CPU、runqueue 压力、拓扑、cgroup 配额和迁移事件。

必背路径
--------

Task 被唤醒后的 CPU 选择：

::

   task 从睡眠变为 runnable
   → 读取有效 allowed cpumask
   → 排除 offline、inactive 或不允许 CPU
   → 考虑 previous CPU 和 wake CPU 的缓存关系
   → 比较候选 CPU 的 idle、utilization 与 capacity
   → 结合 sched_domain、NUMA 和能耗约束
   → 选择目标 CPU 的 rq
   → 入队并执行抢占判断

周期性负载均衡：

::

   当前 CPU 到达均衡时机或进入 idle
   → 遍历相应 sched_domain 层级
   → 比较 sched_group 负载与 capacity
   → 找到 busiest group 和 busiest rq
   → 筛选允许迁移的 task
   → 检查 affinity、迁移状态和缓存成本
   → 把 task 移到目标 rq
   → 更新两侧队列与负载统计

Affinity 修改：

::

   用户或管理器提交 CPU 集合
   → 内核验证权限和 CPU 编号
   → 与 cpuset、active CPU 等约束求交集
   → 更新 task 的有效 allowed mask
   → 当前 CPU 不再合法时触发迁移
   → 后续 placement 和 balancing 只能使用新集合

排查局部 CPU 拥塞：

::

   查看目标 task 的 allowed CPU 集合
   → 查看 task 实际运行 CPU 与迁移历史
   → 查看热点 CPU 的 rq 和 IRQ/softirq 压力
   → 检查 cpuset、quota 和 CPU isolation
   → 检查 sched_domain 是否允许跨相关 CPU 均衡
   → 检查 NUMA、capacity 与 EAS 约束
   → 用 sched_migrate_task 等事件验证迁移

必须区分
--------

* Affinity 与实际运行 CPU：affinity 给出允许集合；调度器仍会在集合内选择当前运行 CPU。
* 空闲 CPU 与可用 CPU：CPU 空闲不代表它在 task 的 allowed mask、cpuset 或调度域中。
* Wakeup placement 与负载均衡：placement 决定唤醒时的初始 CPU；balancing 负责后续纠正队列失衡。
* Load 与 utilization：load 常包含权重和可运行竞争含义；utilization 更接近近期实际 CPU 使用需求。
* Utilization 与 capacity：utilization 是任务需求；capacity 是 CPU 可提供的相对能力。
* Affinity 与 CPU quota：affinity 限制位置；quota 限制一定周期内可使用的总 CPU 时间。
* 性能放置与节能放置：最低延迟可能倾向高能力或空闲 CPU；最低能耗可能选择不同位置。

一句话结论
----------

多核调度先受 affinity 和 cpuset 限制，再在调度域、负载、缓存、NUMA、CPU capacity 与能耗之间选择和修正 task 的运行位置。
