第090章：诊断 Major Fault、Minor Fault 与内存异常
=================================================

核心知识点
----------

内存异常必须先拆成事件
   “变慢、变大、抖动”不是可执行结论。应先区分 major fault、minor fault、COW、THP、回收、writeback、TLB 和调度，再建立时间线。

Fault 计数必须看时间窗口
   ``minflt``、``majflt`` 和系统 fault 统计通常是累计值。至少采样两次计算增量，并按秒、请求数或业务阶段归一化。

Major fault 指向后端读入
   文件页不在 Page Cache、匿名页需要 swap-in，或其它后端必须把内容带入内存时，任务通常等待 I/O。应同时检查块设备、远端文件系统和 swap。

Minor fault 指向内存内修复
   匿名页首次触碰、安装已有 Page Cache 页的 PTE、fork COW、权限更新和 THP split 都可形成 minor fault。没有后端读入不表示单次成本一定低。

Fault 类型不能由 VMA 后端直接决定
   文件 VMA 既可能 minor 也可能 major，取决于 Page Cache 状态；匿名 VMA 的首次触碰通常 minor，swap-in 则通常 major。

VMA 用于定位语义
   ``/proc/<pid>/maps`` 回答 fault 地址属于哪段范围、权限和 private/shared 属性；``smaps`` 进一步给出 RSS、PSS、Anonymous、Dirty 和 HugePages 等构成。

VMA 存在不证明页面驻留
   Maps 只证明地址范围具有语义。页面是否在 Page Cache、是否有 PTE、是否在 swap，仍需 fault、I/O、smaps 或页级证据确认。

Fault 数量与单次成本必须分开
   一万个基础页 PTE 安装与一万个 THP COW fault 的成本不同。应同时观察处理时间、I/O、复制量、compaction、锁等待和 TLB shootdown。

系统内存压力会放大 Fault
   Minor fault 分配新页时可能进入 direct reclaim，文件 fault 也可能等待 folio lock、已有 I/O 或 writeback。``allocstall``、``pgscan``、``pgsteal`` 和 PSI memory 能说明叠加压力。

冷文件映射具有阶段性
   冷启动、容器迁移、节点重启或 Page Cache 被回收后，major fault 常在首次访问阶段升高。预热是否有效，要看后续 fault 斜率和真实工作集覆盖。

Fork COW 通常表现为 Minor fault 与私有化增长
   Fork 后写入会让 ``Private_Dirty``、``Anonymous``、RSS/PSS 和 minor fault 同步增长。父子 RSS 简单相加会重复统计共享页。

THP 诊断要区分策略和结果
   Sysfs 表示尝试规则，``smaps`` 表示实际覆盖，``vmstat`` 中的 fault、fallback、collapse、split 和 compaction 增量表示生命周期事件。

TLB miss 与 Page fault 是不同问题
   TLB miss 高而 fault 不高时，瓶颈属于翻译缓存覆盖与 page walk，不是页面缺失。硬件事件名称和支持范围需按目标 CPU 验证。

特殊机制会制造不同 Fault 流量
   NUMA hinting、userfaultfd、KVM、设备映射、``mprotect`` 和 DAX 都可能改变 fault 数量与含义，分析前必须确认 workload 是否使用这些机制。

错误结果必须纳入性能诊断
   ``SIGSEGV``、``SIGBUS`` 和 OOM 是 fault 无法完成的结果。Mmap、fork 或 write 成功都不保证后续页面构造一定成功。

关键路径
--------

Fault 第一层分类：

::

   固定 PID、cgroup 和时间窗口
   → 采样 minor 与 major fault 增量
   → Major 上升时检查文件、swap 和 I/O
   → Minor 上升时检查首次触碰、PTE、COW 和 THP
   → Fault 不高时转向 reclaim、TLB、锁和调度
   → 按请求量与业务阶段归一化

关联 VMA 与后端：

::

   取得 fault 地址或异常阶段
   → maps 定位 VMA 范围和权限
   → 判断 anonymous/file 与 private/shared
   → smaps 检查 RSS、PSS、Anonymous、Dirty 和 HugePages
   → 文件 VMA 对照 Page Cache、存储与 major fault
   → 匿名 VMA 对照首次触碰、swap 与 COW

诊断 COW 与 THP 放大：

::

   记录 fork、首次写入和延迟窗口
   → 采样 minor fault、Private_Dirty 与 Anonymous
   → 检查实际 AnonHugePages 覆盖
   → 采样 THP fault、fallback、collapse、split
   → 对齐 compaction、reclaim 和业务 p99
   → 判断页面复制、拆分或大页建立成本

概念辨析
--------

* Major fault 与文件映射：文件 VMA 可产生 minor 或 major；分界取决于是否需要从后端读入内容。
* Minor fault 与低延迟：Minor 不等待后端读入，但 COW、大页、回收和 TLB shootdown 仍可能昂贵。
* VMA 存在与页面驻留：Maps 描述范围语义；驻留与页表状态需要运行时证据确认。
* RSS 与独占内存：RSS 包含共享页；PSS、Private_Dirty 和映射分类更适合分析 fork/COW。
* THP 策略与 THP 结果：策略只决定尝试规则；smaps 和 vmstat 才能说明实际覆盖及生命周期事件。
* Fault 数量与 Fault 成本：计数说明频率；处理时间、I/O、复制、锁和 compaction 决定实际代价。

本章结论
--------

内存故障诊断应从 fault 增量开始，再定位 VMA、后端和页面状态，最后把 COW、THP、回收与 I/O 放入同一时间线。任何单一计数、RSS 或策略开关都不足以解释根因。
