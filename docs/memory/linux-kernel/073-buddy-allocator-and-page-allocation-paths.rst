第073章：Buddy 分配器与页分配路径
=================================

核心知识点
----------

Buddy 管理物理连续页块
   ``alloc_pages(gfp, order)`` 请求 ``2^order`` 个物理连续页。Order 0 是单页，order 越高，对连续性、对齐和碎片状态越敏感。

空闲内存既有容量，也有形状
   Zone 中的总空闲页描述容量；``free_area[order]`` 描述不同阶数连续块的分布。两者必须分开理解。

高阶块可以逐级拆分
   目标 order 没有空闲块时，分配器从更高阶取块，每次拆成两个低一阶 buddy，直到得到目标大小。

释放时尝试向上合并
   页块释放后，若对应 buddy 同样空闲且状态兼容，两者合并成更高阶块，并继续递归检查新的伙伴。

PFN 决定 buddy 关系
   Buddy 地址关系由 PFN 和 order 计算。释放时必须使用正确起始页与 order，否则会破坏空闲链表和页元数据。

PCP 加速低阶页流动
   Per-CPU Pagesets 缓存常用低阶空闲页，使 order-0 分配和释放尽量在 CPU 本地完成，减少 zone 锁竞争。

PCP 与 Buddy 分工不同
   PCP 是低阶快速缓存；Buddy 才保存 zone 范围内完整的阶数结构。高阶请求通常直接依赖 buddy、watermark 和 compaction。

快路径先尝试现有空闲页
   分配器解析 GFP、order、节点和 zonelist，检查水位后，从 PCP 或 buddy 取得页面。快路径成功只说明当前约束下已有可交付页。

慢路径负责恢复可分配状态
   快路径失败后，可睡眠请求可能唤醒 ``kswapd``、执行 direct reclaim、compaction、重试或 OOM 处理。

Reclaim 与 Compaction 解决不同问题
   Reclaim 释放可回收页，增加容量；Compaction 迁移可移动页，聚合连续空闲块，改善高阶形状。

高阶失败不等于系统没有内存
   系统可能有大量 order-0 空闲页，却没有目标 order 的连续块。长期 pin、不可移动页和混合 pageblock 会限制合并与压缩。

关键路径
--------

低阶分配快路径：

::

   alloc_pages(gfp, order)
   → 解析 GFP、节点与 zonelist
   → 检查候选 zone 水位
   → 低阶请求检查当前 CPU PCP
   → PCP 命中则返回页面
   → PCP 不足时从 buddy 批量补充
   → 返回 struct page

Buddy 拆分：

::

   目标 order 没有空闲块
   → 向更高 order 查找
   → 摘下高阶空闲块
   → 拆成两个低一阶 buddy
   → 一个继续拆分
   → 另一个放回对应 free_area
   → 达到目标 order 后返回

Buddy 合并：

::

   上层释放完整页块
   → 确认引用和用途已经清理
   → 根据 PFN 与 order 找到 buddy
   → buddy 空闲且兼容
   → 从链表摘除并合并
   → 继续检查更高阶 buddy
   → 最终进入 free_area 或 PCP

页分配慢路径：

::

   快路径失败
   → 唤醒 kswapd
   → 允许时执行 direct reclaim
   → 高阶请求尝试 compaction
   → 重新检查 zonelist、watermark 与 free_area
   → 按 GFP 重试策略继续
   → 成功返回或最终失败

概念辨析
--------

空闲容量与连续形状
   总空闲页多不代表存在目标 order 的连续块。

PCP 与 Buddy
   PCP 加速 CPU 本地低阶页分配；Buddy 管理 zone 内各阶连续空闲块。

Reclaim 与 Compaction
   Reclaim 解决容量不足；Compaction 解决连续形状不足。

物理连续与虚拟连续
   Buddy 提供物理连续页；``vmalloc`` 可以提供虚拟连续、物理分散的内存。

快路径失败与最终失败
   快路径失败只表示要进入恢复流程；慢路径耗尽允许手段后才是最终失败。

高阶页与多个单页
   高阶请求要求页面物理相邻；多个 order-0 页只保证总数量。

本章结论
--------

Buddy allocator 用 order 保存空闲内存的连续形状：低阶请求依靠 PCP 和拆分快速完成，高阶请求则取决于水位、空闲块、回收与压缩能否共同满足。