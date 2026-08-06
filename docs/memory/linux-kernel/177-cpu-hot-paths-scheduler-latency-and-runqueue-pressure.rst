第177章：CPU 热路径、调度延迟与 Runqueue 压力
==============================================

本章必须记住
------------

#. CPU 性能问题首先要区分 On-CPU 执行成本和 Runnable Waiting 调度成本。
#. CPU Sampling 回答“正在执行时样本落在哪里”；Scheduler Event 回答“可运行任务何时真正得到 CPU”。
#. 一个请求线程变慢时，样本少可能表示它在睡眠，也可能表示它长期 Runnable 但没有被调度。
#. ``perf top`` 适合快速观察当前热点，``perf record/report`` 适合保存可复盘的采样窗口。
#. 热点函数只说明样本集中位置，必须结合 Call Graph 确认是谁把工作带到该函数。
#. 相同底层函数可由不同系统调用、IRQ、Softirq、Kworker 或内核线程调用，修复方向可能完全不同。
#. Kernel Symbol 解析依赖匹配的 ``vmlinux``、Kallsyms、Module、Build ID、KASLR 和权限。
#. ``[unknown]`` 或裸地址意味着符号证据不足，不能直接猜测热点函数。
#. Sampling Overhead 是当前 Event、Scope、Frequency 和聚合方式下的样本比例，不是函数绝对耗时。
#. Cycles Sampling 主要覆盖 On-CPU 时间，不包含 Task 离开 CPU 后的完整等待。
#. Flat View 回答样本落点；Caller/Callee View 回答进入路径。
#. 看到 ``native_queued_spin_lock_slowpath`` 只能证明自旋等待样本集中，还需找到具体锁对象和持锁路径。
#. 看到 ``copy_*_user`` 只能证明数据拷贝路径消耗 CPU，还需确认来自文件、网络、设备或其它接口。
#. 看到 Scheduler 函数热点可能来自高切换率，不自动说明调度器实现有 Bug。
#. PMU 事件用于继续解释同一热路径为何昂贵。
#. ``cycles`` 近似表示周期消耗，``instructions`` 表示退休指令数量。
#. IPC 是 Instructions/Cycles 的派生量，只描述退休效率，不直接给出根因。
#. Cycles 高且 Instructions 高通常指向真实工作量大、批量小或算法路径长。
#. Cycles 高而 Instructions 相对低时，应检查 Cache/TLB Miss、内存延迟、锁自旋和 Pipeline Stall。
#. Cache Miss 必须确认具体层级和事件定义；通用 ``cache-misses`` 不一定等同于 LLC Load Miss。
#. Branch Miss 高可能来自复杂控制流、间接分支、异常路径或数据分布变化。
#. PMU Event 强依赖 CPU 型号、微架构、虚拟化和 Counter 可用数量。
#. Raw Event 编码不能在不同 CPU 型号间机械复用。
#. 同时采集过多 Event 会触发 Multiplexing；Scaled Count 是估算值。
#. 比较 PMU 时应固定负载、窗口、CPU 范围和并发量，优先计算每请求事件成本。
#. CPU 总利用率会掩盖 Per-CPU、Per-Core、SMT、NUMA Node 和 Cgroup 局部饱和。
#. 某个网络 RX Queue、IRQ、Ksoftirqd 或单线程可占满一个 CPU，而整机仍显示大量空闲。
#. 单个 CPU 饱和时，增加未参与该路径的 CPU 不会自动改善延迟。
#. Runqueue 是 Per-CPU 调度对象，Runnable Task 需要入队、竞争、被选中并完成 Context Switch 才真正运行。
#. Runnable 与 Running 必须分开：Runnable 表示有资格，Running 表示正在执行。
#. Scheduler Latency 可用 Wakeup Timestamp 到实际 Switch-in Timestamp 近似观察。
#. ``sched_wakeup`` 表示 Task 变为可运行，``sched_switch`` 表示 CPU 切换执行实体。
#. Wakeup 成功不表示 Task 已经立即运行。
#. ``sched_switch`` 中的 Prev State 要按当前 Tracepoint ``format`` 解释。
#. Runnable Waiting 高通常指向 Runqueue 竞争、优先级、Affinity、Quota、IRQ、RT Task 或 CPU Offline。
#. Blocking Sleep 高通常指向锁、I/O、Timer、Memory、Socket 或 Condition Wait。
#. Load Average 包含可运行任务和部分不可中断睡眠任务，不能直接等同于 CPU Runqueue 长度。
#. CPU PSI 描述任务因 CPU 资源不足失去运行进展的时间，不等于 CPU 利用率。
#. ``/proc/schedstat``、Scheduler Trace、Runqueue 统计和 PSI 的可用字段具有版本边界。
#. Cgroup CPU Quota 可让宿主 CPU 有空闲，同时目标 Cgroup 内任务被周期性 Throttle。
#. Quota Throttling 要检查 ``cpu.max``、``cpu.stat`` 和目标 Cgroup，而不只是宿主 ``top``。
#. Cpuset 与 CPU Affinity 可把任务限制到少量 CPU，造成局部 Runqueue 压力。
#. Thread Affinity、IRQ Affinity 和 Application Sharding 必须放在同一 CPU 拓扑中检查。
#. NUMA 机器上任务迁移会改变 Cache 和内存局部性，纯粹追求平均 Runqueue 平衡可能增加远端访问成本。
#. CPU Migration 高不自动是坏事；需结合 Working Set、NUMA、Cache Miss 和尾延迟解释。
#. Context Switch 高可能来自高并发、短任务、I/O、锁、Timer 或抢占，不自动说明调度器异常。
#. 自愿切换通常来自 Task 主动阻塞，非自愿切换通常来自抢占或时间片等条件，精确统计口径依工具而定。
#. 高优先级 RT/DL Task 可让普通 Task 长期等待，即使总 CPU 使用率没有持续 100%。
#. Softirq、Hardirq 和 NMI 时间会占用 CPU，但可能不归入目标用户线程的普通样本。
#. 网络或存储 IRQ 集中时，应同时观察 ``/proc/interrupts``、Softirq 时间和目标 CPU Runqueue。
#. Ksoftirqd 热点可能说明软中断工作从正常上下文溢出到内核线程，不自动说明 Ksoftirqd 本身是根因。
#. 热点在 ``memcpy``、Checksum、Crypto、Compression 等路径时，应确认工作量是否可批处理、卸载或减少复制。
#. 热点在 Lock Slowpath 时，应确认共享对象、Cacheline、持锁长度和并发结构。
#. 热点在 Page Fault、Reclaim 或 Compaction 时，应转入内存性能证据链。
#. 热点在 Block、Filesystem 或 Network Stack 时，应继续定位 Queue 和 Completion，而非只优化 CPU 指令。
#. CPU Frequency、Thermal Throttling、Power Policy 和 SMT 竞争会改变相同代码的 Cycles 与延迟。
#. Frequency 降低时 CPU Utilization 可能接近不变，但每请求服务时间上升。
#. 虚拟机中的 Steal Time 表示 VCPU 等待宿主调度，不能归因于来宾内核 Runqueue。
#. Bare-metal 与 Virtual Machine 的 PMU、Frequency 和 Scheduler 证据不可机械比较。
#. 调度问题调查应保存 Task PID/TID、Comm、Cgroup、CPU、Priority、Policy、Affinity 和时间窗口。
#. PID 复用要求长时间采集同时保存进程启动时间或业务实例 Generation。
#. Scheduler Trace 数据量很大，应限制到目标 PID、CPU、Cgroup 或短窗口。
#. 采样频率越高，统计分辨率和扰动同时增加。
#. 短时尖峰应使用 Trigger、Snapshot 或循环低成本观测，而不是长期全量 Function Trace。
#. 调优 CPU 前应先确定瓶颈是执行量、微架构停顿、Runqueue、Quota、IRQ 还是锁。
#. 增加线程只对尚有可用并行度且共享争用可控的路径有效。
#. 线程数超过有效 CPU、队列或分片数量后，常增加 Context Switch、Cache Miss 和 Lock Contention。
#. 绑核可降低迁移和 Cache 抖动，也可能造成负载倾斜和局部饱和。
#. 调整 IRQ Affinity 可改善队列分布，也可能破坏应用与数据的 NUMA 局部性。
#. 修改 Scheduler Policy 或 Priority 会改变其它任务的公平性和饥饿风险。
#. CPU 优化结果应同时验证 Cycles/Request、Runnable Wait、p99、吞吐、迁移和邻居工作负载。
#. 热点样本下降但 Runnable Wait 上升，可能只是把执行成本转成更多调度竞争。
#. Runqueue 下降但 Cache Miss/Request 上升，可能是过度迁移或错误分片。
#. 稳定诊断顺序是：Per-CPU 利用率 → Target Task On/Off-CPU → Hot Path → PMU → Wakeup/Switch → Affinity/Quota/IRQ → 最小修复。

