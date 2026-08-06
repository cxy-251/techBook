第049章：CPU 亲和性、负载均衡与多核调度
========================================

核心知识点
----------

多核调度同时决定 task 与 CPU 的匹配
   调度器不仅选择下一个 task，还要决定它在哪个 CPU 的运行队列中竞争。位置选择会影响排队时间、缓存、NUMA 和能耗。

CPU affinity 是可运行位置的硬约束
   task 只能在有效允许集合中运行。该集合通常由用户 affinity、cpuset/cgroup 约束和 CPU online/active 状态共同求交得到。

affinity 不决定当前运行位置
   affinity 只定义允许 CPU 集合；task 实际落在哪个 CPU，还由唤醒放置、负载均衡、缓存局部性和调度拓扑决定。

唤醒放置在延迟与局部性之间权衡
   task 被唤醒时，调度器会在允许 CPU 中比较 previous CPU、waker CPU、空闲程度、队列压力和缓存关系，选择目标 ``rq``。

迁移具有成本
   迁移可以减少局部排队，却可能丢失缓存和 TLB 热度、增加远端 NUMA 访问，并引入跨 CPU 队列同步。因此调度器不会为了表面平均而无条件迁移。

调度域表达硬件拓扑层级
   ``sched_domain`` 和 ``sched_group`` 把 SMT、核心、共享缓存、NUMA 节点等层级组织起来。负载均衡通常先在近层级寻找机会，再扩大到迁移成本更高的范围。

负载均衡具有多个入口
   Wakeup placement 决定 task 刚变为 runnable 时的落点；周期性均衡与 idle balancing 在后续运行中修正多个 ``rq`` 之间的失衡。

utilization、capacity 与能耗共同影响异构放置
   utilization 表示近期计算需求，capacity 表示 CPU 可提供的相对能力。异构系统还可能结合 Energy Model，在性能、队列压力和能耗之间选择 CPU。

关键路径
--------

task 唤醒后的 CPU 选择：

::

   task 变为 runnable
   → 取得有效 allowed cpumask
   → 排除 offline、inactive 或不允许 CPU
   → 考虑 previous CPU 与 waker CPU
   → 比较 idle、utilization 和 capacity
   → 结合缓存、sched_domain、NUMA 与能耗约束
   → 选择目标 CPU 的 rq
   → 入队并执行抢占判断

周期性负载均衡：

::

   到达均衡时机或 CPU 进入 idle
   → 遍历相关 sched_domain
   → 比较 sched_group 的负载与 capacity
   → 找到 busiest group 和 busiest rq
   → 筛选允许迁移的 runnable task
   → 检查 affinity、迁移状态和局部性成本
   → 把 task 移入目标 rq
   → 更新两侧队列统计

修改 CPU affinity：

::

   用户或管理器提交 CPU 集合
   → 内核验证权限与编号
   → 与 cpuset 和 active CPU 求交集
   → 更新 task 的有效允许集合
   → 当前 CPU 不再合法时触发迁移
   → 后续放置与均衡只能使用新集合

排查局部 CPU 拥塞：

::

   检查 task 的有效 allowed CPU 集合
   → 检查实际运行 CPU 与迁移记录
   → 检查目标 CPU 的 rq、IRQ 与 softirq 压力
   → 检查 cpuset、quota 和 CPU isolation
   → 检查 sched_domain、NUMA 与 capacity 约束
   → 用 sched_migrate_task 等事件验证实际迁移

概念辨析
--------

Affinity 与实际运行 CPU
   affinity 给出合法集合；调度器在集合内继续选择当前落点。

空闲 CPU 与可用 CPU
   CPU 空闲不表示它属于 task 的 affinity、cpuset 或有效调度范围。

Wakeup placement 与负载均衡
   placement 决定唤醒时的初始 CPU；balancing 负责后续修正队列失衡。

Load 与 utilization
   load 更强调可运行竞争和权重；utilization 更接近近期实际 CPU 需求。

Utilization 与 capacity
   utilization 描述任务需求；capacity 描述 CPU 的相对供给能力。

Affinity 与 CPU quota
   affinity 限制 task 可以在哪里运行；quota 限制一段周期内最多能使用多少 CPU 时间。

性能放置与节能放置
   最低延迟可能倾向高能力或空闲 CPU；最低能耗可能选择不同位置。

本章结论
--------

多核调度先受 affinity、cpuset 和 CPU 状态约束，再在运行队列压力、缓存、拓扑、NUMA、CPU capacity 与能耗之间选择并修正 task 的运行位置。
