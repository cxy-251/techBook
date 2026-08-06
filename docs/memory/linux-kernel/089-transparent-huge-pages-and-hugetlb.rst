第089章：透明大页与 HugeTLB
===========================

本章必须记住
------------

#. 大页的主要收益是让一个页表项和一个 TLB 条目覆盖更大的虚拟地址范围，减少页表层级访问和 TLB miss。
#. 常见 4 KiB 基础页与 2 MiB PMD 大页只是典型组合，实际页大小由架构、配置和支持的 huge page size 决定。
#. 大页收益取决于工作集大小和访问局部性；稀疏触碰会放大物理占用、清零和复制成本。
#. Transparent Huge Pages（THP）让普通匿名内存、shmem 或部分文件映射在策略允许时自动使用较大页面。
#. HugeTLB 把大页作为显式资源池管理，应用通过 hugetlbfs、``MAP_HUGETLB`` 或相关共享内存接口使用。
#. THP 与 HugeTLB 都使用大粒度翻译，但资源来源、失败语义、回收方式和用户控制完全不同。
#. THP 通常从普通页分配器取得页面；失败时多数路径可以回退到基础页，功能继续但翻译收益下降。
#. HugeTLB 依赖专用 huge page pool、reservation 和 quota；没有可用页或 reservation 时，映射或 fault 可能失败。
#. THP 可以在 fault 时直接分配大页，也可以由 ``khugepaged`` 把已存在的基础页 collapse 成大页。
#. Fault-time THP 需要满足 VMA 允许、地址对齐、页大小、NUMA policy、内存策略和物理页可用性。
#. ``khugepaged`` 只会合并满足条件的范围；页被 pin、不可迁移、特殊映射或内容状态不合适时会跳过或失败。
#. Multi-size THP（mTHP）允许部分内核和架构使用介于基础页与传统 PMD 大页之间的尺寸，具体支持具有版本与架构差异。
#. 不能把 THP 固定理解为 2 MiB PMD 映射；应读取目标系统实际暴露的 size 与统计。
#. ``/sys/kernel/mm/transparent_hugepage/`` 提供全局策略、defrag 和各尺寸控制，实际文件布局随版本变化。
#. ``always``、``madvise``、``never`` 表达默认尝试策略，不等于某个进程一定已获得或完全没有大页。
#. ``MADV_HUGEPAGE`` 表示一段 VMA 适合尝试 THP；``MADV_NOHUGEPAGE`` 表示不希望普通 THP 策略覆盖该范围。
#. 进程级 THP 禁用和继承语义可通过 ``prctl`` 等接口控制，排查时要同时读取全局、进程和 VMA 策略。
#. THP fault 为了取得连续页面可能触发 reclaim 或 compaction，是否同步等待取决于 defrag 策略和调用路径。
#. 同步 compaction 会把大页收益的成本集中到首次 fault 或业务请求中，可能形成尾延迟尖刺。
#. 后台 ``kcompactd`` 和 ``khugepaged`` 可以把部分成本移出前台路径，但仍消耗 CPU、内存带宽和迁移资源。
#. THP collapse 需要把一组基础页内容和映射关系合并，涉及页锁、页表更新、rmap 和 TLB 失效。
#. THP split 把大页映射或大 folio 拆成更细粒度对象，可能由 COW、回收、迁移、mprotect、unmap 或内存压力触发。
#. 拆分 PMD 映射和拆分底层 compound folio 是不同层次，具体路径可能只先拆页表映射。
#. 大页被 split 后，虚拟地址语义不一定变化，但页表数量、TLB 覆盖和管理粒度会改变。
#. Fork 后 THP 写入可能复制整张大页、拆分后复制基础页或使用版本相关优化，单次 COW 成本可能很高。
#. 大页减少页表页数量，却可能增加内部碎片、清零时间、COW 放大、迁移成本和 reclaim 粒度。
#. THP 不是锁定内存；它仍可被回收、迁移、swap、split 或重新 collapse，具体取决于页类型和策略。
#. HugeTLB 页通常来自预留池，不按普通 Page Cache/LRU 路径自动回收，资源规划必须显式进行。
#. 启动早期预留 HugeTLB 页通常比运行中扩容更容易成功，因为物理内存碎片更低。
#. ``nr_hugepages``、``free_hugepages``、``resv_hugepages``、``surplus_hugepages`` 等指标描述池总量、空闲、reservation 和临时超额。
#. Reservation 表示映射未来 fault 时有资源承诺，不等于目标页已经映射进当前进程页表。
#. HugeTLB 的 reservation、实际分配、映射和释放是不同阶段，失败诊断必须确认卡在哪一层。
#. Private HugeTLB 映射写入也可能涉及 COW 和 reservation；没有足够资源时可能触发 ``SIGBUS`` 或失败路径。
#. Shared HugeTLB 映射按共享后端语义工作，不应套用普通匿名 THP 的自动回退规则。
#. HugeTLB 页大小可有多种，用户接口、挂载选项和 ``MAP_HUGE_*`` 编码必须与系统支持的大小匹配。
#. HugeTLB pool 占用的内存减少普通 page allocator 可用容量，过度预留会挤压普通工作负载。
#. 预留过少会让显式大页应用启动或 fault 失败，预留过多会造成资源闲置和普通内存压力。
#. THP 的优势是透明和可回退，代价是运行时行为更依赖碎片、策略和后台整理。
#. HugeTLB 的优势是资源与页大小更可预测，代价是部署、reservation、容量和 NUMA 管理更复杂。
#. NUMA 系统上，大页位置会影响远端访问；THP 和 HugeTLB 都要结合 cpuset、mempolicy 和节点池观察。
#. ``/proc/<pid>/smaps`` 中的 ``AnonHugePages``、``ShmemPmdMapped``、``FilePmdMapped`` 等字段可观察部分实际大页结果。
#. ``KernelPageSize``、``MMUPageSize`` 与 huge page 统计必须结合解释，不能只看一个字段判断底层 folio 和页表层级。
#. ``/proc/meminfo`` 的 ``AnonHugePages``、``ShmemHugePages``、``Hugetlb``、``HugePages_*`` 提供系统级不同大页维度。
#. ``/proc/vmstat`` 中 ``thp_fault_alloc``、``thp_fault_fallback``、``thp_collapse_alloc``、split 与 compaction 计数名称可能随版本变化。
#. THP fallback 增长只说明未形成目标大页，不自动说明应用失败；应检查是否成功回退基础页以及延迟成本。
#. Collapse 成功率低可能来自 VMA 不合格、页面未全部驻留、被 pin、碎片、NUMA 或频繁修改。
#. Split 增长可能是正常生命周期，也可能表明 fork/COW、内存压力或 VMA 操作正在抵消大页收益。
#. 大页性能评估必须同时观察 TLB miss、页表内存、fault 延迟、compaction、RSS/PSS、COW 和业务吞吐。
#. 只看 ``AnonHugePages`` 增加无法证明性能改善；只看 THP fallback 也无法证明应关闭 THP。
#. 针对低延迟服务，应比较 THP 策略下的 p50/p99/p999，而不是只比较平均吞吐。
#. 针对数据库、虚拟机和大模型工作集，还应检查自身内存管理器是否已提供显式大页或预触碰策略。
#. DMA 需要设备可访问地址和 DMA API，普通 THP 或 HugeTLB 用户映射不能直接替代驱动 DMA 分配协议。
#. DAX、设备私有内存和文件 THP 有各自后端限制，不能从匿名 THP 规则推导全部行为。
#. 最稳定的大页分析顺序是：确认页大小与机制 → 读取策略 → 检查实际映射结果 → 观察 fault/collapse/split → 对齐 compaction 与业务延迟。

