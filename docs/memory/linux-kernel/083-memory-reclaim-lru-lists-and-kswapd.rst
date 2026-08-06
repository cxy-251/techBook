第083章：内存回收、LRU 列表与 kswapd
===================================

核心知识点
----------

Reclaim 把占用页转换为空闲页
   内存回收的目标不是减少虚拟地址，而是让当前物理页重新进入可分配状态。页面能否回收取决于内容是否可丢弃、写回、换出、迁移或重建。

页面类型决定回收成本
   Clean file folio 可以从 Page Cache 删除并重新读取；dirty file folio 需要 writeback；匿名页需要 swap、demotion 或其它内容保存目标。

部分内核缓存通过 shrinker 回收
   Dentry、inode 和其它 slab 对象能否释放取决于引用与子系统生命周期。``SReclaimable`` 表示存在回收设计，不表示所有对象当前都能立即释放。

固定页面不属于普通回收候选
   ``mlock``、长期 GUP pin、DMA、设备页和仍被活跃内核对象持有的页面，通常要等持有者结束语义后才能释放。

回收按资源域组织
   ``lruvec`` 把 node 与 memcg 的页面集合联系起来。Global reclaim、memcg reclaim、zone、cpuset 和 GFP 约束可能形成不同的候选范围。

LRU 是复用价值的近似模型
   传统模型把 file/anon 与 active/inactive 组合成四类列表。Active 页面仍可降级；inactive 页面只是优先候选，仍需检查引用、dirty、锁和映射状态。

Workingset 用 refault 修正判断
   文件页被回收后很快再次访问，说明它可能属于工作集。Refault 距离和访问证据用于重新激活页面并调整 file/anon 回收平衡。

MGLRU 按代际估计冷热
   启用 Multi-Gen LRU 后，页面按访问代际组织，不再完全遵循传统四列表扫描。稳定目标仍是保护热页并优先回收冷页。

``kswapd`` 负责后台恢复水位
   每个 NUMA node 通常有后台回收线程。Zone 低于 low watermark 时唤醒，回收到 high watermark 附近后停止主动扫描。

Direct reclaim 由分配者承担
   快路径和后台回收无法及时满足请求时，允许回收的分配任务会同步扫描 LRU、调用 shrinker、等待 writeback 或执行 swap I/O，直接形成业务尾延迟。

扫描量不等于回收成果
   ``pgscan`` 表示检查候选数量，``pgsteal`` 表示成功回收数量。扫描很多而释放很少，说明工作集活跃、页面脏、被固定或目标域缺少可回收对象。

``allocstall`` 与 PSI 表示业务受压
   ``allocstall`` 增长说明分配路径进入同步回收。PSI memory 描述任务因回收、refault 和相关压力停顿的时间比例。

Swap 扩展匿名页回收空间
   Swap-out 释放当前物理页，把成本转移到未来 swap-in fault。``vm.swappiness`` 调整 anon/file 成本权衡，不是简单的 swap 开关。

Reclaim 与 compaction 解决不同问题
   Reclaim 增加空闲页总量；compaction 迁移页面形成连续块。高阶请求即使回收出许多单页，也仍可能因物理形状失败。

关键路径
--------

后台回收：

::

   Zone 低于 low watermark
   → 唤醒 node 对应 kswapd
   → 建立目标回收域与 scan_control
   → 扫描 file / anon LRU 或代际
   → 丢弃 clean file folio
   → 写回 dirty file folio
   → 换出可回收匿名页
   → 调用 shrinker
   → 空闲页恢复到 high 附近
   → kswapd 睡眠

Direct reclaim：

::

   页分配快速路径失败
   → 后台回收未及时补足页
   → 当前 GFP 允许同步回收
   → 分配任务进入 reclaim
   → 扫描、写回、换出或收缩 slab
   → 成功时重试分配
   → 无进展时继续慢路径、失败或进入 OOM 判断

Clean file cache 回收：

::

   选择冷文件 folio
   → 确认未重新访问
   → 确认 clean 且无阻止回收的引用
   → 从 address_space 索引移除
   → 解除 LRU 与映射关系
   → 释放物理页
   → 后续访问重新读取文件

匿名页回收：

::

   选择冷匿名 folio
   → 确认存在 swap 或 demotion 目标
   → 保存页面内容
   → 更新页表为非驻留状态
   → 解除当前物理页映射
   → 释放物理页
   → 后续访问触发换入 fault

概念辨析
--------

* 可回收与立即可释放：页面类型允许回收，不表示当前引用、dirty、锁、pin 和后端状态已经满足释放条件。
* ``kswapd`` 与 direct reclaim：前者后台恢复水位；后者由当前分配任务承担，直接影响业务延迟。
* File reclaim 与 anon reclaim：文件页可从文件重读；匿名页需要 swap、demotion 或其它内容保存目标。
* 传统 LRU 与 MGLRU：前者使用 active/inactive 近似热度；后者使用访问代际，运行模式取决于配置。
* ``pgscan`` 与 ``pgsteal``：前者是扫描工作量；后者才是成功回收成果。
* Reclaim 与 compaction：Reclaim 解决容量；compaction 解决连续形状。

本章结论
--------

Memory reclaim 根据页面类型和复用价值，在后台 ``kswapd`` 或前台 direct reclaim 中把缓存、匿名页和可收缩对象转换为空闲页，无法隐藏的成本最终表现为 I/O 与任务停顿。
