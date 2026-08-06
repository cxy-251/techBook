第075章：诊断物理内存碎片与压力
================================

本章必须记住
------------

#. 物理内存分配失败必须区分三类原因：容量不足、连续形状不足、约束范围内没有可用页。
#. 容量表示空闲和可回收页总量；形状表示空闲页能否组成目标 order 的连续块；约束表示 node、zone、GFP、cpuset 和上下文边界。
#. 系统显示还有大量 free 或 available memory，高阶连续页分配仍然可能失败。
#. ``order`` 请求需要 ``2^order`` 个物理连续页，连续字节数为 ``PAGE_SIZE << order``。
#. 在 4 KiB 页系统上，order 9 是 2 MiB；其它页大小系统必须重新计算。
#. ``/proc/buddyinfo`` 按 node、zone 和 order 展示空闲块数量，是观察当前空闲形状的第一入口。
#. Buddyinfo 左侧低 order 表示小块，右侧高 order 表示大块；目标 order 和更高 order 都为 0 时，不能直接拆分得到目标块。
#. 大量 order-0 空闲页只能证明小页容量充足，不能证明存在 order-9 连续页。
#. ``/proc/zoneinfo`` 展示 zone 的 free、min、low、high、protection、highatomic 和统计，用于判断水位与保留页压力。
#. Buddyinfo 回答“空闲块长什么样”，zoneinfo 回答“当前 zone 是否允许把这些页交给该请求”。
#. 分析前必须先固定失败请求的 order、GFP mask、目标 node、zone、nodemask 和调用上下文。
#. 全局内存正常时，目标 cpuset、NUMA node、DMA zone 或 Normal zone 仍可能局部耗尽。
#. 外部碎片表示总空闲页足够，但可用连续块不足；内部碎片表示已分配块内部有空间未被有效使用。
#. Buddyinfo 主要反映外部连续块形状，不能直接衡量对象内部浪费。
#. 高阶分配对外部碎片敏感；order-0 分配通常只需要任意单页，失败通常表示更严重的容量或约束问题。
#. 高阶失败不必然是内核缺陷，许多调用者必须提供低阶、scatter-gather、vmalloc 或功能降级方案。
#. Zone 空闲页接近 ``min`` 时，分配器会保护安全余量，即使仍能数到一些空闲页也可能拒绝普通请求。
#. Lowmem reserve 会保护低地址 zone，防止可使用其它 zone 的请求耗尽 DMA 或 Normal 关键资源。
#. ``nr_free_highatomic`` 等储备用于紧急原子分配，普通请求不能把它等同于自由可用容量。
#. GFP mask 决定调用者是否允许睡眠、direct reclaim、I/O、文件系统递归、compaction 和较长重试。
#. ``GFP_ATOMIC`` 或 ``GFP_NOWAIT`` 失败时，系统可能仍有可回收内存，因为当前上下文不能等待回收完成。
#. ``GFP_NOIO`` 与 ``GFP_NOFS`` 会缩小回收手段，以避免递归和锁依赖，代价是压力下更容易失败。
#. ``__GFP_NORETRY`` 会缩短重试，``__GFP_RETRY_MAYFAIL`` 允许更积极尝试但最终仍可失败。
#. ``__GFP_NOFAIL`` 不是消除内存压力的开关，只能用于具有严格语义且可长期等待的受控低阶路径。
#. Allocation failure 日志中的 ``order``、``mode`` 或 GFP mask、nodemask、CPU、PID 和 call trace 是重建请求的核心证据。
#. 调用栈说明哪个对象或子系统请求页面；失败打印点只说明分配器无法满足请求，不等于调用栈最上层就是根因。
#. ``__GFP_NOWARN`` 可以抑制失败日志，不改变分配成功率，也不能替代调用者错误处理。
#. Compaction 通过迁移 movable pages，把分散空闲页聚合成更高 order 连续块。
#. Direct compaction 在当前高阶分配路径中执行；``kcompactd`` 在后台改善 node 的连续页形状。
#. Compaction 解决形状，不凭空增加总容量；容量不足仍需要 reclaim、swap、释放对象或降低负载。
#. Reclaim 解决容量，不保证释放页物理相邻；高阶请求经常需要 reclaim 与 compaction 协同。
#. 长期 pin 页面、不可移动 slab、页表页、设备页和混合 pageblock 会阻断迁移，限制压缩结果。
#. ``__GFP_MOVABLE`` 页面更适合迁移和反碎片；错误地把不可移动对象放入 movable 区会破坏恢复能力。
#. Migratetype fallback 会让 pageblock 混合，短期提高成功率，长期可能增加碎片。
#. CMA 依靠预留的可移动区域提供部分连续内存；区域被不可迁移 pin 污染时也可能分配失败。
#. 透明大页通常需要高阶页面，碎片会降低 THP 分配和 collapse 成功率，不一定影响普通 4 KiB 页分配。
#. ``/proc/pagetypeinfo`` 可进一步观察 pageblock 迁移类型与各 order 空闲块，字段解释依赖目标内核版本。
#. ``/proc/vmstat`` 中的 ``compact_*``、``pgscan_*``、``pgsteal_*``、``allocstall`` 等计数可说明回收和压缩压力趋势。
#. 计数是累计值，必须在固定时间窗口计算增量，不能只看启动以来总数。
#. Page allocation tracepoint、page owner 和 stack depot 可以帮助定位谁长期持有页面或制造碎片，前提是内核已启用相应配置。
#. Memory pressure 需要同时观察 reclaim、swap、direct reclaim 延迟、kswapd、OOM 和业务尾延迟。
#. 内存压力高不等于碎片高；碎片高也不等于容量即将耗尽，两者可以独立或叠加。
#. Order-0 分配持续失败、Normal zone 低于 min、direct reclaim 长时间无进展，通常比单次高阶失败更严重。
#. OOM killer 处理约束范围内的容量危机，不能直接制造物理连续高阶块，因此不应把高阶碎片简单归为 OOM。
#. 调整 ``min_free_kbytes``、compaction 参数、THP、CMA 或内存策略前，必须先证明问题属于对应层次。
#. 提高保留水位可能减少临界分配失败，也会减少普通工作负载可用内存。
#. 提高 compaction 积极度可能改善高阶块，也会增加 CPU、迁移和延迟成本。
#. 最可靠修复通常从调用者需求开始：降低 order、预分配、使用 mempool、允许分散页或缩短 pin 生命周期。
#. 诊断报告必须写明哪个 node/zone、何种 GFP、哪个 order、何时失败、当时水位与 buddy 形状，以及 slow path 做过什么。