必背路径
--------

Fault-time THP：

::

   进程访问符合条件的 VMA
   → page fault 检查 THP 策略
   → 检查地址与页大小对齐
   → 检查 NUMA、VMA 和内存策略
   → 尝试分配连续大页
   → 必要时按 defrag 策略回收或压缩
   → 成功时建立大粒度页表映射
   → 失败时通常回退基础页
   → 记录 fault alloc / fallback 统计

``khugepaged`` collapse：

::

   普通基础页已经驻留
   → khugepaged 扫描候选 VMA
   → 检查整段页面状态与可合并性
   → 分配目标大页
   → 复制或迁移基础页内容
   → 更新反向映射和页表
   → 刷新 TLB
   → 释放旧基础页
   → 建立大页映射

THP split：

::

   COW、回收、迁移或 VMA 变更需要细粒度
   → 锁定大页和相关页表
   → 拆除大粒度映射
   → 建立基础页级映射或元数据
   → 更新 rmap、mapcount 和引用
   → 执行 TLB shootdown
   → 后续页面按细粒度处理

HugeTLB 显式分配：

::

   管理员配置指定大小 huge page pool
   → 应用创建 hugetlbfs / MAP_HUGETLB 映射
   → 建立 reservation
   → fault 时从对应节点和大小池取得页
   → 安装 HugeTLB 页表映射
   → 使用期间按显式资源语义管理
   → unmap / 退出后归还 reservation 与页池

大页延迟诊断：

::

   定位延迟窗口
   → 采样 THP fault、fallback、collapse、split 增量
   → 采样 compaction 与 direct reclaim
   → 读取 smaps 中实际大页覆盖
   → 检查 fork/COW 与 mprotect/munmap
   → 对照 TLB miss 和页表内存
   → 判断收益来自翻译还是成本来自建立与拆分

必须区分
--------

* THP 与 HugeTLB：THP 自动尝试并通常可回退；HugeTLB 使用显式资源池和 reservation，失败语义更严格。
* 策略允许与实际映射：Sysfs 或 madvise 只表达许可；实际大页还依赖 VMA、对齐、物理形状和运行状态。
* 大页映射与大 folio：页表可以先拆映射而底层 folio仍保持复合状态；两种 split 层次不能混写。
* Fallback 与应用失败：THP fallback 通常继续使用基础页；HugeTLB 资源不足可能让显式映射或 fault 失败。
* 翻译收益与分配成本：大页降低 TLB/page walk 成本，同时可能提高 fault、compaction、COW、回收和内部碎片成本。
* Reservation 与驻留页：HugeTLB reservation 是未来资源承诺；真正驻留和建立页表通常发生在后续 fault 或 population。

一句话结论
----------

THP 与 HugeTLB 都用更粗粒度页面换取地址翻译效率，但前者依赖自动策略和回退，后者依赖显式页池与 reservation，性能必须把长期 TLB 收益和 fault、压缩、拆分、COW 成本放在同一时间线上评估。
