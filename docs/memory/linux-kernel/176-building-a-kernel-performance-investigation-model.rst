第176章：建立内核性能调查模型
==============================

本章必须记住
------------

#. 性能调查的目标不是寻找“最优参数”，而是把用户可见的慢转换成可验证的时间路径。
#. 稳定调查闭环是：症状 → 路径假设 → 测量点 → 运行证据 → 最小修复 → 同口径复测。
#. 症状必须包含对象、时间窗口、基线、当前值、负载和影响范围。
#. “系统慢”“CPU 高”“磁盘忙”都不是足以行动的性能结论。
#. 合格症状应写成可比较事实，例如某接口 ``p99`` 从多少升到多少、吞吐下降多少、持续多久。
#. 路径假设必须指出哪个对象在哪个阶段等待、执行、排队或重试。
#. “请求线程在 Block I/O Completion 前睡眠”是可测试假设；“内核有问题”不是。
#. 测量必须由假设决定，不能先运行所有工具再从海量输出中寻找故事。
#. CPU 热路径优先使用 Sampling、Call Graph 和 PMU；调度等待优先使用 Wakeup/Switch 事件。
#. I/O 排队优先观察 Submit、Issue、Complete、Queue Depth 和设备统计。
#. 网络问题优先按 NIC、Driver、NAPI、Stack、Socket、Application 分层观察。
#. 锁问题要同时找等待者、持有者、锁对象和临界区，不能只看 Slowpath 函数名。
#. 修复必须落在已经被证据支持的对象和阶段上。
#. 最小修复的价值是验证因果，而不只是暂时让指标变化。
#. 修改线程数、Queue、Buffer、Timeout 或 Sysctl 前，必须说明它会改变哪一段路径。
#. 性能时间至少分成 On-CPU、Runnable Waiting、Blocking Wait、Queueing、Hardware Service 和 Retry。
#. On-CPU 表示 Task 正在执行指令；它主要由 CPU Sampling 和 PMU 观察。
#. Runnable Waiting 表示 Task 已有运行资格但尚未获得 CPU；它需要 Scheduler Event 观察。
#. Blocking Wait 表示 Task 等待锁、I/O、Timer、Memory、Socket 或其它事件。
#. Queueing 表示工作已经进入某个服务队列但尚未开始处理。
#. Hardware Service 表示设备已经接管请求并执行 DMA、存储或链路传输。
#. Retry 表示原工作因丢包、冲突、错误恢复、回收失败或协议条件被重复执行。
#. 同一请求的墙钟时间可以同时包含多类成本，不能用单一工具覆盖全部阶段。
#. CPU Profile 只观察采样时正在 CPU 上运行的代码，不能直接看到完整 Off-CPU 时间。
#. Scheduler Trace 能证明 Wakeup、Switch 和 Runnable Waiting，不能单独解释硬件服务时间。
#. Block Trace 能证明 Request 阶段，不能覆盖进入块层前的文件系统锁和 Dirty Throttling。
#. Packet Counter 能说明某层事件数量，不能单独证明端到端业务延迟来源。
#. 延迟回答一个工作单元完成需要多久。
#. 吞吐回答单位时间完成多少工作。
#. 利用率回答资源有多长时间处于忙碌状态。
#. 饱和度回答是否已有额外工作等待资源服务。
#. 错误率回答系统是否通过失败、Drop、Timeout 或 Retry 维持表面吞吐。
#. 利用率高不自动等于饱和；现代并行设备可以高利用率且低延迟。
#. 利用率不高也不排除局部饱和，单 CPU、单 Queue、单 NUMA Node 或单锁可能已经满载。
#. CPU 总利用率 70% 不能证明目标请求有 30% CPU 余量。
#. 平均值掩盖尾部，性能工程必须保留 Histogram、``p95``、``p99`` 和最大值。
#. ``p99`` 变化必须结合样本量和相同负载窗口解释。
#. 吞吐下降可能来自服务能力下降，也可能来自上游输入下降，必须同时记录请求到达率。
#. Queue Length 是饱和线索，必须结合服务率和等待时间解释。
#. Little's Law 适用于稳定系统中的平均关系，不能用来隐藏瞬时 Burst 和尾部异常。
#. Counter 是累计事实，Rate 是两个时间点 Counter 的差值除以时间。
#. 单次读取 ``/proc`` 或 ``/sys`` Counter 不能说明最近一分钟发生了什么。
#. Counter Reset、Wrap、设备重置、Namespace 重建和进程重启会破坏时间序列连续性。
#. 每次采集必须记录 Kernel、Boot ID、PID/TID、Cgroup、CPU、Device、Interface 和时间范围。
#. PID 会复用，长时间调查还需要进程启动时间、容器实例或业务 Generation。
#. 多工具关联前必须确认 Clock Source、时间单位、时区和采样窗口。
#. 应用时间、Trace Clock、Perf 时间、设备时间和远端抓包时间未必天然对齐。
#. 业务请求 ID、Trace ID 或 Marker 能把内核事件放回具体请求，但 Marker 本身也有开销。
#. 相关性只说明两个现象同时变化，不自动证明一个导致另一个。
#. 因果证据通常来自路径顺序、对象关系、受控修改和同口径复测的共同支持。
#. 基线必须覆盖正常窗口，而不只是故障窗口中的当前值。
#. 基线应记录负载、延迟分布、吞吐、错误、资源统计和 Kernel/Firmware 配置。
#. 正常与异常窗口必须具有可比负载，否则差异可能只是请求类型或并发不同。
#. 每请求成本比整机总量更适合跨吞吐窗口比较，例如 Cycles/Request、Bytes/Request、Faults/Request。
#. 多租户系统还要记录邻居负载、Cgroup、NUMA 和共享设备变化。
#. 性能问题经常是阶段迁移：调大 Buffer 可能把 Drop 转成 Queueing，把前台延迟转成后台回收。
#. 调大 Queue Depth 可能提高吞吐，也可能增加 Tail Latency 和超时恢复成本。
#. 调大线程池可能增加 Runqueue、Lock Contention、Cache Miss 和上下文切换。
#. 调大 Timeout 不会修复丢失 Completion，只会延迟故障暴露。
#. 降低安全检查可能减少 CPU 成本，同时改变系统威胁模型，不能作为普通调优处理。
#. 测量工具本身会扰动系统；Printk、Function Graph、全量 Trace 和高频 Sampling 都有成本。
#. 应先使用低成本聚合指标，再逐步缩小到 Tracepoint、Sampling 和函数级追踪。
#. 观测范围应限制到目标 PID、CPU、Cgroup、Device、Queue、Interface 或短时间窗口。
#. 采集前要定义停止条件，防止 Trace Buffer、Perf Data 或日志占满存储。
#. 只有在测量口径、负载、观察工具和时间窗口一致时，修改前后结果才可比较。
#. 修复后应先确认中间状态按假设变化，再确认用户可见指标改善。
#. 参数值变了而中间状态没变，通常说明作用域、生命周期或对象选择错误。
#. 中间状态改变而业务不改善，说明该路径不是主瓶颈或下游出现新的瓶颈。
#. 平均延迟改善但 ``p99``、错误率或资源压力恶化，不应判定为成功。
#. 吞吐提高但丢包、重传、OOM、Recovery 或邻居工作负载恶化，也不应判定为成功。
#. 性能调查的输出应包括事实、证据范围、版本边界、结论置信度和未解释部分。
#. 不可复现问题仍可通过长期低成本 Counter、Histogram、Trace Trigger 和 Crash Evidence 建立下一次证据。
#. 读源码时应先找运行证据对应的对象和事件，再从对象进入函数路径。
#. 只看源码能证明路径存在，不能证明本次故障实际经过该路径。
#. 只看运行工具能证明事件发生，不能自动解释对象语义和生命周期。
#. 稳定工程顺序是：用户症状 → 请求时间分解 → 资源/队列定位 → 内核对象 → 源码路径 → 最小验证。

