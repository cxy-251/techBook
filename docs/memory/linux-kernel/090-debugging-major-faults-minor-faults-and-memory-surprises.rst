第090章：诊断 Major Fault、Minor Fault 与内存异常
=================================================

本章必须记住
------------

#. 内存“变慢、变大、抖动”必须先拆成 fault、I/O、COW、大页、回收和调度等可观测事件。
#. Major fault 表示合法 fault 处理需要从文件、swap 或其它后备存储把页内容带入内存。
#. Minor fault 表示无需后端读入即可完成页表修复，但仍可能包含页分配、清零、COW 复制、大页拆分和 TLB shootdown。
#. Major fault 通常更容易形成 I/O 延迟；大量 minor fault 也可能消耗显著 CPU、锁和内存带宽。
#. Fault 计数是处理结果，不直接说明哪个 VMA、哪条代码或哪个后端造成成本。
#. 第一步应在固定时间窗口计算 fault 增量，并与请求量、延迟、I/O、RSS 和 CPU 同步对齐。
#. ``perf stat -e page-faults,minor-faults,major-faults`` 可观察命令或窗口内的软件 fault 事件。
#. ``/proc/<pid>/stat`` 提供累计 minflt/majflt 等字段，解析时必须处理括号中的 ``comm`` 可能包含空格。
#. ``/proc/<pid>/status``、``statm`` 和 ``smaps`` 提供不同粒度的虚拟内存、RSS、PSS 和映射构成。
#. 累计值本身没有速率意义，应至少采样两次并除以时间或请求数。
#. 线程级与进程级 fault 统计范围可能不同，使用 perf、proc 和应用指标时必须确认统计对象。
#. 子进程 fault 字段与当前进程 fault 字段也可能分开累计，fork-heavy workload 不能只读一个数字。
#. Major fault 增长时，应优先检查文件映射冷页、可执行映射、动态库、swap-in、网络文件系统和存储延迟。
#. Major fault 与块读取、I/O wait、blocked task 同时增长时，后备 I/O 是强候选。
#. Major fault 增长但本地块 I/O 不明显时，还要检查远端文件系统、DAX、用户态 fault handler 和容器层统计。
#. Minor fault 增长时，应优先检查匿名页首次触碰、Page Cache 已命中页的 PTE 安装、fork COW、THP split 和权限变更。
#. Minor fault 接近零不表示没有内存压力；回收、writeback、TLB miss 和锁竞争可以在没有大量 fault 时发生。
#. Major fault 接近零也不表示所有文件页已经驻留，应用可能尚未访问相关 VMA。
#. ``/proc/<pid>/maps`` 用于把虚拟地址或内存区域定位到 VMA 范围、权限、private/shared 和文件路径。
#. ``maps`` 只能说明映射语义，不能说明目标页当前是否在 Page Cache 或是否驻留。
#. ``smaps`` 的 RSS、PSS、Shared/Private Clean/Dirty、Anonymous、AnonHugePages 等字段可进一步分析页面来源与共享。
#. ``smaps_rollup`` 适合低成本查看进程整体汇总，但不能定位到具体 VMA。
#. 频繁读取完整 ``smaps`` 可能有开销，线上采样应控制频率并使用必要权限。
#. 文件 VMA + major fault + 后端读 I/O 通常表示冷 Page Cache 或 swap/file 后备读入。
#. 文件 VMA + minor fault + 无读 I/O 通常表示 folio 已在 Page Cache，只需建立当前进程 PTE。
#. 匿名 VMA + minor fault + RSS 增长通常表示首次触碰、COW 或 THP 处理。
#. 匿名 VMA + major fault + swap-in 计数增长通常表示匿名页正在从 swap 返回。
#. Fault 地址来自崩溃、perf sample、tracepoint 或应用日志时，应先在 ``maps`` 中定位对应 VMA。
#. 地址不在 VMA 或权限不符时，应转向 ``SIGSEGV``/``SIGBUS`` 诊断，而不是性能型 major/minor fault 分析。
#. ``vmstat``、``/proc/vmstat`` 和 PSI 可以把进程 fault 放回整机回收、swap 和任务停顿背景。
#. ``pgfault`` 和 ``pgmajfault`` 是系统累计统计，字段单位和含义以目标内核文档为准。
#. ``pswpin``、``pswpout``、块 I/O 和 major fault 对齐时，可以证明 swap 或文件后备正在参与。
#. ``allocstall``、``pgscan``、``pgsteal`` 和 PSI memory 上升说明 fault 延迟可能叠加 direct reclaim。
#. Page fault 期间分配新页可能进入 reclaim，因此一次 minor fault 也可能被内存压力放大成高尾延迟。
#. 文件 fault 可能等待 folio lock、已有 read I/O 或 writeback，不能把所有 major fault 延迟归给设备本身。
#. Readahead 可以减少顺序文件访问中的后续 major faults，也可能读入无用页面并挤压工作集。
#. 冷启动、容器迁移、节点重启和缓存被回收后，文件映射 major faults 往往出现阶段性升高。
#. 预热效果必须通过后续 fault 斜率和业务延迟验证，不能只证明程序执行了一次扫描。
#. Fork 后 COW 放大通常表现为 minor faults、Private_Dirty、Anonymous 和 RSS/PSS 随写入增长。
#. Parent 与多个 child 的 RSS 相加会重复计算共享页，PSS 更适合估算真实共享成本。
#. Fork 前父进程热页越多、fork 后父子写入越广，COW 放大越明显。
#. Fork 后立即 exec 的子进程通常不会复制大部分父进程数据页；长期 worker 写入才是 COW 主风险。
#. COW 诊断应对齐 fork 时间、worker 启动、写入阶段、minor fault、Private_Dirty 和内存带宽。
#. THP 诊断必须区分策略、实际大页覆盖、fault-time allocation、collapse、split 和 fallback。
#. ``/sys/kernel/mm/transparent_hugepage/`` 表示策略，不证明目标 VMA 实际使用大页。
#. ``smaps`` 中 AnonHugePages 等字段用于观察映射结果，仍需结合页表层级和内核版本解释。
#. ``/proc/vmstat`` 中 THP fault、fallback、collapse、split 和 compaction 计数应按时间窗口计算增量。
#. THP fault 与 synchronous compaction 对齐时，首次触碰可能形成明显尾延迟。
#. THP fallback 增长且业务无失败，通常说明回退基础页；重点应判断延迟和长期 TLB 收益变化。
#. THP split 与 fork/COW、mprotect、munmap 或 reclaim 对齐时，说明粗粒度映射正在被细化。
#. Split 增长本身不是 bug，只有与性能回退、重复 collapse、COW 放大或内存压力结合才有诊断意义。
#. HugeTLB 应观察专用池、reservation、free、surplus 和具体页大小，不能用 THP 计数解释。
#. Page table 内存增长可能来自进程数量、VMA 大量触碰、THP split 或极大稀疏地址空间，应同时观察页表统计。
#. TLB miss 高但 fault 不高时，问题属于地址翻译缓存和工作集覆盖，不是缺页异常数量。
#. Perf 硬件事件名称与支持情况依赖 CPU 和内核，TLB 事件必须先用 ``perf list`` 确认。
#. Fault 事件数量与单次成本都重要；同样一万个 minor faults，基础页 PTE 安装和 THP COW 的成本不同。
#. 应使用延迟直方图或 tracing 区分 fault handler 执行时间，而不是只用总 fault 数推断成本。
#. Fault tracepoint、perf sample、ftrace 或 eBPF 可以把地址、task、结果和调用栈关联，具体可用点依赖内核版本。
#. 线上使用动态追踪前必须评估采样开销、地址隐私和生产权限。
#. ``mincore`` 可以查询给定用户映射页是否驻留，但结果是瞬时信息且受权限、映射和竞争影响。
#. ``mincore`` 驻留不等于当前进程已有 PTE，也不等于页面不会马上被回收。
#. ``pagemap`` 受权限和安全限制，present/PFN 信息不能作为普通无权限诊断的唯一依赖。
#. ``numa_maps`` 可帮助判断 VMA 的 NUMA 分布、匿名/文件属性和大页信息，但格式具有版本差异。
#. NUMA hinting faults 与普通 demand fault 的性能意义不同，统计和 tracing 时要检查是否启用自动 NUMA balancing。
#. Mprotect、userfaultfd、KVM 和设备映射可以制造特殊 fault 流量，分析前必须确认 workload 是否使用这些机制。
#. OOM、SIGBUS 或 SIGSEGV 属于 fault 失败结果，性能诊断不能忽略错误日志和信号现场。
#. 一次 ``write``、fork 或 mmap 成功不保证后续 fault 一定成功；页面分配仍可能受 memcg、NUMA 和容量限制。
#. 对比实验只能一次改变一个主要变量，例如预热、THP 策略、fork 时机或数据集大小，否则难以归因。
#. 不应使用 ``drop_caches`` 作为常态修复；它适合受控冷缓存实验，并会影响整机其它工作负载。
#. 正确报告应包含时间窗口、PID/cgroup、VMA、fault 增量、RSS/PSS、I/O、swap、THP、回收和业务延迟。
#. 最稳定诊断顺序是：fault 增量分类 → 定位 VMA → 判断匿名/文件与 private/shared → 检查后端驻留 → 检查 COW/THP → 对齐回收和 I/O。

