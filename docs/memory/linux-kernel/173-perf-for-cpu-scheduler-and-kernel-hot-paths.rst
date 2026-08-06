第173章：perf：CPU、Scheduler 与 Kernel Hot Paths
================================================

本章必须记住
------------

#. ``perf`` 是 Linux ``perf_events`` 子系统的主要用户态工具族，通过 ``perf_event_open()`` 创建事件对象，统一观测硬件 PMU、软件事件、Tracepoint、Kprobe/Uprobe 等数据源。
#. ``perf`` 的三种核心能力必须分开：Counting、Sampling 与 Event Correlation。
#. Counting 回答某个时间窗口内事件发生了多少次；Sampling 回答样本集中在哪些指令、函数和调用链；Event Correlation 回答事件在 CPU、Task 和时间线上的关系。
#. ``perf stat`` 主要做计数；``perf record`` 保存样本或事件；``perf report`` 聚合解释 ``perf.data``；``perf top`` 提供实时热点视图。
#. ``perf sched`` 主要分析调度事件；``perf lock`` 主要分析锁竞争；它们和普通 Cycles Sampling 回答不同问题。
#. 性能调查不能从“CPU 高”直接跳到“某函数慢”。稳定顺序是：现象 → 范围 → 计数 → 采样 → 调用链 → 调度/锁/Tracepoint → PMU → 源码和对象解释。
#. 一个 Perf Event 可绑定到 Task、Thread、CPU、Cgroup 或系统范围；分析前必须确认观测范围。
#. 同一命令在 Per-task 与 System-wide 模式下得到的样本集合不同，不能直接比较百分比。
#. ``struct perf_event_attr`` 描述事件 Type、Config、Sample Period/Frequency、Sample Type、Read Format、Exclude 规则等 UAPI。
#. ``perf_event_open()`` 返回的 fd 代表一个内核 Event 对象；Close fd、Disable Event、Unmap Ring Buffer 与最终释放是不同生命周期边界。
#. Event 可组成 Group，共享 Enable/Disable 和调度关系；Group 读数需要检查 Multiplexing 与 Scale。
#. PMU Counter 数量有限，事件过多时内核会时间复用；输出中的 ``time_enabled``、``time_running`` 或 Scale 反映复用影响。
#. Multiplexed 计数是估算值，不等于每个事件全窗口都在硬件上运行。
#. ``perf stat`` 中 Cycles、Instructions、Context Switches、CPU Migrations、Page Faults 等属于不同层面的证据。
#. Cycles 与 Instructions 可计算 IPC，但 IPC 只描述退休效率，不直接指出 Cache、Branch、Lock、I/O 或调度根因。
#. Context Switches 高可能来自高并发、阻塞 I/O、锁、定时器或短任务，不自动等于调度器异常。
#. CPU Migrations 高需要结合 Affinity、NUMA、负载均衡和工作集，不能只按数量判断坏处。
#. Page Faults 必须区分 Minor 与 Major；Fault 多不一定是问题，关键是是否造成 I/O、Reclaim 或尾延迟。
#. ``perf record`` 按 Period 或 Frequency 生成样本；样本占比反映事件样本分布，不是函数绝对执行时间的精确测量。
#. 采样频率越高，统计分辨率越高，开销、数据量和扰动也越大。
#. 短窗口和低频事件可能样本不足；样本不足时应扩大时间或选择更直接事件，而不是对百分比过度解释。
#. ``cycles`` Sampling 主要告诉 CPU 时间样本落在哪里；它不会记录 Task 离开 CPU 后等待 I/O、锁或调度的全部 Off-CPU 时间。
#. On-CPU Hotspot 与 Off-CPU Wait 是两类问题；低 CPU 利用率并不排除严重调度、锁、I/O 或内存等待。
#. ``perf report`` 的 Overhead 表示当前聚合方式下样本比例；改变 Event、Scope、Call Graph 或过滤器会改变含义。
#. Flat View 回答样本落在哪个 Symbol；Call Graph 回答样本从哪些入口到达该 Symbol。
#. 同一个底层函数可由完全不同路径调用，必须展开 Caller/Callee 后再决定修复方向。
#. ``native_queued_spin_lock_slowpath`` 热点只能证明自旋等待样本集中；还需调用链和 Lock Event 找到具体锁对象与持有者路径。
#. ``copy_*_user`` 热点可能来自系统调用数据搬运，也可能来自 Fault、Filesystem、Network 或 Device 控制路径。
#. ``clear_page``、``copy_page`` 热点需要结合 Page Fault、Allocation、COW、Zeroing 和 Memory Policy 解释。
#. Kernel Symbol 解析依赖 ``/proc/kallsyms``、未压缩 ``vmlinux``、Module Symbol、Build ID、Debuginfo 和权限。
#. 报告中出现 ``[unknown]`` 或裸地址时，应先修复符号与栈回溯证据，不能直接猜测函数。
#. ``vmlinuz`` 是启动镜像，通常不能替代带符号的未压缩 ``vmlinux``。
#. KASLR 会改变运行地址；Perf 需要正确的内核映像、Build ID 或 Kallsyms 信息完成地址重定位。
#. Module 采样还需要与运行模块版本匹配的 ``.ko``/Debuginfo；模块重载会改变地址与生命周期。
#. Call Chain 质量依赖 Frame Pointer、DWARF、LBR、ORC/架构 Unwinder 和编译优化。
#. 调用链断裂只能说明 Unwind 证据不足，不等于路径在该位置开始。
#. User Stack 与 Kernel Stack 使用的 Unwind 机制可不同，混合调用链要分别检查。
#. ``perf top`` 适合快速发现当前热点，但界面变化快、难复盘；关键调查应使用 ``record`` 保存数据。
#. ``perf.data`` 必须和 Kernel Release、Machine、Workload、Command Line、Event 与时间窗口一起保存。
#. 在另一台机器分析 Perf Data 时，需要匹配的 Binary、Debuginfo、Module 和 Build ID Cache。
#. ``perf sched record`` 通过调度 Tracepoint 保存 Wakeup、Switch、Migration 等事件。
#. Scheduler Latency 的核心关系是 Wakeup Timestamp → Task 真正 Switch-in Timestamp。
#. 一个 Task 被唤醒后长时间未运行，可能来自 Runqueue 压力、优先级、CPU Affinity、Cgroup Quota、RT Task、IRQ 或 CPU Offline。
#. ``perf sched latency`` 聚合调度等待；``perf sched timehist`` 提供更接近时间线的视图，精确命令随工具版本变化。
#. ``sched_switch`` 记录上下文切换，不直接记录业务请求边界；需要 PID/TID、Comm、Cgroup 或应用 Marker 关联。
#. ``prev_state`` 等字段的编码和含义必须参考当前 Tracepoint Format，不能凭旧版本记忆解释。
#. Runnable Waiting 与 Blocking Sleep 必须区分：前者等待 CPU，后者等待事件、锁或 I/O。
#. Cycles Hotspot 只能看到 Runnable 且在 CPU 上执行的时间；Off-CPU 分析需要调度、锁、Block 或应用事件。
#. ``perf lock`` 依赖锁事件与相关内核配置，可聚合 Contention Count、Wait Time、Acquisition 等指标。
#. Lock 名称或地址只是入口；结论需要锁类型、对象归属、持有路径、等待路径、临界区和 CPU 拓扑。
#. 自旋锁竞争主要消耗 On-CPU Cycles；Mutex/Semaphore 等睡眠锁会形成 Off-CPU Wait，两者证据形态不同。
#. Lock Contention 可能来自真正共享状态，也可能来自 False Sharing、全局 Queue 或错误 Batch Size。
#. Tracepoint 可作为 Perf Event，通过 ``perf record -e subsystem:event`` 保存结构化事件。
#. 使用 Tracepoint 前应读 Tracefs ``format`` 或 ``perf list`` 输出，确认字段与版本。
#. Perf 的 Tracepoint 记录和 Ftrace Event 可以来自同一内核 Hook；差异主要在控制、数据格式、存储和分析工具链。
#. PMU Event 是硬件微架构证据，必须按 CPU 型号和厂商文档解释。
#. ``cycles``、``instructions``、``cache-misses``、``branch-misses`` 是通用名称，但底层映射和精度具有平台差异。
#. Cache Miss 计数需要确认层级和事件定义；“cache-misses”不一定等同于 LLC Load Miss。
#. Branch Miss 比例高可能来自复杂控制流、间接分支、异常路径或代码布局，不能自动归因于编译器。
#. 高 Cycles、低 Instructions 可能表示 Stall，也可能表示频率、虚拟化、Counter 语义或 Speculation 影响。
#. PMU 分析应检查 Frontend、Backend、Memory、Branch、TLB、Core/Uncore 等可用事件族，而不是只看一个通用计数器。
#. Raw Event 编码强依赖 CPU Model，跨机器复用前必须验证 Event Table。
#. Virtual Machine 中 PMU 可能被 Hypervisor 虚拟化、限制或 Multiplex，计数精度和可用事件不同。
#. ``perf_event_paranoid``、``kptr_restrict``、Lockdown、LSM 与 Capability 会限制观测范围和符号。
#. ``CAP_PERFMON`` 是较窄的 Perf 观测授权；旧内核或兼容路径可能依赖 ``CAP_SYS_ADMIN``。
#. 获得 Perf 权限意味着可观察内核和其它进程行为，属于安全与隐私边界，不是普通工具便利开关。
#. 容器内 Perf 可受 Cgroup、Namespace、Seccomp、Capability、PMU 虚拟化和宿主策略限制。
#. 容器中可运行 ``perf`` 不表示能够看到宿主所有 CPU、Task 和 Kernel Symbol。
#. System-wide ``perf record -a`` 数据量和开销较大，应限定 CPU、PID、Cgroup、Event 和时间窗口。
#. Call Graph、Stack Dump、Branch Stack、Memory Sample 等附加字段会显著增加每样本数据量。
#. Sampling 本身会触发 PMU Overflow/NMI 或软件回调；高频率可能影响实时性和竞态。
#. 性能敏感系统应先用低成本 ``stat`` 和已有 Counter，再逐步开启短时 Sampling。
#. 观测工具开销必须进入实验基线；修改采样频率或 Call Graph 模式后不能直接和旧数据比较。
#. Perf 可以丢失样本；输出中的 Lost Event、Ring Buffer Overrun 或 Wakeup 统计必须检查。
#. 没有丢失报告不等于完全无扰动；采样仍会改变 Cache、IRQ/NMI 和调度行为。
#. ``perf record`` 正常退出前会 Flush 数据；进程被 Kill、磁盘满或系统崩溃可能留下不完整文件。
#. 报告前应检查文件完整性、事件列表、采样数和时间范围。
#. 事件计数与业务请求必须建立共同时间轴。Perf 只知道 CPU/Task/Event，不知道高层请求含义，除非应用提供 Marker 或可关联 ID。
#. 分析 CPU 热点时应同时记录吞吐和延迟；吞吐下降可能让热点百分比上升，但绝对工作量反而减少。
#. 百分比变化必须结合总 Cycles、Wall Time、CPU 数和工作量归一化。
#. 两次报告中同一函数从 10% 变 20%，可能只是其它路径减少，不表示该函数绝对成本翻倍。
#. 优化后应比较每请求 Cycles、Instructions、Cache Miss、Context Switch 和 Tail Latency，而不是只比较 Overhead。
#. 调度问题应结合 Runqueue 长度、PSI、Cgroup Throttling、IRQ/Softirq、Affinity 与 NUMA 证据。
#. 锁问题应结合调用链、Lock Event、Critical Section、Waiter/Holders 和 Cache Line 共享。
#. 内存问题应结合 Fault、Reclaim、Compaction、NUMA、TLB 和 PMU Memory Stall。
#. I/O 问题应结合 Block Tracepoint、Queueing、Service Time 和 Task Off-CPU 时间。
#. 网络问题应结合 NAPI、Softirq、qdisc、Socket、Retransmit、Drop 与应用消费。
#. Perf 报告中的热点是“下一步阅读入口”，不是自动修复建议。
#. 修改代码前要形成可证伪假设，例如“共享锁导致多核请求在 Slowpath 自旋”，并定义验证指标。
#. 修复后应使用同一 Event、Scope、Workload、采样配置和观测时长复测。
#. Flame Graph 是对 Stack Sample 的可视化聚合，宽度代表样本数量，不直接代表调用耗时或调用次数。
#. Fold/Flame 工具链可能丢失线程、CPU 或事件字段，原始 ``perf.data`` 仍是最终证据。
#. ``perf annotate`` 可把样本映射到指令/源码，但需要匹配 Binary 和 Debuginfo。
#. 指令级热点要结合编译器优化、Inline、Source Mapping 和架构指令，不应仅凭一行源码优化。
#. 事后崩溃分析不由 Perf 替代；Perf 记录运行时间线，Kdump/Vmcore 保存冻结内存对象。
#. 源码阅读顺序是：性能现象 → Event Scope → ``perf_event_attr``/Data Source → Count/Sample → Symbol/Call Chain → Scheduler/Lock/PMU → 对象路径 → 复测。

