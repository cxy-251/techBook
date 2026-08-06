第075章：诊断物理内存碎片与压力
================================

核心知识点
----------

分配失败有三类根因
   必须区分容量不足、连续形状不足，以及 node、zone、GFP、cpuset 或上下文约束内没有可用页面。

Order 描述连续物理页需求
   Order-n 请求需要 ``2^n`` 个物理连续页，连续字节数为 ``PAGE_SIZE << order``。页大小不同，实际容量必须重新计算。

``buddyinfo`` 描述空闲形状
   ``/proc/buddyinfo`` 按 node、zone 和 order 展示空闲块数量。低阶块多只能说明小页充足，不能证明存在目标高阶连续块。

``zoneinfo`` 描述水位与保留约束
   ``/proc/zoneinfo`` 给出 free、min、low、high、protection 和 zone 统计。它回答当前 zone 是否允许把空闲页交付给请求。

容量与形状必须联合判断
   Zone 接近最低水位且各阶都少，通常是容量压力；低阶块很多而目标高阶为空，通常是外部碎片；两种状态也可能叠加。

全局空闲不能代表局部可用
   其它 node 或 zone 的页面可能不满足 DMA、cpuset、mempolicy、watermark 或当前执行上下文。

GFP 决定恢复手段
   ``GFP_KERNEL`` 可以睡眠和回收；``GFP_ATOMIC``、``GFP_NOWAIT``、``GFP_NOIO``、``GFP_NOFS`` 会不同程度限制 direct reclaim、I/O、文件系统或重试。

分配失败日志必须还原请求
   Order、GFP mask、nodemask、CPU、PID 和调用栈共同说明谁在什么约束下请求了多大的连续内存。

Reclaim 增加容量
   回收释放页缓存或匿名页，解决可用页数量不足；它不保证新释放页面物理相邻。

Compaction 改善连续形状
   压缩迁移可移动页面，把分散空闲页聚合成高阶块。长期 pin、不可移动 slab、页表页和设备页会阻断迁移。

高阶失败不等于 OOM
   高阶请求可以因碎片失败，而普通 order-0 分配仍正常。OOM 主要表示约束范围内连基础容量也无法恢复。

累计计数必须看时间窗口增量
   ``compact_*``、``pgscan_*``、``pgsteal_*``、``allocstall`` 等 vmstat 指标只有在固定时间窗口内比较增量，才能说明当前压力趋势。

修复应优先减少高阶依赖
   降低 order、预分配、使用 mempool、允许 scatter-gather、缩短 pin 生命周期，通常比单纯提高回收或压缩强度更可靠。

关键路径
--------

读取一次分配失败：

::

   保存完整 allocation failure 日志与调用栈
   → 提取 order、GFP mask、nodemask、CPU 和 PID
   → 按 PAGE_SIZE 计算连续字节需求
   → 解码睡眠、回收、I/O、FS、zone 和迁移约束
   → 定位调用者对象与降级路径
   → 对齐同一时刻的 zoneinfo、buddyinfo 和 vmstat

判断容量还是碎片：

::

   固定目标 node 与 zone
   → 查看 zoneinfo 的 free 与 min / low / high
   → 查看 buddyinfo 的目标 order 和更高 order
   → 水位低且各 order 都少：容量压力
   → 低 order 多而高 order 空：外部碎片
   → 两者同时异常：容量与碎片叠加
   → 再判断 GFP 是否允许回收与压缩

Compaction 恢复：

::

   高阶请求找不到连续块
   → 识别可移动页与空闲页
   → 迁移 movable pages
   → 聚合相邻空闲页
   → buddy 合并成更高 order
   → 重新检查水位和分配
   → 被 pin 或不可移动页阻断时失败

建立持续压力证据：

::

   固定采样时间窗口
   → 记录 reclaim 与 compaction 计数增量
   → 观察 kswapd、kcompactd 和 direct reclaim
   → 记录 swap、OOM 与 allocation stall
   → 对照业务延迟和失败时间
   → 区分瞬时尖峰与长期不可恢复压力

概念辨析
--------

容量不足与形状不足
   容量不足缺少总页数；形状不足缺少目标 order 的连续块。

``buddyinfo`` 与 ``zoneinfo``
   前者展示各阶空闲形状；后者展示水位、reserve 和 zone 压力。

Reclaim 与 Compaction
   Reclaim 释放页面增加容量；Compaction 迁移页面形成连续空间。

高阶失败与系统 OOM
   高阶分配可以单独因碎片失败；OOM 表示更广泛的可用容量恢复失败。

全局空闲与约束内可用
   页面只有位于允许的 node、zone，并满足水位和上下文要求时，才属于当前请求的可用资源。

日志抑制与问题修复
   ``__GFP_NOWARN`` 只减少日志，不改变碎片、压力或调用者恢复能力。

本章结论
--------

物理内存故障诊断必须先还原请求约束，再用 zone 水位判断容量、用 buddy order 判断连续形状，并证明回收与压缩为何能够或无法恢复。