必背路径
--------

读取一次分配失败日志：

::

   保存完整 allocation failure 日志和调用栈
   → 提取 order、GFP mask、nodemask、CPU 和 PID
   → 按 PAGE_SIZE 计算连续字节需求
   → 解码睡眠、回收、I/O、FS、zone 和迁移约束
   → 定位调用者对象与失败降级路径
   → 对齐同一时刻的 zoneinfo、buddyinfo 和 vmstat

判断容量还是碎片：

::

   固定目标 node 和 zone
   → 查看 zoneinfo 的 free 与 min/low/high
   → 查看 buddyinfo 的目标 order 和更高 order
   → free 接近水位且各 order 都少：容量压力
   → 低 order 多、高 order 空：外部碎片
   → 两者同时异常：容量与碎片叠加
   → 再检查 GFP 和上下文是否允许恢复

Compaction 恢复：

::

   高阶请求找不到连续块
   → 识别可迁移页和空闲页
   → 迁移 movable pages
   → 聚合相邻空闲页
   → buddy 合并成更高 order
   → 重新执行水位和分配检查
   → 被 pin 或不可移动页阻断时失败

持续压力证据：

::

   固定采样时间窗口
   → 记录 vmstat reclaim / compaction 增量
   → 观察 kswapd、kcompactd 和 direct reclaim CPU
   → 记录 swap、OOM 和 allocation stalls
   → 对照业务延迟与失败时间
   → 区分瞬时尖峰和长期不可恢复压力

必须区分
--------

* 容量不足与形状不足：容量不足缺少总页数；形状不足缺少目标 order 的连续块。
* ``buddyinfo`` 与 ``zoneinfo``：前者展示各 order 空闲形状；后者展示水位、reserve 和 zone 压力。
* Reclaim 与 Compaction：Reclaim 释放页增加容量；compaction 迁移页形成连续形状。
* 高阶失败与系统 OOM：高阶块可以因碎片失败；OOM 主要表示约束范围内连普通容量也无法恢复。
* 全局空闲与约束内可用：其它 node 或 zone 的空闲页可能不满足 DMA、cpuset、mempolicy 或当前上下文。
* 日志抑制与问题修复：``__GFP_NOWARN`` 只减少日志，不改变碎片、压力或调用者恢复能力。

一句话结论
----------

物理内存故障要先还原请求约束，再用 zone 水位判断容量、用 buddy order 判断形状，最后证明回收和压缩为何能或不能恢复。