必背路径
--------

热点定位：

::

   固定 Workload、Kernel、CPU 与时间窗口
   → perf stat 统计 Cycles/Instructions/Context Switch/Fault
   → 选择最相关 Event
   → perf record 保存短时样本与 Call Chain
   → perf report 检查 Symbol 和调用来源
   → 回到源码与对象路径建立假设
   → 用相同配置复测修复

调度延迟：

::

   业务线程出现尾延迟
   → 记录 sched_wakeup/sched_switch 等事件
   → 关联目标 TID 的 Wakeup Timestamp
   → 找到实际 Switch-in Timestamp
   → 计算 Runnable Waiting
   → 检查 Runqueue、Affinity、Quota、Priority、IRQ 与 CPU 拓扑

锁竞争：

::

   Cycles 样本出现 Lock Slowpath
   → 展开调用链找到锁使用者
   → perf lock/lock Tracepoint 统计等待与争用
   → 定位锁对象、Holder、Waiter 与临界区
   → 区分自旋 CPU 成本和睡眠等待
   → 验证分片、Per-CPU、Batch 或锁范围修改

PMU 解释：

::

   发现 CPU 路径热点
   → 确认 CPU Model 与 Event 定义
   → 统计 Cycles、Instructions、Cache/TLB/Branch
   → 检查 Multiplexing 和 Scale
   → 按每请求或每字节归一化
   → 结合源码数据布局和访问模式解释

必须区分
--------

* Counting 与 Sampling：Counting 给出事件总量；Sampling 给出事件样本分布。
* On-CPU 与 Off-CPU：Cycles 采样观察正在 CPU 上执行的时间；调度、锁和 I/O 事件补充等待时间。
* Flat Hotspot 与 Call Graph：Flat View 显示样本落点；Call Graph 显示进入来源和调用关系。
* Overhead 百分比与绝对成本：百分比受其它路径变化影响；绝对成本要结合总事件、工作量和 Wall Time。
* PMU Event 名称与真实硬件事件：通用名称是抽象入口；精确含义取决于 CPU Model 和事件映射。
* Perf Event 与 Tracepoint：Perf Event 是统一计数/采样对象；Tracepoint 是其中一种结构化数据源。
* 符号缺失与路径不存在：裸地址或断栈表示解析证据不足，不证明源码路径不存在。
* 热点与根因：热点是样本集中位置；根因还需对象、调用来源、等待和业务证据。

一句话结论
----------

``perf`` 的核心价值是把“系统慢”分解为事件总量、样本落点、调用来源、调度等待和硬件成本，再把这些证据放回真实内核对象路径解释。
