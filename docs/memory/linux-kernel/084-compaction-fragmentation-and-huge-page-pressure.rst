第084章：内存压缩、碎片与大页压力
================================

本章必须记住
------------

#. 高阶分配需要 ``2^order`` 个物理连续基础页，空闲页总量足够不代表存在所需连续形状。
#. External fragmentation 表示空闲页分散在多个小块中，无法组成目标 order 的连续页块。
#. Internal fragmentation 表示已经分配的对象或页块内部存在未使用空间，两者不是同一问题。
#. 在 4 KiB 基础页系统上，order-9 是 512 页、2 MiB；其它页大小和大页配置必须重新计算。
#. Buddy allocator 按 node、zone、order 和 migratetype 保存空闲块，目标分配必须在允许范围内找到合适形状。
#. ``MemFree``、``MemAvailable`` 只提供容量视角，不能证明目标 node/zone 中存在高阶块。
#. ``/proc/buddyinfo`` 展示每个 node、zone 和 order 的空闲块数量，是判断连续形状的第一证据。
#. 目标 order 及所有更高 order 都为 0 时，buddy 不能直接通过拆分得到目标块。
#. ``/proc/pagetypeinfo`` 展示 pageblock 迁移类型和空闲块分布，用于判断 Movable、Unmovable、Reclaimable、CMA 等混合情况。
#. Migratetype 的目标是把相似可迁移属性的页集中，减少不可移动页把潜在连续区域切碎。
#. Fallback 到其它 migratetype 可以提高当前分配成功率，也可能污染 pageblock 并增加未来碎片。
#. Compaction 通过迁移可移动页，把分散空闲页聚合成更大的连续空闲范围。
#. Compaction 改变页面位置和空闲形状，不创造新的总内存容量。
#. Reclaim 释放页面增加容量，但释放结果可能仍然分散；高阶分配经常需要 reclaim 与 compaction 协同。
#. Compaction 同时扫描可迁移页和空闲目标页，把内容迁到另一位置，再释放原页形成连续区域。
#. 匿名页迁移需要更新页表和反向映射；文件页迁移需要维持 Page Cache 与 mapping 关系。
#. 正在 writeback、被锁定、被长期 pin、属于设备或具有特殊引用的页面可能无法迁移。
#. 长期 GUP pin、DMA、不可移动 slab、页表和内核对象会形成 compaction 障碍。
#. 一个 pageblock 中少量不可移动页就可能阻止该区域形成完整高阶块。
#. ``__GFP_MOVABLE`` 表示调用者承诺页面内容可迁移，是反碎片和 compaction 的重要输入。
#. 把实际不可移动的对象错误标为 movable 会破坏迁移正确性；把可移动对象长期放入 unmovable 区会降低整理能力。
#. Direct compaction 在当前高阶分配路径中同步执行，会把扫描和迁移成本直接计入业务线程延迟。
#. ``kcompactd`` 是每个 NUMA node 的后台压缩线程，尝试提前改善高阶空闲块形状。
#. 后台压缩可以减少前台同步压缩，但会消耗 CPU、内存带宽并迁移页面。
#. Proactive compaction 会在未发生即时失败时主动整理，积极度提高可能改善连续块，也会增加系统成本。
#. Compaction 成功不等于目标分配一定成功，之后还要重新检查 watermark、zone、migratetype 和竞争状态。
#. Compaction 失败也不等于系统没有空闲内存，它可能只表示当前形状无法通过可允许迁移恢复。
#. ``compact_*`` vmstat 计数需要在时间窗口内计算增量，用于判断 direct/background compaction 的尝试与结果。
#. 扫描和迁移很多但成功块很少，说明不可移动障碍、空闲目标不足或页面状态限制严重。
#. THP（Transparent Huge Pages）尝试用较大 folio 或 PMD 大页减少 TLB miss，并改善部分内存访问性能。
#. THP 不等于 HugeTLB；THP 由匿名内存、shmem 或文件场景按策略透明使用，失败时通常可回退基础页。
#. THP 的分配和 collapse 可能触发高阶分配、reclaim 和 compaction，形成 fault 或 ``khugepaged`` 延迟。
#. THP ``always``、``madvise``、``never`` 等策略控制使用范围，具体 sysfs 语义以目标内核版本为准。
#. ``madvise`` 模式仍需应用对范围使用 ``MADV_HUGEPAGE`` 等提示，并不提供成功保证。
#. ``MADV_NOHUGEPAGE`` 可阻止目标范围使用 THP，适合已经证明大页收益不足或延迟不可接受的场景。
#. ``khugepaged`` 在后台扫描并尝试把基础页 collapse 成 THP，成功依赖 VMA、页状态、引用和连续目标页。
#. THP 分配失败并回退 4 KiB 页通常不会导致应用分配失败，但可能损失性能并增加页表与 TLB 压力。
#. THP fault 中同步 compaction 可能造成明显尾延迟，必须结合策略和 trace 判断是否发生。
#. HugeTLB 使用显式管理的大页池，具有预留、配额、挂载和不可换出等独立语义。
#. HugeTLB 页池不足时，应用可能直接分配或 mmap 失败，不能按 THP 的透明基础页回退理解。
#. 启动时预留 HugeTLB 通常比系统长期运行后动态申请更容易获得连续物理页。
#. HugeTLB、THP 与普通高阶内核分配虽然都需要连续形状，生命周期和失败语义不同。
#. DMA 缓冲区的连续性需求必须通过 DMA API、IOMMU、scatter-gather 或 CMA 表达，不能简单依赖高阶 ``alloc_pages``。
#. IOMMU 可以把分散物理页映射为设备连续 IOVA，但不改变设备、平台和 DMA API 的实际约束。
#. Scatter-gather 允许设备处理多个段，从设计上减少对大块连续物理页的依赖。
#. CMA 预留一段主要由可移动页使用的区域，在需要时迁移这些页以提供连续内存。
#. CMA 区被长期 pin 或不可迁移页污染时，仍可能在总空闲量充足时分配失败。
#. 网络大包、驱动 ring、巨大 skb、页表和某些内核对象也可能产生高阶需求，调用者应提供失败降级路径。
#. 高阶分配应尽可能避免成为不可恢复的运行时硬要求，优先考虑预分配、分段、page array、scatterlist 或低阶 fallback。
#. 单次高阶失败日志不等于整机 OOM；许多高阶请求会按 GFP 语义静默失败或回退。
#. OOM killer 主要解决约束域内容量危机，不能直接重新排列物理页形成连续高阶块。
#. 杀掉进程释放大量页后可能间接改善形状，但不能把 OOM 当作碎片整理机制。
#. 调整 ``vm.compaction_proactiveness``、THP 策略、HugeTLB 数量或 CMA 前，必须先证明目标 workload 的形状需求。
#. 提高 compaction 积极度可能降低高阶失败，也可能增加 CPU、迁移流量和业务抖动。
#. 关闭 THP 可能减少同步压缩延迟，也可能增加 TLB miss 和页表开销，必须用 workload 数据决策。
#. 调试高阶失败必须记录 order、PAGE_SIZE、GFP、node、zone、migratetype、watermark 和调用栈。
#. 运行证据应同时读取 buddyinfo、pagetypeinfo、zoneinfo、vmstat、THP/HugeTLB 状态和 allocation failure 日志。
#. 最稳定判断顺序是：确认连续需求 → 确认约束域 → 检查高阶形状 → 检查可迁移障碍 → 检查 compaction 结果 → 评估调用者降级。

