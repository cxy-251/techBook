第083章：内存回收、LRU 列表与 kswapd
===================================

本章必须记住
------------

#. Memory reclaim 的目标是把当前占用的物理页转换成可重新分配的空闲页。
#. 回收器首先要判断页面内容能否丢弃、能否写回、能否换出、能否迁移，还是当前完全不可回收。
#. 干净文件缓存通常是成本最低的回收候选，因为后端文件保留了可重新读取的数据。
#. 脏文件页必须先完成或安排 writeback，回收成本会进入文件系统和存储 I/O。
#. 匿名页没有普通文件后端，需要 swap、zswap、远端内存或 NUMA demotion 等保存内容的目标才能释放当前物理页。
#. 没有可用 swap 或其它迁移目标时，匿名页回收空间会显著收缩。
#. Slab 中一部分内核缓存通过 shrinker 回收，是否可释放取决于对象引用和子系统生命周期。
#. ``SReclaimable`` 只表示某类 slab 设计上可以被 shrinker 回收，不保证当前所有对象都能立即释放。
#. 被 ``mlock``、长期 GUP pin、DMA、设备或不可回收内核对象持有的页面通常不能由普通 LRU 回收。
#. ``Unevictable`` 页不等于永远不可释放，而是当前被固定或受特殊语义保护，必须由持有者解除条件。
#. Page table、内核栈、内核文本和活跃对象内存通常不属于普通用户页 LRU 回收候选。
#. 回收以 node、zone、memcg 和 ``lruvec`` 等域组织，整机可回收不表示当前约束域内一定可回收。
#. Global reclaim 处理系统级压力；memcg reclaim 只在目标 cgroup 的内存域内寻找可释放对象。
#. Cpuset、NUMA policy、zone 和 GFP 约束会进一步缩小当前分配可使用的回收结果。
#. 传统 LRU 模型把页分成 file/anon 和 active/inactive 四类，分别表达后端类型和近似复用价值。
#. Active 并不表示绝对不能回收；压力下页面可以被降级到 inactive 后继续评估。
#. Inactive 只是优先扫描候选，页面仍可能因重新访问、锁定、dirty、引用或映射关系而被保留。
#. Linux 的 LRU 是工程近似，不会在每次内存访问时维护严格的全局最近使用顺序。
#. Referenced 位、refault 距离、workingset 统计和列表移动共同估计页面是否属于当前工作集。
#. 文件页被回收后很快再次 fault，形成 refault，说明回收可能伤害了活跃工作集。
#. Workingset 机制使用 refault 证据决定重新激活和调整 file/anon 回收平衡。
#. 现代内核可启用 Multi-Gen LRU（MGLRU），按访问代际管理候选；具体运行模型取决于配置和启动状态。
#. 启用 MGLRU 后，不能把所有运行时行为机械解释为传统 active/inactive 列表扫描，但“估计热度并优先回收冷页”的目标不变。
#. ``kswapd`` 是每个 NUMA node 的后台回收线程，负责在分配路径被迫停顿前补充空闲页。
#. Zone 空闲页低于 low watermark 时通常会唤醒 ``kswapd``。
#. ``kswapd`` 尝试把相关 zone 回收到 high watermark 附近，再进入睡眠。
#. Watermark 是页分配器的安全余量，不只是“系统剩余内存百分比”。
#. ``kswapd`` 后台回收能平滑压力，但不能保证在突发分配、慢存储或低可回收比例下及时补足页。
#. 分配器快速路径和后台回收仍无法满足请求时，当前分配者可能进入 direct reclaim。
#. Direct reclaim 在业务线程上下文中扫描页、调用 shrinker、等待 writeback 或执行 swap I/O，因此会直接形成尾延迟。
#. ``allocstall`` 增长说明分配路径进入同步回收，是业务感知内存压力的重要证据。
#. ``pgscan`` 表示扫描候选页，``pgsteal`` 表示成功回收页；扫描很多但回收很少说明效率低。
#. 应按 kswapd 与 direct 两类计数分别观察，后台扫描和前台停顿的业务含义不同。
#. File reclaim 与 anon reclaim 的比例受 swap 可用性、swappiness、工作集和目标内存域影响。
#. ``vm.swappiness`` 影响匿名页与文件页回收的相对成本评估，不是简单的“是否允许使用 swap”开关。
#. Swappiness 调整不能增加总内存，也不能修复 pinned pages、内核泄漏或后端 I/O 性能问题。
#. Swap-out 释放物理页，但把以后访问成本转化成 swap-in fault 和存储 I/O。
#. Swap thrashing 表示工作集持续换入换出，系统可能表现为高 I/O、低有效吞吐和严重延迟。
#. 干净文件页回收不需要写 I/O，但未来重新访问会产生缓存缺失和文件读取。
#. 脏文件页回收依赖 writeback，writeback 拥塞会降低 reclaim 效率并把压力传回分配者。
#. ``GFP_NOFS``、``GFP_NOIO`` 等上下文限制会减少 direct reclaim 可执行的动作，降低当前路径的恢复能力。
#. 高阶页分配还需要连续形状；reclaim 增加空闲总量，不能保证形成目标 order 的连续块。
#. Compaction 负责迁移页面和整理连续形状，与 reclaim 的容量目标不同。
#. 回收页后返回 buddy allocator，低阶页可以立即服务普通分配，高阶请求还需 buddy 合并或 compaction。
#. Memory pressure 不等于 OOM；只要回收能持续产生页，系统可以长期处于有压力但可推进状态。
#. OOM 也不要求 ``MemFree`` 归零，它取决于当前分配约束内是否还有可恢复内存。
#. ``MemAvailable`` 是启发式估计，不包含具体 GFP、node、zone、order 和 memcg 约束。
#. PSI memory 指标可以观察任务因内存回收、refault 和相关压力而停顿的时间比例。
#. PSI ``some`` 表示至少部分任务受阻，``full`` 表示所有可运行非 idle 任务都因该资源压力受阻，解释需结合系统类型。
#. ``/proc/meminfo`` 应同时观察 Cached、Dirty、AnonPages、Unevictable、Slab、SReclaimable 和 Swap。
#. ``/proc/vmstat`` 应在固定窗口计算 pgscan、pgsteal、allocstall、workingset、swap 和 writeback 计数增量。
#. 单个快照不能还原回收时间线；必须对齐业务延迟、kswapd CPU、direct reclaim、设备 I/O 和 memcg 事件。
#. 大量 page cache 被回收不一定是问题；只有频繁 refault、I/O 上升和业务延迟说明工作集被伤害。
#. 大量匿名页并不自动是泄漏；应结合进程增长、swap、生命周期和工作负载基线判断。
#. 高 slab 占用需要按 cache 和 shrinker 分析，不能直接把全部 Slab 当成不可回收内核泄漏。
#. 直接执行 ``drop_caches`` 会人为清除部分缓存并改变工作集，不适合作为日常压力修复方案。
#. 正确调优应先识别压力来自匿名工作集、文件缓存、脏页、slab、pin、memcg 还是访问局部性。
#. 最稳定的回收诊断顺序是：确定分配域 → 页面类型 → 可回收条件 → LRU/代际位置 → kswapd/direct reclaim → 实际回收效率。