必背路径
--------

Fault 第一层分类：

::

   发现请求延迟或内存增长
   → 固定 PID、cgroup 和时间窗口
   → 采样 minor / major fault 增量
   → major 上升时检查文件、swap 和 I/O
   → minor 上升时检查首次触碰、PTE、COW 和 THP
   → fault 不高时转向 reclaim、TLB、锁或调度
   → 与业务阶段和请求数归一化

关联 VMA 与后端：

::

   取得 fault 地址或异常时间窗口
   → /proc/<pid>/maps 定位 VMA
   → 检查 r/w/x 与 private/shared
   → 检查 pathname、offset 和匿名标记
   → smaps 查看 RSS、PSS、Anonymous、Dirty、HugePages
   → 文件 VMA 对照 Page Cache 与 I/O
   → 匿名 VMA 对照首次触碰、swap 和 COW

诊断冷文件映射：

::

   模型或数据文件存在映射
   → 访问阶段 majflt 增长
   → 块读或远端存储延迟增长
   → Page Cache 冷或已被回收
   → fault 读入 folio
   → 后续同范围访问 majflt 下降
   → 验证预热和 readahead 是否覆盖真实工作集

诊断 COW 放大：

::

   记录 fork 前父进程 RSS/PSS
   → fork 后采样各进程 smaps
   → 对齐首次写入阶段
   → minor faults 与 Private_Dirty 增长
   → Anonymous 与总物理占用上升
   → 检查 THP 是否被复制或拆分
   → 判断工作集分歧范围
   → 调整 fork/exec、继承范围或写入架构

