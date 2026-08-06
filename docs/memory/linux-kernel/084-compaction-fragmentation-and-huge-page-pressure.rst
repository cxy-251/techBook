第084章：内存压缩、碎片与大页压力
================================

核心知识点
----------

高阶分配要求连续物理形状
   Order-n 请求需要 ``2^n`` 个连续基础页。系统空闲页总量充足，不表示目标 node、zone 和 migratetype 中存在所需连续块。

外部碎片与容量不足不同
   外部碎片是空闲页分散成小块；容量不足是可用页总量不足。``MemFree`` 和 ``MemAvailable`` 只能提供容量视角，不能证明高阶形状。

Buddy order 是形状证据
   ``/proc/buddyinfo`` 按 node、zone 和 order 展示空闲块。目标 order 及所有更高 order 都为空时，分配器不能直接通过拆分得到所需块。

Migratetype 保护可整理区域
   Movable、Unmovable、Reclaimable 和 CMA 等类型尽量把迁移属性相近的页放在同一 pageblock。跨类型 fallback 会提高当前成功率，也可能污染未来连续形状。

Compaction 通过迁移恢复形状
   压缩同时寻找可迁移页和空闲目标页，把页面内容及 mapping、rmap、页表关系迁到新位置，再释放旧位置供 buddy 合并。

Compaction 不增加总容量
   Reclaim 释放内容以增加空闲页；compaction 重新排列现有页面。高阶分配常需要两者协同，但它们解决不同问题。

不可移动页面形成物理障碍
   长期 GUP pin、DMA、不可移动 slab、页表、设备页和特殊引用会阻断迁移。Pageblock 中少量障碍就可能破坏整段高阶块。

可迁移性是调用者承诺
   ``__GFP_MOVABLE`` 表示页面内容可以迁移。错误标记会破坏迁移正确性；长期把可移动对象放进 unmovable 区也会降低整理能力。

Direct compaction 影响前台延迟
   高阶分配慢路径可以同步扫描和迁移页面，成本由当前业务任务承担。压缩成功后仍需重新检查水位、zone 和竞争状态。

``kcompactd`` 提供后台整理
   每个 NUMA node 的后台线程尝试提前改善高阶形状。Proactive compaction 可以进一步主动整理，但会消耗 CPU、带宽和迁移开销。

THP 使用透明高阶内存
   Transparent Huge Pages 尝试减少页表项和 TLB miss。Fault 或 ``khugepaged`` collapse 可能触发高阶分配和 compaction，失败时通常可回退基础页。

HugeTLB 使用显式页池
   HugeTLB 具有预留、配额、挂载和不可换出等独立语义。页池不足时，映射或分配可以直接失败，不具备 THP 的普通页透明回退。

DMA 连续性必须由 DMA API 表达
   IOMMU 和 scatter-gather 可以让设备使用分散物理页；CMA 则通过主要容纳可迁移页的预留区域提供连续内存。普通高阶分配不能替代这些设备协议。

高阶需求必须设计降级
   预分配、分段缓冲、page array、scatterlist 和低阶 fallback 能减少运行时对连续物理内存的硬依赖。单次高阶失败不等于整机 OOM。

关键路径
--------

高阶分配：

::

   调用者提交 GFP 与 order
   → 确定 node、zone 和 migratetype
   → 检查 watermark
   → buddy 查找目标或更高 order
   → 命中时拆分并返回连续页块
   → 未命中时进入 reclaim / compaction
   → 重试成功或按调用者语义失败

Compaction：

::

   目标 zone 缺少连续块
   → 扫描可迁移 folio
   → 扫描空闲目标页
   → 隔离两类页面
   → 迁移内容、mapping、rmap 和页表
   → 释放旧物理位置
   → buddy 合并相邻空闲页
   → 形成更高 order 块
   → 重新尝试分配

THP fault：

::

   进程访问符合策略的匿名范围
   → 检查 VMA、对齐和 THP 策略
   → 尝试分配大 folio / PMD 大页
   → 必要时 reclaim 或 direct compaction
   → 成功时建立大页映射
   → 失败时按策略回退基础页

后台 collapse：

::

   khugepaged 扫描候选 VMA
   → 检查基础页与引用条件
   → 取得连续大页目标
   → 复制或迁移页面内容
   → 替换页表映射
   → 回收旧基础页
   → 成功形成 THP 或放弃本次候选

概念辨析
--------

* 容量不足与外部碎片：前者缺少页总量；后者缺少目标 order 的连续形状。
* Reclaim 与 compaction：Reclaim 释放页面；compaction 迁移页面并整理物理布局。
* Direct compaction 与 ``kcompactd``：前者由当前分配任务同步承担；后者在后台整理 node。
* THP 与 HugeTLB：THP 透明使用且通常可回退；HugeTLB 使用显式页池和独立配额。
* 物理连续与设备连续：物理连续表示 PFN 相邻；设备可以通过 IOMMU 或 scatter-gather 使用分散页。
* 高阶失败与 OOM：高阶请求可以只因形状失败；OOM 处理的是约束域内无法恢复的容量危机。

本章结论
--------

Compaction 通过迁移可移动页恢复物理内存的连续形状；高阶页、THP、HugeTLB、CMA 与 DMA 必须按各自的连续性、回退和生命周期语义分析。
