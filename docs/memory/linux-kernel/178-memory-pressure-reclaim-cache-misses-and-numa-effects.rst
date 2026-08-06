第178章：内存压力、回收、Cache Miss 与 NUMA 影响
================================================

本章必须记住
------------

#. 内存性能问题不能只看“剩余内存”，必须同时看分配等待、回收、缺页、Cache/TLB、NUMA 和 I/O。
#. 内存压力最直接的用户可见结果是 Allocation Latency 和任务因回收、整理或 Fault 停顿。
#. 正常小页分配可从 Per-CPU Pageset 或 Buddy 快速完成；资源不足时会进入 Slowpath。
#. Zone Watermark 决定何时唤醒 ``kswapd``、何时让申请方进入 Direct Reclaim。
#. ``kswapd`` 是后台回收；Direct Reclaim 在申请 Task 自己的路径中执行并直接增加请求延迟。
#. ``allocstall`` 增长说明分配者进入同步回收或等待分配进展，是重要的延迟信号。
#. ``pgscan_*`` 表示扫描候选页，``pgsteal_*`` 表示成功回收页；二者比例反映回收效率线索。
#. 大量扫描而回收很少，常说明活跃工作集、脏页、不可回收页、Mlock、Pinned Page 或不合适的回收目标。
#. Memory PSI 表示任务因内存资源压力失去运行进展的时间，不是“内存使用百分比”。
#. ``some`` 表示至少部分任务受影响，``full`` 表示所有非 Idle 任务同时受阻，精确口径按 PSI 文档解释。
#. 还有大量 Page Cache 不代表没有内存压力；当前请求可能受目标 Node、Zone、Cgroup 或高阶页约束。
#. ``MemAvailable`` 低不自动表示业务已受影响；要看回收、Fault、PSI 和分配等待。
#. 内存容量问题、碎片问题和局部性问题必须分开。
#. 容量不足表示工作集与可用物理内存不匹配。
#. 碎片问题表示总空闲页存在，但缺少满足 Order 或连续性要求的页块。
#. 局部性问题表示页面存在，却位于远端 NUMA Node 或 CPU Cache/TLB 外层。
#. Compaction 试图把分散空闲页整理为连续物理页，服务 THP、DMA 或高阶分配。
#. ``compact_stall`` 表示申请方因 Compaction 停顿，``compact_fail``/``compact_success`` 说明整理结果。
#. 高阶分配失败不等于整机无空闲内存，可能只是没有合适连续块。
#. THP 可减少 TLB 压力，也可能引入 Fault-time Allocation、Compaction、Split 和 Reclaim 成本。
#. THP 是否有利必须按目标工作集、Fault 分布、延迟和内存碎片测量。
#. Page Fault 是虚拟地址访问需要内核处理的事件，不等于每次都进行磁盘 I/O。
#. Minor Fault 通常不需要从存储读取数据，但仍可涉及页表、匿名页、COW、NUMA Hinting 或映射建立。
#. Major Fault 通常需要从文件、Swap 或其它后端获取页面，成本通常更高。
#. Fault 数量必须按请求量和时间窗口归一化，冷启动一次性 Fault 与持续 Working-set Miss 含义不同。
#. RSS 只描述当前驻留规模，不说明驻留的是否正是业务热页。
#. 工作集被挤出后，RSS 可保持相近，而业务仍持续发生 Major Fault 和 Page Cache 抖动。
#. 文件映射工作集 Miss 常与存储读取、Page Cache Refill 和 Reclaim 同时出现。
#. 匿名内存压力可能表现为 Swap-out/Swap-in、Reclaim、OOM 或 Cgroup Memory Pressure。
#. 禁用或减少 Swap 不会增加物理内存，也不会修复内存泄漏。
#. Swap 可为冷匿名页腾出空间，也可能把 Latency 转换为后续 Swap-in I/O。
#. Cgroup Memory Limit 可在宿主仍有空闲内存时触发 Memcg Reclaim、Throttle 或 OOM。
#. 调查容器内存必须读取目标 Cgroup 的 ``memory.current``、``memory.events``、``memory.stat``、``memory.pressure`` 和限制。
#. ``memory.high`` 主要施加回收与节流压力，``memory.max`` 是硬上限；两者行为不同。
#. Global Reclaim 与 Memcg Reclaim 可同时存在，必须确认统计作用域。
#. Dirty Page 与 Writeback 会降低可立即回收页比例，并把内存压力传导到块设备。
#. 内存问题经常通过 I/O 表现：Major Fault、Swap、Writeback 和 Reclaim 都可能等待设备。
#. Cache Miss 是 CPU 微架构事件，不等于内核 Page Cache Miss。
#. CPU Cache 指 L1/L2/LLC 等硬件缓存；Page Cache 是内核文件数据缓存。
#. LLC Miss 可能进入本地 DRAM、远端 NUMA Node 或其它内存层级，成本取决于拓扑。
#. Cache Miss 绝对数会随工作量增长，应优先比较 Miss/Instruction、Miss/Request 和 Stall/Request。
#. 通用 PMU 事件名称可能映射到不同硬件事件，必须按 CPU 型号确认。
#. TLB Miss 表示地址翻译缓存未命中，可能触发硬件 Page Walk，不等于 Linux Page Fault。
#. TLB Miss 可在页表映射有效时发生，Page Fault 则表示当前访问无法由现有有效映射直接完成。
#. 大页可能降低 TLB Miss，但会增加连续内存、Compaction 和内部碎片权衡。
#. Memory Stall 高而 Reclaim/Fault 平稳，问题可能主要在 CPU Cache、TLB、带宽或 NUMA，而不是 VM 容量。
#. Reclaim 高而 PMU Cache Miss 平稳，问题仍可能来自分配停顿和后台回收。
#. NUMA 系统的物理内存按 Node 组织，每个 Node 具有自己的 Zone、Watermark 和后台线程。
#. Task 运行 CPU 所属 Node 与页面所在 Node 不一致时，会产生远端内存访问。
#. 远端访问延迟和带宽通常劣于本地访问，精确差异依平台拓扑。
#. First-touch 常决定匿名页面初始分配位置，初始化线程位置会影响后续 Locality。
#. CPU Affinity 只固定执行位置，不自动迁移已有页面。
#. Memory Policy、Cpuset、Mempolicy、NUMA Balancing 和 Page Migration 共同决定页面位置。
#. Automatic NUMA Balancing 可通过 Hinting Fault 和迁移改善局部性，也会增加 Fault、扫描和迁移成本。
#. ``numastat``、Per-node Meminfo、Task NUMA 统计和 PMU Remote Access 事件是常见证据。
#. Node 总空闲充足不表示目标 Task 能在本地 Node 获得所需页面；局部 Node 可先进入回收。
#. 盲目 ``numactl --interleave`` 可减少单 Node 压力，也可能增加所有访问的平均距离。
#. 绑 CPU 与绑内存必须按同一 Worker、Queue、Device 和 NUMA Node 设计。
#. NIC、NVMe、GPU 等 PCIe 设备也有 NUMA 归属，DMA Queue 与 Worker 位置会影响数据路径。
#. 内存带宽饱和可在 CPU 利用率未满时限制性能，需使用平台 PMU 或内存控制器证据。
#. Cacheline Sharing 和 False Sharing 会产生 Coherence Traffic，表现为高 Cycles、Cacheline Bounce 和扩展性下降。
#. False Sharing 是不同变量落在同一 Cacheline 的并发写竞争，不是内核锁本身。
#. Per-CPU 数据可减少共享写，但会增加聚合、内存占用和 CPU Hotplug 处理复杂度。
#. 内核 Slab 增长要区分有效对象增长、Cache、延迟释放、Leak 和 Debug 配置。
#. ``slabtop``/``/proc/slabinfo`` 是对象缓存证据，不能单独证明 Leak。
#. Leak 调查需要对象分配/释放路径、增长速率、引用和工作负载关联。
#. Page Cache 大通常是正常资源利用，不能把 ``Cached`` 直接视为泄漏。
#. ``drop_caches`` 会破坏系统 Cache 基线，不应作为常规生产优化或诊断第一步。
#. 回收策略调优前必须先确认压力来自工作集、脏页、Memcg、碎片、NUMA 还是内核对象。
#. 调低 Swappiness、调整 Watermark 或 Compaction 只会改变策略，不会创造容量。
#. 扩容内存可能缓解容量压力，不能自动修复远端访问、False Sharing 或错误绑核。
#. 调整 NUMA 策略后必须验证 Local/Remote Access、Fault、Migration、Bandwidth 和业务 p99。
#. 调整 THP 后必须验证 TLB、Compaction、Fault Latency、RSS 和内部碎片。
#. 内存优化结果要同时看 Allocation Stall、Fault/Request、PSI、I/O、PMU 和尾延迟。
#. 单一 ``free``、RSS 或 Cache Miss 指标不足以解释完整内存性能问题。
#. 稳定调查顺序是：Scope/Limit → Watermark/Reclaim → Fault/Working Set → Writeback/Swap → PMU Cache/TLB → NUMA/Topology。