必背路径
--------

通用性能调查：

::

   固定用户可见症状和时间窗口
   → 记录负载、延迟分布、吞吐与错误
   → 把墙钟时间拆成 On-CPU / Runnable / Blocking / Queue / Service / Retry
   → 提出对象级路径假设
   → 为每个阶段选择最小测量点
   → 收集同一时钟和同一范围内的证据
   → 找到最早出现饱和或等待的对象
   → 执行一个最小修复
   → 按原口径复测中间状态与业务结果

请求时间分解：

::

   Request Arrival
   → User-space Queue
   → On-CPU User Work
   → Syscall / Kernel Work
   → Runnable Waiting 或 Blocking Wait
   → Subsystem Queue
   → Device / Network Service
   → Completion 与 Wakeup
   → User-space Completion
   → Response

证据选择：

::

   怀疑 CPU 执行
   → perf stat / record / report / PMU

   怀疑等待 CPU
   → sched_wakeup + sched_switch + Runqueue / PSI

   怀疑锁或事件等待
   → Lock/Event Trace + Off-CPU Stack + Owner Object

   怀疑存储
   → Writeback + Block Submit/Issue/Complete + Device Stats

   怀疑网络
   → NIC Queue + IRQ/NAPI + Stack Drop + Socket Queue + Application

最小修复验证：

::

   保存原始配置和基线
   → 明确修复预计改变的中间指标
   → 只修改一个关键变量
   → 保持负载与观测方式一致
   → 验证中间指标是否按假设变化
   → 验证 p99、吞吐、错误和副作用
   → 回滚或固化

必须区分
--------

* On-CPU 与 Off-CPU：前者是执行，后者包括等待、睡眠、排队和节流。
* Runnable 与 Running：Runnable 已具备运行资格，Running 才真正占用 CPU。
* 利用率与饱和度：资源忙不等于已有工作排队，局部排队也可能被整机平均值隐藏。
* 延迟与吞吐：单请求时间和单位时间完成量属于不同目标。
* Counter 与 Rate：累计值必须通过时间差转换成当前速率。
* 平均值与尾部：平均稳定不能证明少数请求没有严重长尾。
* 相关性与因果：同时变化需要路径顺序和受控实验才能升级为因果结论。
* 路径存在与路径发生：源码证明可能，运行 Trace 证明当前窗口实际记录。
* 工具输出与业务结论：样本、事件和 Counter 必须放回对象及请求语义解释。
* 参数回读与修复成功：控制面新值不证明下游行为和用户结果已经改善。

一句话结论
----------

内核性能工程不是根据总利用率猜瓶颈，而是把每个慢请求拆成执行、等待、排队、服务和重试，并用对象级证据验证最小修复。

来源
----

* 教材：AIBook Linux Kernel
* Part：Part 36 — Kernel Performance Engineering for CPU, Memory, I/O, Network, and Lock Contention
* 章节：Chapter 176 — Building a Kernel Performance Investigation Model
* 源文件：``docs/LinuxK/Part_36_Kernel_Performance_Engineering_for_CPU_Memory_IO_Network_and_Lock_Contention/Chapter_176_Building_a_Kernel_Performance_Investigation_Model.md``
* 固定版本：`18386764582829f2b807b7b0947785eb77b50446 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_36_Kernel_Performance_Engineering_for_CPU_Memory_IO_Network_and_Lock_Contention/Chapter_176_Building_a_Kernel_Performance_Investigation_Model.md>`_
