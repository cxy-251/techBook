第178章：内存压力、回收、Cache Miss 与 NUMA 影响
================================================

核心知识点
----------

内存性能不能只看剩余容量
   真实成本来自分配 Slowpath、Reclaim、Compaction、Fault、Writeback、Swap、CPU Cache/TLB 与 NUMA 远端访问。``MemAvailable`` 只是容量线索，不是延迟结论。

分配压力由 Watermark 驱动
   小页分配通常先走 Per-CPU Pageset 与 Buddy Fastpath。目标 Zone Watermark 不满足时会唤醒 ``kswapd``，Fastpath 继续失败则申请者可能进入 Direct Reclaim、Compaction 和 Retry。

后台回收与同步停顿不同
   ``kswapd`` 在后台恢复 Watermark；Direct Reclaim 发生在申请 Task 自己的路径中，会直接进入请求延迟。``allocstall``、扫描与回收计数是关键证据。

扫描量与回收量要共同解释
   ``pgscan_*`` 表示扫描候选页，``pgsteal_*`` 表示成功回收。大量扫描而回收很少，常说明活跃工作集、脏页、不可回收页、Pinned Page 或错误的回收范围。

容量、碎片和局部性是三类问题
   容量不足是工作集超过可用内存；碎片是有空闲页却缺少高阶连续块；局部性问题是页面存在但位于远端 Node 或 CPU Cache/TLB 之外。

Fault 不等于磁盘 I/O
   Minor Fault 可来自匿名页、COW、页表建立和 NUMA Hinting；Major Fault 通常需要从文件、Swap 或其它后端取页。Fault 数必须按请求量和冷/热阶段归一化。

工作集与 RSS 不相同
   RSS 描述当前驻留规模，不保证业务热页持续驻留。持续 Major Fault、Page Cache Refill 和 Reclaim 抖动，才说明工作集无法稳定保留。

CPU Cache、TLB 与 Page Cache 必须分开
   L1/L2/LLC Miss 和 TLB Miss 是微架构事件；Linux Page Cache 是文件页缓存。TLB Miss 可在页表有效时发生，Page Fault 则表示现有映射无法直接完成访问。

NUMA 性能取决于执行与页面位置
   Task 所在 CPU Node、页面所在 Node、设备 NUMA Node、Cpuset、Memory Policy 与自动 NUMA Balancing 共同决定访问距离。绑 CPU 不会自动迁移既有页面。

Memcg 可制造局部内存压力
   Cgroup ``memory.high``、``memory.max``、``memory.events`` 和 ``memory.pressure`` 可在宿主仍有空闲内存时触发回收、节流或 OOM，必须和全局 VM 证据分开。

关键路径
--------

分配 Slowpath：

::

   Task 申请 Page
   → Per-CPU Pageset / Buddy Fastpath
   → Zone Watermark 不满足
   → 唤醒 kswapd
   → Fastpath 失败
   → Direct Reclaim / Compaction / Retry
   → 分配成功或失败
   → 请求延迟或 OOM 风险上升

工作集 Miss：

::

   CPU 访问虚拟地址
   → 现有页表不能满足
   → Page Fault
   → 区分 Anonymous / File / COW / NUMA / Swap
   → Minor Fault 建立映射
      或 Major Fault 读取后端
   → 页面驻留
   → Task 恢复执行

NUMA 局部性：

::

   Worker 运行在 Node A
   → 页面由 First-touch 或 Policy 分配到 Node B
   → 发生远端访问
   → Cache/TLB/Memory Stall 与延迟增加
   → 检查 CPU Affinity、Memory Policy 和 Device Node
   → 重新对齐并复测

概念辨析
--------

* Memory Used 与 Memory Pressure：占用高不等于任务正在因内存等待。
* Global Reclaim 与 Memcg Reclaim：整机和 Cgroup 的作用域不同。
* Kswapd 与 Direct Reclaim：后台恢复和申请者同步停顿不同。
* Capacity 与 Fragmentation：缺少总页数和缺少连续页块不同。
* Minor Fault 与 Major Fault：前者通常无需慢后端，后者通常需要读取数据。
* TLB Miss 与 Page Fault：硬件地址翻译未命中和内核映射故障不同。
* CPU Cache 与 Page Cache：硬件 Cacheline 和内核文件页缓存不同。
* CPU Affinity 与 Memory Locality：固定任务位置不会自动移动页面。

本章结论
--------

内存性能调查必须同时回答分配是否被回收拖住、工作集是否持续缺页、CPU 是否等待内存层级，以及页面是否位于正确的 NUMA Node。