必背路径
--------

高阶分配：

::

   调用者提交 GFP 与 order
   → 确定 node、zone 和 migratetype
   → 检查 watermark
   → buddy 查找目标 order 或更高 order
   → 命中时拆分并返回连续页块
   → 未命中时进入 reclaim / compaction 慢路径
   → 重试成功或按调用者语义失败

Compaction：

::

   目标 zone 缺少高阶连续块
   → 从一侧扫描可迁移 folio
   → 从另一侧扫描空闲目标页
   → 隔离可迁移页与目标页
   → 复制内容并更新 mapping / rmap / 页表
   → 释放旧物理页位置
   → buddy 合并相邻空闲页
   → 形成更高 order 块
   → 重新尝试分配

THP fault：

::

   进程访问符合 THP 策略的匿名范围
   → 检查 VMA、对齐和策略
   → 尝试分配大 folio / PMD 大页
   → 必要时 direct reclaim 或 compaction
   → 成功时建立大页映射
   → 失败时按策略回退基础页
   → 记录 THP allocation / fallback 统计

``khugepaged`` collapse：

::

   后台扫描候选 VMA
   → 检查基础页存在、引用和可合并条件
   → 取得连续大页目标
   → 复制或迁移基础页内容
   → 替换页表映射
   → 回收旧基础页
   → 成功形成 THP 或放弃本次候选

诊断碎片：

::

   从日志提取 order、GFP 和调用栈
   → 计算目标连续字节数
   → 在 zoneinfo 检查水位
   → 在 buddyinfo 检查目标及更高 order
   → 在 pagetypeinfo 检查 pageblock 污染
   → 查看 compact / THP vmstat 增量
   → 判断容量、形状、迁移障碍或上下文限制

必须区分
--------

* 容量不足与外部碎片：容量不足缺少可用页总数；外部碎片缺少目标 order 的连续形状。
* Reclaim 与 Compaction：Reclaim 释放页；compaction 迁移页并整理物理布局。
* Direct compaction 与 ``kcompactd``：前者由当前分配任务同步承担；后者在后台提前整理 node。
* THP 与 HugeTLB：THP 透明使用且常可回退基础页；HugeTLB 使用显式页池和独立配额，失败语义更严格。
* 物理连续与设备连续：物理连续是页框相邻；设备可能通过 IOMMU 或 scatter-gather 使用分散页，必须由 DMA API 定义。
* 高阶失败与 OOM：高阶请求可因形状失败；OOM 处理约束域内无法恢复的容量危机，两者不能等同。

一句话结论
----------

Compaction 通过迁移可移动页恢复物理内存的连续形状，高阶页、THP、HugeTLB 与 DMA 都必须按各自的连续性、回退和生命周期语义分析。
