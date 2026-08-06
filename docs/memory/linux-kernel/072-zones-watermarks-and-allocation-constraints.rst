第072章：Zone、水位线与分配约束
===============================

本章必须记住
------------

#. 页分配请求不是从“全局空闲内存池”随意取页，而是在 node、zone、watermark、GFP、order 和迁移类型约束下搜索。
#. NUMA node 表达物理内存访问距离；zone 表达硬件寻址、内核映射和迁移属性约束，二者是不同维度。
#. ``struct zone`` 保存一段物理页范围的起始 PFN、managed pages、空闲结构、per-CPU pageset、水位线和统计。
#. 可见 zone 由架构与配置决定，不能假设所有机器都同时存在 DMA、DMA32、Normal、HighMem 和 Movable。
#. ``ZONE_DMA`` 与 ``ZONE_DMA32`` 为受限设备提供低地址候选页，真正驱动代码仍应优先通过 DMA API 表达设备能力。
#. ``ZONE_NORMAL`` 通常承载内核可长期直接访问的普通物理内存，是许多核心内核对象的重要资源。
#. ``ZONE_HIGHMEM`` 主要出现在部分 32 位系统，页面不能始终保持内核永久直接映射。
#. ``ZONE_MOVABLE`` 用于集中可迁移页面，服务内存热插拔、反碎片和高阶连续页整理。
#. Zone 类型决定候选物理范围，不直接表示页面性能、是否空闲或分配一定成功。
#. Watermark 是 zone 级安全余量，用来决定当前空闲页是否足以接受某类分配。
#. ``min`` 是最低安全线附近的保留边界；接近或低于它时，普通分配进入强压力处理或失败路径。
#. ``low`` 通常是后台回收触发线；低于 low 时，内核会唤醒 ``kswapd`` 恢复平衡。
#. ``high`` 通常是后台回收目标线；回收到 high 附近后，``kswapd`` 可以停止主动扫描。
#. Watermark 不是固定字节常量，它受 zone 大小、``vm.min_free_kbytes``、``watermark_scale_factor`` 和运行状态影响。
#. ``lowmem_reserve`` 与 protection 规则防止可以使用高层内存的请求过度消耗低地址关键 zone。
#. 系统全局仍有空闲内存，不代表目标 node、目标 zone 或当前约束集合内还有可分配页。
#. Watermark 判断不仅看空闲页总数，还会考虑 order、保留页、highatomic 储备、迁移类型和 alloc flags。
#. Order 越高，需要的物理连续页越多，watermark 与空闲块形状越难同时满足。
#. GFP flags 是调用者向分配器声明的上下文与约束，不只是“分配优先级”。
#. ``GFP_KERNEL`` 适合可睡眠的普通进程上下文，通常允许 direct reclaim、I/O 和文件系统回收路径。
#. ``GFP_ATOMIC`` 适合不能睡眠的中断或原子路径，只能快速尝试并可能使用部分紧急储备，不保证成功。
#. ``GFP_NOWAIT`` 表示不进入会睡眠的直接回收路径，调用者必须准备立即失败处理。
#. ``GFP_NOIO`` 阻止回收递归进入块 I/O，常用于避免 I/O 栈递归和死锁。
#. ``GFP_NOFS`` 阻止回收递归进入文件系统路径，常用于文件系统持锁或事务上下文。
#. ``GFP_DMA``、``GFP_DMA32`` 和 ``__GFP_HIGHMEM`` 会改变可选择的最高 zone。
#. ``__GFP_MOVABLE`` 与 ``__GFP_RECLAIMABLE`` 表达页面迁移或回收属性，影响反碎片布局和 fallback。
#. ``__GFP_ZERO`` 要求返回页面清零，它改变返回内容要求，不放宽 node、zone 或水位限制。
#. ``__GFP_NORETRY``、``__GFP_RETRY_MAYFAIL`` 和 ``__GFP_NOFAIL`` 表达不同重试承诺，不能在不理解调用路径时随意添加。
#. ``__GFP_NOFAIL`` 只适合真正无法处理失败且允许长期等待的受控路径，不适合任意高阶请求或原子上下文。
#. 分配 API 返回 ``NULL`` 时，调用者必须按接口契约回滚或降级；GFP 标志不能代替错误处理。
#. 分配器先由 GFP 推导候选 zone，再结合 NUMA policy、cpuset 和 nodemask 构造可遍历的 zonelist。
#. Zonelist 按节点距离和 zone fallback 顺序遍历候选范围，不会忽略调用者声明的硬件和允许节点约束。
#. 从高层 zone fallback 到低层 zone 会消耗更稀缺资源，因此必须经过 reserve 与 watermark 检查。
#. Migratetype fallback 可以临时借用其它类型的空闲块，但会增加 pageblock 混合和后续外部碎片风险。
#. ``MIGRATE_HIGHATOMIC`` 等保留用于无法睡眠的紧急高阶需求，普通请求不应持续侵占这些储备。
#. 快路径水位不足时，可睡眠分配可能唤醒 ``kswapd``、执行 direct reclaim、compaction、OOM 处理或重试。
#. 原子分配通常不能执行普通 direct reclaim，失败更快，调用者必须缩小请求、预分配或延后到线程上下文。
#. ``/proc/zoneinfo`` 展示每个 node/zone 的 free、min、low、high、protection 和统计，是判断约束范围的主要证据。
#. ``/proc/zoneinfo`` 是瞬时状态，必须与请求的 GFP、order、node、cpuset 和调用时间对齐。
#. 调高 ``min_free_kbytes`` 或水位参数会增加安全余量，也会减少普通负载可直接使用的页，属于容量与稳定性权衡。
#. 诊断页分配必须先还原调用者约束，再看 zone 状态；只看 ``free``、``available`` 或单个 sysctl 无法解释结果。

