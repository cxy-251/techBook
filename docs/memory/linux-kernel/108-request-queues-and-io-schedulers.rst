第108章：Request Queue 与 I/O Scheduler
======================================

核心知识点
----------

``struct request_queue`` 是块设备提交边界
   它汇集该设备上的 bio/request，并保存 queue limits、merge 规则、scheduler、blk-mq 映射、tag set 与驱动接口。

Queue limits 是硬能力边界
   最大 sectors、segment 数、边界、对齐、discard、write zeroes、zone 与 atomic write 等限制决定请求是否必须拆分。Scheduler 不能越过这些约束。

Merge 改变请求形状
   相邻、兼容的 bio/request 可以 front merge 或 back merge，减少 request、tag 与设备命令数量。操作标志、完整性、加密、flush 和 zone 语义都可能阻止合并。

I/O scheduler 控制软件派发顺序
   Scheduler 对尚未交给驱动的 request 排序、批量和限速。已经进入控制器内部队列的命令不再受主机 elevator 重排。

``none`` 不表示没有队列
   它只关闭通用 elevator 排序；blk-mq software context、hardware context、tag、驱动队列与设备固件仍然会排队。

``mq-deadline`` 侧重避免饥饿
   它在读写期限与 sector 顺序之间取舍，限制请求长期停留在软件队列，但不提供设备完成的实时保证。

BFQ 侧重服务公平性
   BFQ 按任务或 cgroup 预算分配服务，适合交互与多租户目标。它的收益依赖设备、内核配置和 workload，不能由名称直接推断。

Kyber 侧重延迟反馈控制
   Kyber 通过读写域 token 和延迟反馈限制派发深度。可用性与具体实现随版本变化，稳定理解是“用反馈控制并发”。

Plug 提供短期批量窗口
   ``blk_start_plug()`` 一类机制暂存当前上下文产生的请求，增加 merge 和批量派发机会。窗口过长会增加等待，因此在调度或显式结束时必须冲刷。

软件容量与硬件深度不同
   ``nr_requests``、scheduler tags、driver tags、硬件 queue depth 和应用 outstanding depth 属于不同层。修改一个参数不能代表其它层同步扩大。

调度目标存在冲突
   顺序吞吐、公平性、交互延迟和尾延迟不能同时无条件最优。选择 scheduler 必须结合介质类型、请求大小、读写比例、队列深度与租户模型。

关键路径
--------

Request queue 派发
~~~~~~~~~~~~~~~~~~

::

   上层提交 bio
   → 检查 queue limits
   → 尝试 merge
   → 形成 struct request
   → 直接派发或插入 elevator
   → scheduler 选择 request
   → blk_mq_hw_ctx
   → 驱动 queue_rq

小读与后台写竞争
~~~~~~~~~~~~~~~~

::

   小读进入软件队列
   → 后台写已形成批量 request
   → scheduler 比较 deadline、预算与类别
   → 选择派发顺序
   → 请求进入硬件队列
   → 继续受设备 backlog 影响
   → completion 返回

Scheduler 选择
~~~~~~~~~~~~~~

::

   确认真实设备与 Device Mapper 层
   → 查看 rotational、硬件队列和当前 scheduler
   → 固定请求大小、读写比例与深度
   → 对比 none / mq-deadline / BFQ / Kyber
   → 同时测吞吐、P99、CPU 与公平性
   → 选择满足业务目标的策略

概念辨析
--------

Request queue 与设备内部队列
   前者属于 Linux 块层；后者位于驱动、控制器和介质内部，主机 scheduler 无法完全观察或控制。

Merge 与 Scheduler
   Merge 减少并改变 request 形状；scheduler 决定等待 request 的派发顺序与节奏。

Queue limits 与调度策略
   Limits 是必须遵守的能力边界；scheduler 是在合法 request 集合中的策略选择。

Deadline 与完成期限
   Deadline 只限制软件队列饥饿，设备服务、错误恢复与完成调度仍可能超时。

``nr_requests`` 与硬件 queue depth
   前者主要描述软件等待容量；后者描述可交给驱动或控制器的在途命令规模。

本章结论
--------

Request queue 汇集块设备工作，I/O scheduler 在驱动接收前控制请求的 merge、等待和派发，并在吞吐、延迟与公平性之间做明确取舍。