第072章：Zone、水位线与分配约束
===============================

核心知识点
----------

页分配不是从全局池中随意取页
   一次请求同时受 node、zone、watermark、GFP、order、migratetype、cpuset 和内存策略约束。全局仍有空闲内存，不代表目标约束内存在可交付页面。

Node 与 Zone 表达不同维度
   Node 描述 NUMA 拓扑和访问距离；zone 描述硬件寻址、内核映射和迁移约束。一次分配必须同时满足二者。

``struct zone`` 是局部页管理根对象
   Zone 保存 PFN 范围、managed pages、空闲结构、per-CPU pageset、水位线、保留规则和统计。

Zone 类型由平台决定
   DMA、DMA32、Normal、HighMem、Movable 是否存在取决于架构与配置。Zone 只限定候选物理范围，不保证页面空闲或分配成功。

Watermark 保护系统安全余量
   ``min`` 是最低安全边界，``low`` 常用于触发后台回收，``high`` 常作为恢复目标。它们不是固定常量，而是由 zone 大小和系统参数计算得到。

保留规则保护稀缺区域
   lowmem reserve 和 protection 防止普通请求过度消耗低地址关键 zone。能使用更高 zone 的请求，不能无限制侵占 DMA 或 Normal 资源。

GFP 描述调用者能力与意图
   GFP 不只是优先级。它决定能否睡眠、回收、进入 I/O 或文件系统、选择哪些 zone、采用哪种迁移属性以及允许多强的重试。

``GFP_KERNEL`` 与 ``GFP_ATOMIC`` 的根本差异是上下文
   ``GFP_KERNEL`` 适合可睡眠路径，可进入 direct reclaim；``GFP_ATOMIC`` 面向不可睡眠路径，只能快速尝试并要求调用者处理失败。

``GFP_NOIO`` 与 ``GFP_NOFS`` 限制回收递归
   它们用于避免 I/O 栈或文件系统锁递归，代价是内存压力下可用恢复手段减少。

Order 同时增加容量与连续性要求
   Order 越高，所需物理连续页越多。即使水位允许，总空闲页也可能因为缺少足够大的 buddy 块而无法满足请求。

迁移类型服务反碎片布局
   Movable、Reclaimable、Unmovable 等类型用于把相似生命周期页面聚集。Fallback 可以短期提高成功率，也会混合 pageblock 并增加后续碎片。

慢路径能力由 GFP 决定
   快路径失败后，可睡眠请求可能唤醒 ``kswapd``、执行 direct reclaim、compaction、重试或 OOM；原子请求通常不能使用这些阻塞恢复路径。

关键路径
--------

解析一次页分配请求：

::

   调用者给出 GFP、order 和目标节点
   → 判断上下文能否睡眠与回收
   → GFP 推导候选 zone 与 migratetype
   → mempolicy、cpuset 和 nodemask 限定节点
   → 构造 zonelist
   → 检查 zone watermark 与 reserve
   → 从 PCP 或 buddy 取页
   → 成功返回或进入允许的慢路径

水位压力恢复：

::

   zone free pages 下降
   → 低于 low watermark
   → 唤醒 kswapd
   → 后台回收释放可回收页
   → 必要时分配者执行 direct reclaim / compaction
   → 恢复到 high 附近
   → 分配重新检查水位与空闲块

原子上下文分配：

::

   hardirq、softirq 或持 spinlock 路径
   → 使用非睡眠 GFP 语义
   → 快速检查 PCP、buddy 与允许储备
   → 不进入普通阻塞回收
   → 失败后立即降级、丢弃或转移到线程上下文

诊断分配失败：

::

   从日志取得 order 与 GFP mask
   → 解码睡眠、I/O、FS、zone 和迁移约束
   → 确认 node、cpuset 与 mempolicy
   → 查看 zoneinfo 的 free、min、low、high 和 protection
   → 查看 buddyinfo 的目标 order 形状
   → 判断容量、水位、碎片还是上下文限制

概念辨析
--------

Node 与 Zone
   Node 表示访问拓扑；Zone 表示物理页可达性与迁移约束。

全局空闲与可分配页
   全局容量可以充足，目标 node 或 zone 在水位与保留规则下仍不可用。

Watermark 与空闲块形状
   Watermark 判断安全余量；buddy order 判断连续块是否存在，两者必须同时满足。

``GFP_KERNEL`` 与 ``GFP_ATOMIC``
   前者允许睡眠和回收；后者只能快速尝试，失败处理属于调用者协议的一部分。

Zone fallback 与无约束借用
   Fallback 只能在允许的节点、zone 和保留规则内进行，不能突破设备能力、cpuset 或内存策略。

迁移类型与优先级
   Migratetype 用于反碎片和可迁移性组织，不是简单的分配优先级。

本章结论
--------

页分配本质上是约束求解：GFP 说明调用者能等待和恢复到什么程度，node 与 zone 限定页面来源，watermark 与 order 决定当前状态是否能够交付。