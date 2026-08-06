第080章：Per-CPU 内存与可扩展分配模式
=====================================

核心知识点
----------

Per-CPU 用复制减少共享写
   每个 possible CPU 获得一份独立数据，把高频全局更新转成高频本地更新和低频聚合读取，从而降低锁竞争、原子 RMW 和 cache line bouncing。

适用对象必须允许分布式状态
   统计计数器、本地缓存、临时队列和每 CPU 快路径适合 per-CPU；必须实时强一致的单一全局状态通常不适合直接拆分。

静态变量位于专用 section
   ``DEFINE_PER_CPU()`` 定义静态副本，链接和启动代码为每个 possible CPU 建立实例布局，``DECLARE_PER_CPU`` 用于跨文件声明。

动态分配返回 ``__percpu`` 指针
   ``alloc_percpu()`` 一类接口按 possible CPU 数量分配副本，最终由 ``free_percpu()`` 释放。大型结构会按 CPU 数量放大内存成本。

``__percpu`` 不是普通对象地址
   调用者必须通过 ``this_cpu_ptr()`` 或 ``per_cpu_ptr()`` 取得某个 CPU 的真实副本地址，不能直接解引用或传给要求普通线性地址的接口。

单次本地操作与多步访问不同
   ``this_cpu_*`` 表达在执行该指令的当前 CPU 上完成一次操作；取得普通指针后跨多条指令访问，则必须防止 task 迁移。

固定 CPU 不等于排除本地中断
   ``preempt_disable()`` 或 ``get_cpu_ptr()`` 可以阻止 task 迁移，但 hardirq、softirq 或 NMI 仍可能访问同一 CPU 副本，需要额外的上下文同步协议。

Per-CPU 不自动消除同 CPU 重入
   它主要减少跨 CPU 共享，不能替代 local lock、IRQ 控制、原子操作或序列计数对本地嵌套执行的保护。

远程访问会重新引入竞争
   读取其它 CPU 副本时，目标 CPU 可能正在更新；远程写还会破坏局部性，并可能与本地无锁操作竞争。

聚合结果不自动形成一致快照
   逐 CPU 求和通常混合不同时间点。允许近似统计时这是可接受的；多字段一致性或精确快照需要 ``u64_stats_sync``、seqcount、锁或专用协议。

``percpu_counter`` 平衡更新与读取成本
   它把本地批量计数和全局基值结合，适合高频更新、偶尔近似或精确汇总的场景。

Possible CPU 与 online CPU 不同
   Possible 集合决定副本分配范围，online 集合决定当前能执行的 CPU。离线副本是否计入统计取决于对象语义。

CPU hotplug 属于对象生命周期
   下线前必须停止新本地工作、排空队列、迁移对象或归并统计；不能只把 CPU 标记离线后继续保留未处理状态。

局部缓存会造成资源滞留
   Per-CPU freelist 和批量缓存能减少全局锁竞争，但缓存过大可能让空闲资源分散在各 CPU，造成全局可用量下降。

对齐是空间与共享的权衡
   Cacheline 对齐可以减少 false sharing，也会按 CPU 数量扩大内存开销，应由真实访问模式决定。

关键路径
--------

静态 per-CPU 统计：

::

   DEFINE_PER_CPU 建立每 CPU 副本
   → 热路径使用 this_cpu_* 更新本地状态
   → 避免全局共享写
   → 管理路径选择 possible 或 online CPU 集合
   → 按一致性要求读取每个副本
   → 聚合为近似值或精确结果

动态 per-CPU 对象：

::

   alloc_percpu 分配 __percpu 指针
   → 检查 NULL
   → 初始化每个 possible CPU 的复杂字段
   → CPU 上线时启用本地资源
   → 运行路径通过 this_cpu_ptr / per_cpu_ptr 访问
   → 下线时排空队列并归并状态
   → 停止所有访问
   → free_percpu

安全使用当前 CPU 指针：

::

   进入多步本地访问
   → get_cpu_ptr 或 preempt_disable 固定当前 CPU
   → 取得本 CPU 普通指针
   → 完成连续操作
   → 按需要处理 IRQ、softirq 或 NMI 并发
   → put_cpu_ptr 或 preempt_enable
   → 不在保护范围外保存该指针

一致读取多字段统计：

::

   本 CPU 写者更新字段组
   → 使用 u64_stats_sync、seqcount 或 local lock
   → 读者记录序列起点
   → 复制该 CPU 的全部字段
   → 检查序列是否变化
   → 变化时重试
   → 对其它 CPU 重复并聚合

CPU 下线：

::

   阻止该 CPU 新建本地工作
   → 排空 per-CPU 队列与缓存
   → 迁移对象或归并统计
   → 注销相关 IRQ、timer 与 worker
   → CPU 离线
   → 按对象语义保留或清理副本

概念辨析
--------

Per-CPU 副本与全局对象
   前者每个 CPU 一份并需要聚合；后者只有一份并要求共享同步。

单次 ``this_cpu_*`` 与长期本地指针
   单次操作在执行 CPU 上完成；多步使用普通指针必须固定 CPU，防止 task 迁移。

关闭抢占与关闭中断
   关闭抢占阻止 task 换 CPU；不能阻止同 CPU 的 IRQ、softirq 或 NMI 重入。

近似聚合与一致快照
   普通逐 CPU 读取可以混合不同时刻；一致字段组需要序列计数、锁或专用统计协议。

Possible CPU 与 online CPU
   Possible 决定分配了多少副本；online 表示当前可运行 CPU 集合。

本地更新与远程访问
   本地写是 per-CPU 的主要性能收益；远程写会重新引入一致性流量和竞争。

本章结论
--------

Per-CPU 内存通过减少共享提高多核扩展性。它把同步成本从热更新路径转移到迁移控制、聚合读取和 CPU hotplug 生命周期中。