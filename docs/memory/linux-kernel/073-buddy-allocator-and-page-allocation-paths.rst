第073章：Buddy 分配器与页分配路径
=================================

本章必须记住
------------

#. Buddy allocator 是 Linux 分配物理连续页块的核心页级分配器。
#. 调用者使用 ``alloc_pages(gfp, order)`` 请求 ``2^order`` 个物理连续页，成功时返回首个页面的 ``struct page *``。
#. Order 0 是单页；order 越高，连续页数量、对齐要求和碎片敏感度越高。
#. Buddy 管理的是物理连续性，不保证返回一段已经建立的虚拟连续用户映射。
#. 每个 zone 使用 ``free_area[order]`` 记录不同阶数的空闲块，并按 migratetype 进一步组织链表。
#. 空闲页总数表示容量，``free_area`` 的 order 分布表示连续块形状，二者不能互相替代。
#. 分配目标 order 没有空闲块时，分配器可以从更高 order 取块并逐级拆分。
#. 高阶块每拆分一次会形成两个低一阶 buddy：一个继续拆分或返回，另一个放回相应空闲链表。
#. 释放页块时，分配器检查对应 buddy 是否空闲、order 和迁移状态是否允许合并。
#. 两个兼容 buddy 合并成更高一阶块，并可以继续向上递归合并。
#. Buddy 地址关系以 PFN 和 order 计算，概念上可用当前块 PFN 与 ``1 << order`` 的位关系定位伙伴。
#. 页面只有在所有上层引用、映射、I/O 和对象用途结束后，才能交还页分配器。
#. ``__free_pages(page, order)`` 的 order 必须与分配和拆分协议匹配，错误 order 会破坏分配器元数据。
#. 释放复合页或高阶块不能把任意 tail page 当成独立块起点。
#. Per-CPU Pagesets（PCP）缓存高频低阶空闲页，减少每次分配都争用 zone 全局锁。
#. 常见 order-0 分配优先尝试当前 CPU 的 PCP，本地命中时路径短且缓存局部性较好。
#. PCP 不足时，分配器从 zone buddy 批量补充；PCP 过多时也会批量归还 buddy。
#. PCP 保存空闲页的位置，不表示页面内容可以跨对象直接复用；清零和初始化仍由上层协议负责。
#. CPU offline、内存隔离和部分回收操作需要 drain PCP，确保页面回到可全局观察的 buddy 状态。
#. 高阶请求通常更依赖 buddy 全局空闲块、watermark、migratetype 和 compaction，不能只靠单页 PCP 满足。
#. 页分配主路径先解析 GFP、order、NUMA policy 和 zonelist，再检查 zone 水位并尝试取页。
#. ``get_page_from_freelist()`` 一类路径负责遍历候选 zone，并从 PCP 或 buddy 尝试满足请求。
#. 快路径成功表示当前约束下已有可交付页，不表示系统没有内存压力或碎片。
#. 快路径失败后，可睡眠请求进入 ``__alloc_pages_slowpath()`` 一类慢路径。
#. 慢路径可能唤醒 ``kswapd``、执行 direct reclaim、direct compaction、节点回收、重试或 OOM 处理。
#. Reclaim 解决可回收页面占用导致的容量不足；compaction 解决空闲页分散导致的连续形状不足。
#. 回收释放很多 order-0 页，不保证自动形成高阶连续块；形成高阶块还需要物理邻接和合并或迁移。
#. Compaction 通过迁移 movable pages，把空闲页聚合成更大的连续块。
#. 不可移动内核页、长期 pin 页面、设备页和混合 pageblock 会限制 compaction 效果。
#. ``GFP_ATOMIC`` 等非睡眠请求通常不能进入普通 direct reclaim，慢路径能力明显受限。
#. ``__GFP_NORETRY``、``__GFP_RETRY_MAYFAIL`` 和 order 大小会影响慢路径重试强度。
#. 某些允许的分配可能进入 OOM killer 路径，但 OOM 是约束内无法恢复容量时的最后手段，不解决纯连续碎片。
#. 高阶分配在系统总 free memory 很高时仍可能失败，因为目标 zone 没有足够大的连续空闲块。
#. 对可拆分需求，应优先申请多个低阶页并使用 scatter-gather、``vmalloc`` 或上层分段结构，减少高阶依赖。
#. DMA 物理连续需求应通过 DMA API、IOMMU、CMA 或专用内存池评估，不能只盲目提高 order。
#. CMA 预留可移动区域服务部分大块连续分配，其策略和普通 buddy 空闲块不完全相同。
#. 预分配、mempool 和对象缓存可以把关键路径的分配风险转移到可睡眠初始化阶段。
#. ``/proc/buddyinfo`` 是 zone 各 order 空闲块数量的瞬时投影，适合判断当前连续形状。
#. ``/proc/zoneinfo`` 提供水位和 reserve，必须与 buddyinfo、GFP、order 和 node 一起解释。
#. 页分配 tracepoint、page owner 和失败日志可以说明谁请求了页面以及请求在哪个路径失败。
#. 分配失败处理必须保持原始错误语义并回滚已取得资源，不能假设页分配“理论上总会成功”。
#. 页分配性能问题要区分快路径命中率、PCP refill、zone 锁竞争、回收时间、压缩时间和调度等待。
#. 读取分配器源码时，应按“约束解析 → zonelist → watermark → PCP/buddy → slow path → 返回或失败”顺序追踪。