必背路径
--------

一次页分配的约束解析：

::

   调用者给出 GFP、order 和目标节点
   → 判断当前上下文能否睡眠与回收
   → GFP 推导最高可用 zone 和迁移类型
   → NUMA policy、cpuset、nodemask 限定节点
   → 构造并遍历 zonelist
   → 检查每个 zone 的 watermark 和 reserve
   → 从 PCP 或 buddy 尝试取页
   → 成功返回或进入 slow path

水位压力路径：

::

   zone free pages 下降
   → 低于 low watermark
   → 唤醒 kswapd 后台回收
   → 可睡眠分配仍失败时进入 direct reclaim / compaction
   → 恢复到 high 附近后后台回收减弱
   → 无法满足约束时返回失败或进入允许的 OOM 路径

原子上下文分配：

::

   hardirq / softirq / 持 spinlock 路径
   → 使用不允许睡眠的 GFP 语义
   → 快速检查 PCP、buddy 和允许的 reserve
   → 不能执行普通阻塞回收
   → 失败时立即降级、丢弃、排队或转移到线程上下文

诊断分配失败：

::

   从日志取得 order 和 GFP mask
   → 解码可睡眠、I/O、FS、zone 和迁移约束
   → 确认 NUMA node 与 cpuset allowed mems
   → 查看 /proc/zoneinfo 的 free 和水位
   → 查看 buddyinfo 的目标 order 形状
   → 判断容量、水位、碎片还是上下文限制

必须区分
--------

* Node 与 Zone：Node 表示访问拓扑和距离；Zone 表示页的硬件可达性、映射和迁移约束。
* 全局空闲与可分配页：全局容量可能充足，目标 node/zone 在水位和 reserve 约束下仍不可用。
* ``GFP_KERNEL`` 与 ``GFP_ATOMIC``：前者允许睡眠和普通回收；后者只能快速尝试并要求调用者处理失败。
* Watermark 与空闲块形状：Watermark 判断安全余量；buddy order 判断是否存在所需连续块，两者必须同时满足。
* Zone fallback 与无限制借用：Fallback 只在允许范围和 reserve 规则内放宽候选，不能突破设备、cpuset 和策略约束。
* 迁移类型与分配优先级：Migratetype 用于反碎片和可迁移性组织，不是简单的请求优先级数字。

一句话结论
----------

页分配是约束求解：GFP 描述调用者能做什么，node 与 zone 描述页能从哪里来，watermark 和 order 决定当前状态能否交付。