必背路径
--------

分配压力：

::

   Task 申请 Page
   → Per-CPU Pageset / Buddy Fastpath
   → 目标 Zone Watermark 不满足
   → 唤醒 kswapd
   → Fastpath 仍失败
   → __alloc_pages_slowpath
   → Direct Reclaim / Compaction / Retry
   → 分配成功或失败
   → Task 请求延迟上升

工作集 Miss：

::

   CPU 访问 Virtual Address
   → Page Table 无法直接满足
   → Page Fault Entry
   → handle_mm_fault 类路径
   → 区分 Anonymous / File / COW / NUMA / Swap
   → Minor Fault 建立映射
      或
   → Major Fault 读取后端数据
   → 页面重新驻留
   → Task 恢复执行

NUMA 局部性：

::

   Worker 固定或运行在 CPU Node A
   → 页面由 First-touch / Policy 分配到 Node B
   → CPU 访问远端内存
   → 更高 Latency / 更低 Bandwidth
   → Cache/TLB/Remote PMU 证据增加
   → 检查 CPU Affinity、Memory Policy 与 Device Node
   → 重新对齐后复测

内存性能调查：

::

   固定目标进程/Cgroup 与延迟窗口
   → 读取 Limit、memory.events、PSI
   → 计算 vmstat Reclaim/Compaction 增量
   → 计算 Minor/Major Fault 每请求
   → 对齐 Dirty、Writeback、Swap 与设备 I/O
   → 采集 Cache/TLB/Memory Stall
   → 检查 Per-node 页面与远端访问
   → 只修改一个容量、局部性或策略变量