必背路径
--------

后台回收：

::

   Zone 空闲页低于 low watermark
   → 唤醒 node 对应 kswapd
   → 建立 scan_control 与目标回收域
   → 扫描 file / anon LRU 或代际
   → 回收 clean file folio
   → 写回 dirty file folio
   → 换出可回收匿名页
   → 调用 shrinker 回收内核缓存
   → 空闲页恢复到 high watermark 附近
   → kswapd 睡眠

Direct reclaim：

::

   页分配快速路径失败
   → 后台回收未及时产生足够页
   → 当前 GFP 允许 direct reclaim
   → 分配者进入 reclaim
   → 扫描、写回、换出或 shrink slab
   → 成功时重试分配
   → 无进展时继续慢路径、失败或进入 OOM 判断

回收 clean file cache：

::

   选择 inactive file 候选
   → 确认 folio 未被重新访问
   → 确认 clean 且无阻止回收的引用
   → 从 address_space 索引移除
   → 解除 LRU 与映射关系
   → 释放物理页
   → 后续访问重新从文件读取

匿名页回收：

::

   选择冷匿名 folio
   → 确认存在 swap / demotion 目标
   → 分配并写入后端条目
   → 更新页表为非驻留状态
   → 解除当前物理页映射
   → 释放物理页
   → 后续访问触发 swap-in fault

诊断回收效率：

::

   固定 node、zone 或 memcg 域
   → 采样 pgscan 与 pgsteal 增量
   → 计算扫描和回收效率
   → 检查 allocstall 与 PSI memory
   → 检查 Dirty / Writeback / swap I/O
   → 检查 workingset refault
   → 判断容量、工作集抖动或不可回收比例

必须区分
--------

可回收与当前能立即释放
   页面类型可能允许回收，但 dirty、引用、锁、pin 和后端状态会阻止当前释放。

``kswapd`` 与 Direct reclaim
   前者后台恢复水位；后者由当前分配任务承担并直接影响业务延迟。

File reclaim 与 Anon reclaim
   文件页可从文件重读；匿名页需要 swap、demotion 或其它内容保存目标。

Reclaim 与 Compaction
   Reclaim 增加可用页总量；compaction 重新排列页以形成连续块。

传统 LRU 与 MGLRU
   前者按 active/inactive 近似热度；后者按代际组织，具体运行路径取决于内核配置。

扫描量与回收成果
   ``pgscan`` 是检查候选数量；``pgsteal`` 才是成功释放或回收的页数量。

一句话结论
----------

Memory reclaim 通过估计页面复用价值，在后台 ``kswapd`` 或前台 direct reclaim 中把文件缓存、匿名页和可收缩对象转换成空闲页，并把无法隐藏的成本表现为 I/O 与任务停顿。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 17，Page Cache, Writeback, Reclaim, Compaction, and OOM；
* AIBook 章节：Chapter 83，Memory Reclaim, LRU Lists, and kswapd；
* 源文件：``docs/LinuxK/Part_17_Page_Cache_Writeback_Reclaim_Compaction_and_OOM/Chapter_083_Memory_Reclaim_LRU_Lists_and_kswapd.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_17_Page_Cache_Writeback_Reclaim_Compaction_and_OOM/Chapter_083_Memory_Reclaim_LRU_Lists_and_kswapd.md>`_。