必背路径
--------

低阶分配快路径：

::

   alloc_pages(gfp, order)
   → 解析 GFP、节点和 zonelist
   → 检查候选 zone 水位
   → 低阶请求先查当前 CPU PCP
   → PCP 命中则返回 struct page
   → PCP 不足时从 buddy 批量 refill
   → 返回目标页面

Buddy 拆分：

::

   目标 order 无空闲块
   → 向更高 order 查找
   → 摘下一个高阶空闲块
   → 拆成两个低一阶 buddy
   → 一个继续拆分
   → 另一个放回 free_area
   → 达到目标 order 后返回

Buddy 合并：

::

   上层释放完整页块
   → 检查引用和页面状态已经清理
   → 根据 PFN 和 order 找 buddy
   → buddy 空闲且兼容时从链表摘除
   → 合并成更高 order
   → 继续检查新的 buddy
   → 最终放入对应 free_area 或 PCP

页分配慢路径：

::

   快路径和水位检查失败
   → 唤醒 kswapd
   → 允许时执行 direct reclaim
   → 高阶请求尝试 direct compaction
   → 重新遍历 zonelist 和 watermarks
   → 按 GFP 重试策略继续或停止
   → 必要时进入允许的 OOM 处理
   → 成功返回页面或 NULL

必须区分
--------

空闲容量与连续形状
   总空闲页多不代表目标 order 有可用连续块。

PCP 与 Buddy
   PCP 加速 CPU 本地低阶页流动；buddy 管理 zone 范围内各阶连续空闲块。

Reclaim 与 Compaction
   Reclaim 释放可回收页解决容量；compaction 迁移页面解决连续形状。

物理连续与虚拟连续
   Buddy 返回物理连续页；``vmalloc`` 可以提供虚拟连续而物理分散的内存。

快路径失败与最终失败
   快路径未命中只表示要进入慢路径；慢路径耗尽允许手段后才形成最终分配失败。

高阶请求与多个单页
   高阶请求要求连续物理块；多个 order-0 页只保证总容量，不保证物理相邻。

一句话结论
----------

Buddy allocator 用 order 保存空闲内存的形状：低阶请求靠 PCP 和拆分快速满足，高阶请求则取决于 zone 水位、连续块、回收与压缩能否共同成功。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 15，Physical Memory, Zones, NUMA, and Page Allocator；
* AIBook 章节：Chapter 73，Buddy Allocator and Page Allocation Paths；
* 源文件：``docs/LinuxK/Part_15_Physical_Memory_Zones_NUMA_and_Page_Allocator/Chapter_073_Buddy_Allocator_and_Page_Allocation_Paths.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_15_Physical_Memory_Zones_NUMA_and_Page_Allocator/Chapter_073_Buddy_Allocator_and_Page_Allocation_Paths.md>`_。