必背路径
--------

CPU 热点定位：

::

   固定异常负载和时间窗口
   → perf stat 判断 Cycles、Instructions 与基础事件
   → perf record 保存目标范围的采样
   → perf report 检查 Flat Hotspot
   → 展开 Caller/Callee Call Graph
   → 对照匹配 Kernel/Module 源码
   → 用 PMU Event 解释执行为何昂贵
   → 计算每请求成本

Runnable Waiting：

::

   Task 被事件唤醒
   → sched_wakeup 记录 Runnable 时刻
   → Task 进入目标 CPU Runqueue
   → 与同优先级、RT、IRQ 和其它工作竞争
   → sched_switch 记录真正 Switch-in
   → Wakeup 到 Switch-in 的差值形成调度等待
   → 结合 Affinity、Quota、Priority 和 CPU 拓扑解释

局部 CPU 饱和：

::

   总 CPU 看似有余量
   → 检查 Per-CPU Utilization 与 Softirq/IRQ
   → 检查目标 Task/Queue 的 CPU Affinity
   → 检查 Cgroup Quota 与 Cpuset
   → 检查单队列、单线程或单锁
   → 对齐 NUMA Node 和应用 Worker
   → 再决定分流、扩队列、绑核或减少工作

CPU 修复验证：

::

   保存原始线程、Affinity、Quota 与 IRQ 配置
   → 只改变一个并行或局部性变量
   → 保持请求组成和观测 Event 一致
   → 比较 Cycles/Request、IPC、Cache Miss、Runnable Wait
   → 比较 p99、吞吐和其它工作负载
   → 回滚或固化

必须区分
--------

* Hotspot 与 Root Cause：样本集中位置仍需调用来源和对象证据。
* On-CPU 与 Runnable Waiting：前者正在执行，后者已有资格但等待 CPU。
* Runnable Waiting 与 Blocking Sleep：前者等待调度资源，后者等待事件或对象。
* CPU 总利用率与局部饱和：整机平均值可隐藏单 CPU、Queue、Cgroup 和 NUMA Node 压力。
* Cycles 与 Instructions：周期包含停顿，指令表示退休工作量。
* IPC 与业务效率：IPC 高低不能脱离算法、工作量和延迟目标解释。
* Cache Miss 与 Reclaim：前者是 CPU 内存层级事件，后者是内核页回收路径。
* Context Switch 与 Scheduler Bug：切换数量必须结合原因、任务和等待时间。
* Affinity 与性能保证：绑核改变位置，不自动增加服务能力。
* Sampling Percent 与绝对时间：样本比例依 Event、Scope、Window 和聚合方式变化。

一句话结论
----------

CPU 性能调查必须同时解释“CPU 正在执行什么”和“目标任务为什么还没得到 CPU”，再用 PMU、调度事件和拓扑证据决定修复对象。