诊断 THP 延迟：

::

   读取全局和进程 THP 策略
   → 检查实际 AnonHugePages 覆盖
   → 采样 thp_fault_alloc / fallback
   → 采样 collapse / split 与 compaction
   → 对齐 fault 延迟和业务 p99
   → 区分建立成本、拆分成本和长期 TLB 收益
   → 用受控策略实验验证

必须区分
--------

* Major fault 与文件映射：文件 VMA 既可 minor 也可 major；是否需要后端读入取决于 Page Cache 当前状态。
* Minor fault 与低延迟：Minor 不等待后端内容读入，但 COW、大页和 reclaim 仍可能让单次处理昂贵。
* VMA 存在与页面驻留：Maps 说明地址语义；驻留和 PTE 状态需要 smaps、fault 与后端证据。
* RSS 与真实独占内存：RSS 包含共享页；PSS、Private_Dirty 和映射分类更适合分析 fork/COW。
* THP 策略与 THP 结果：Sysfs/madvise 表达尝试规则；smaps 和 vmstat 才显示实际映射与生命周期事件。
* Fault 数量与 Fault 成本：计数说明频率；处理时间、I/O、复制和 compaction 决定每次 fault 的实际延迟。

一句话结论
----------

诊断内存异常必须先用时间窗口区分 major 与 minor fault，再把事件落到具体 VMA、后端驻留、COW 和大页状态，并与 I/O、回收及业务延迟形成同一证据链。