必须区分
--------

* Memory Used 与 Memory Pressure：占用规模不等于任务正在因内存等待。
* Global Reclaim 与 Memcg Reclaim：整机和 Cgroup 的回收作用域不同。
* Kswapd 与 Direct Reclaim：后台回收和申请者同步停顿不同。
* Capacity 与 Fragmentation：缺少总页数和缺少连续页块不同。
* Minor Fault 与 Major Fault：前者通常无需存储读取，后者通常需要慢后端。
* TLB Miss 与 Page Fault：硬件翻译缓存未命中和内核映射故障不同。
* CPU Cache 与 Page Cache：硬件 Cacheline 和内核文件页缓存不同。
* Cache Miss 与 Reclaim：微架构等待和内核页面管理路径不同。
* RSS 与 Working Set：当前驻留规模不表示热数据一直驻留。
* CPU Affinity 与 Memory Locality：固定 Task 位置不会自动移动页面。

一句话结论
----------

内存性能调查必须同时回答“分配是否被回收拖住、工作集是否持续缺页、CPU 是否等待内存层级、页面是否位于正确 NUMA Node”。

来源
----

* 教材：AIBook Linux Kernel
* Part：Part 36 — Kernel Performance Engineering for CPU, Memory, I/O, Network, and Lock Contention
* 章节：Chapter 178 — Memory Pressure, Reclaim, Cache Misses, and NUMA Effects
* 源文件：``docs/LinuxK/Part_36_Kernel_Performance_Engineering_for_CPU_Memory_IO_Network_and_Lock_Contention/Chapter_178_Memory_Pressure_Reclaim_Cache_Misses_NUMA_Effects.md``
* 固定版本：`18386764582829f2b807b7b0947785eb77b50446 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_36_Kernel_Performance_Engineering_for_CPU_Memory_IO_Network_and_Lock_Contention/Chapter_178_Memory_Pressure_Reclaim_Cache_Misses_NUMA_Effects.md>`_
