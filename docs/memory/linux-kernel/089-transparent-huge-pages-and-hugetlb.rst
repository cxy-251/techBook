第089章：透明大页与 HugeTLB
===========================

核心知识点
----------

大页优化地址翻译覆盖率
   一个更大的页表项和 TLB 条目可以覆盖更大虚拟地址范围，减少页表项数量、page walk 和 TLB miss。收益取决于工作集大小与访问局部性。

大页同时放大管理粒度
   更粗的页面会增加清零、复制、迁移、回收和内部碎片成本。稀疏访问只使用大页中的少量内容时，物理占用可能明显放大。

THP 是自动大页机制
   Transparent Huge Pages 在普通匿名内存、shmem 或部分文件映射中，根据系统、进程和 VMA 策略自动尝试较大页面，应用通常无需显式资源池。

HugeTLB 是显式资源机制
   HugeTLB 通过专用页池、reservation、quota 和指定页大小管理大页。应用经 hugetlbfs、``MAP_HUGETLB`` 或相关共享内存接口显式使用。

THP 通常允许基础页回退
   Fault-time THP 分配失败时，多数普通内存路径可继续使用基础页，功能保持正确，但翻译收益降低，并可能留下 compaction 或 fault 延迟。

HugeTLB 失败语义更严格
   HugeTLB 没有对应大小的空闲页、reservation 或配额时，映射或 fault 可能直接失败并产生 ``SIGBUS``，不能按 THP 的透明回退理解。

THP 有两条形成路径
   进程首次访问时可直接分配大 folio 并建立大粒度映射；``khugepaged`` 也可以扫描已驻留基础页，把符合条件的范围 collapse 成大页。

策略允许不等于实际获得
   Sysfs 的 ``always``、``madvise``、``never``，以及 ``MADV_HUGEPAGE`` 只表达尝试规则。实际结果还依赖地址对齐、VMA、NUMA、物理连续形状和页面状态。

THP 建立可能进入回收与压缩
   Fault-time 分配为了取得连续页，可能按 defrag 策略触发 reclaim 或 synchronous compaction，把成本直接放进业务请求延迟。

Collapse 与 Split 是生命周期事件
   Collapse 把基础页和页表关系合并；split 则因 COW、回收、迁移、``mprotect`` 或 ``munmap`` 恢复细粒度。拆页表映射和拆底层复合 folio 是不同层次。

COW 会放大大页成本
   Fork 后写入 THP 可能复制整张大页、先拆分再复制基础页，或使用版本相关优化。大页收益必须与分歧时的复制和拆分成本共同评估。

HugeTLB Reservation 不是驻留映射
   Reservation 表示未来 fault 的资源承诺，实际取页、安装页表和驻留发生在后续阶段。诊断必须区分预留、分配、映射和释放。

大页位置具有 NUMA 属性
   THP 与 HugeTLB 都需要结合 cpuset、mempolicy、节点页池和实际页位置判断；大页位于远端节点时，翻译收益可能被访问延迟部分抵消。

运行证据必须区分机制与结果
   ``smaps`` 中的 ``AnonHugePages`` 等字段显示进程映射结果，``meminfo``、``vmstat`` 和 HugeTLB 池指标显示系统状态。单看策略或单个计数不能证明性能收益。

关键路径
--------

Fault-time THP：

::

   进程访问符合条件的 VMA
   → 检查 THP 策略、地址对齐和页大小
   → 检查 NUMA 与内存策略
   → 尝试分配连续大页
   → 必要时执行 reclaim 或 compaction
   → 成功时建立大粒度页表映射
   → 失败时通常回退基础页

``khugepaged`` Collapse 与 Split：

::

   基础页已经驻留
   → khugepaged 扫描候选范围
   → 验证页面状态、引用和可合并性
   → 分配目标大页并迁移内容
   → 更新 rmap、页表和 TLB
   → 后续 COW、回收或 VMA 变更需要细粒度时再 split

HugeTLB 显式资源路径：

::

   管理员建立指定大小 huge page pool
   → 应用创建 hugetlbfs 或 MAP_HUGETLB 映射
   → 建立 reservation
   → Fault 时从对应节点页池取得大页
   → 安装 HugeTLB 页表映射
   → Unmap 或退出后释放映射、页和 reservation

概念辨析
--------

* THP 与 HugeTLB：THP 自动尝试且通常可回退；HugeTLB 使用显式页池与 reservation，资源不足可能直接失败。
* 策略允许与实际映射：Sysfs 和 madvise 只定义许可；实际大页还依赖 VMA、对齐、物理形状和运行状态。
* 大页映射与大 folio：页表映射可以先拆分，而底层复合 folio 仍存在，两种层次不能混为一谈。
* Fallback 与应用失败：THP fallback 通常改用基础页；HugeTLB 失败可能阻止映射或 fault 完成。
* 翻译收益与管理成本：大页减少 TLB/page walk 成本，同时提高 fault、compaction、COW、回收和内部碎片成本。
* Reservation 与驻留：Reservation 是未来资源承诺；真正页面和页表映射通常在 fault 或 population 阶段建立。

本章结论
--------

THP 与 HugeTLB 都用更粗粒度页面换取地址翻译效率。前者依赖自动策略与回退，后者依赖显式页池与 reservation，评估时必须同时计算长期 TLB 收益和建立、压缩、拆分、COW 成本。
