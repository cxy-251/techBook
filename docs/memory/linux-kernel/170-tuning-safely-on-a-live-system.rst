第170章：在运行系统上安全调优
==============================

本章必须记住
------------

#. Live Tuning 的本质是对正在运行的内核执行一次可观测、可回滚、可复盘的受控实验。
#. 参数修改只是实验中间步骤；基线、假设、作用域、验证、停止条件和回滚共同构成完整闭环。
#. “系统慢”不是可执行结论，必须拆成延迟、吞吐、利用率、饱和、错误率和资源等待。
#. 调优前必须先确定用户可见症状、目标负载、故障时间窗口和怀疑的内核路径。
#. 不应先搜索“最佳 sysctl”，再把参数套到当前机器。
#. 同一个参数在数据库、日志服务、桌面、网络网关和容器节点上可产生完全不同结果。
#. 调优结论只在特定 Kernel、Hardware、Firmware、Workload 和配置组合下成立。
#. 修改前至少记录 Kernel Version、Boot ID、机器拓扑、设备、负载和当前参数值。
#. 基线必须覆盖业务指标与内核指标，不能只看系统平均值。
#. 业务基线可包括请求速率、并发、p50/p95/p99、超时、错误和队列长度。
#. 内核基线应按假设选择 CPU、Scheduler、Memory、I/O、Network、Lock 和 PSI 证据。
#. ``/proc/meminfo`` 提供内存快照，``/proc/vmstat`` 提供累计事件；两者不能互相替代。
#. ``/proc/diskstats`` 提供块设备累计统计，不直接给出某个应用请求的端到端延迟。
#. PSI 表示任务因资源压力失去运行进展的时间，不等于硬件利用率。
#. ``dmesg`` 中的 Reset、Timeout、OOM、Warn 和 Error 会污染调优实验，必须先排除故障。
#. 单次 ``cat`` 是快照；计数器需要按固定间隔采样并计算增量或速率。
#. 修改前后必须处于可比较负载，负载自然下降不能被误判为参数收益。
#. 对周期性业务，应覆盖至少一个完整周期或采用可重复压测。
#. 性能假设应写成路径关系，例如“Dirty Page 积累导致 Writeback Burst，进而抬高块层排队和写 p99”。
#. 一个可测试假设必须指出参数影响哪个中间状态和哪个可观测指标。
#. 没有中间证据的“改值后更快”无法区分因果、噪声和偶然变化。
#. 一次只修改一个关键变量，是保持因果可识别性的基本要求。
#. 同时修改多个 sysctl、队列、线程数和应用策略，会让收益来源无法解释。
#. 单变量并不意味着只观察一个指标；必须同时监控目标收益和副作用。
#. 每个实验单元应记录参数、原值、新值、预期作用、观察窗口、停止条件和回滚命令。
#. 原值必须从当前运行系统读取，不能从文档默认值或配置文件猜测。
#. 新值必须落在文档范围和硬件/子系统可支持范围内。
#. 参数单位、特殊值和相关参数优先级必须提前确认。
#. 写入前应验证目标路径属于预期 Namespace、Device、Queue、Module 或 Cgroup。
#. 在容器中修改一个 Netns sysctl，不能当作宿主全局网络调优。
#. 修改 Device Sysfs 属性前应核对真实设备、Serial、Major:Minor、BDF 或规范路径。
#. 参数 Scope 可分为全局、Namespace、Cgroup、设备、队列、模块和进程。
#. 参数 Lifetime 可分为启动期、模块加载期、对象创建期、周期读取和每次热路径读取。
#. 参数 Reversibility 回答写回旧值是否足够，还是需要重建对象、Reload、Reset 或重启。
#. 参数 Persistence 回答重启、模块重载、设备重枚举和 Namespace 重建后由谁重新应用。
#. 修改运行时值前必须知道它是否被 Config Manager、Systemd、Network Manager 或 Runtime 持续管理。
#. 手工写入受管理参数可能很快被自动化覆盖，造成状态震荡。
#. 生产修改应通过正式变更流程记录 Owner、目的、时间、影响范围和回退责任。
#. 高风险写入应先在 Staging、Canary 或单个实例验证。
#. 远程系统必须准备 Console/BMC、健康检查和自动回滚，不能只依赖同一网络路径。
#. 修改可能影响 SSH、Route、Memory、I/O 或 Console 时，失联本身就是必须设计的失败模式。
#. 回滚命令应在修改前准备并验证语法。
#. 停止条件应使用明确阈值，例如错误率、p99、PSI、OOM、Drop、Reset 或健康检查失败。
#. 达到停止条件后应立即回滚，而不是继续等待“也许会稳定”。
#. 调优时间窗口内应冻结无关发布、扩缩容、流量切换和硬件维护。
#. 无法冻结时，必须记录所有并发变化并降低结论置信度。
#. Sysctl 写入成功只证明 Handler 接受输入。
#. Sysfs Store 成功只证明对象回调接受请求。
#. Module Parameter 新值可只影响后续 Probe。
#. Debugfs 写入可能触发实验动作，没有稳定回滚语义。
#. 每种接口都必须通过对应下游状态验证，而不是只回读文件内容。
#. 写回调返回前可能已经完成状态切换，也可能只排队异步工作。
#. 异步调优需要等待 Completion/Event，并在超时后检查半配置状态。
#. 修改队列深度时应观察实际 In-flight、Queueing、Memory Footprint、Throughput 和 p99。
#. 队列更深可提高设备利用率，也会增加排队时间和尾延迟。
#. 调大 Backlog 可减少短时 Drop，也会增加内存和等待。
#. 调大 Socket Buffer 可提高高带宽时延积利用，也会扩大每连接内存和排队。
#. 调大 Timeout 可减少误判，也会延长真实故障恢复。
#. 调大 Retry 可掩盖瞬态错误，也可能形成请求放大和风暴。
#. CPU 参数调优前应区分 On-CPU Hot Path、Runqueue Waiting、Quota Throttle 和 IRQ/Softirq 压力。
#. CPU 利用率低不表示没有 CPU 瓶颈；单核、Affinity、Lock 或 Cgroup 限制都可造成局部饱和。
#. 调度参数改变公平性与延迟时，必须观察其它工作负载是否被饿死。
#. VM 调优前应区分容量不足、Working Set Miss、Reclaim、Compaction、Writeback、Swap 和 NUMA 远端访问。
#. 降低 Swappiness 不会增加物理内存，也不能修复内存泄漏。
#. Drop Caches 会破坏 Cache 基线，不能作为常规生产内存优化。
#. Dirty 参数会改变 Page Cache 中延迟积累位置，可能把前台快写转成后续突发回写。
#. 内存参数收益必须同时观察 I/O、PSI 和应用尾延迟。
#. I/O 调优前应拆开应用等待、文件系统、Writeback、块层排队、设备服务和错误恢复。
#. 设备 Util 高不必然是瓶颈，现代并行设备可在高利用率下保持低延迟。
#. 设备 Util 低也不排除单队列、限速、Flush、Lock 或上层串行化。
#. Scheduler、Queue Depth、Read-ahead 和 Writeback 参数应结合实际设备类型与访问模式。
#. NVMe、网络块设备、RAID、Device Mapper 和虚拟磁盘不能套用同一参数经验。
#. 网络调优前应定位 Drop 和 Queue 发生在 NIC、Driver、NAPI、协议栈、qdisc、Socket 还是应用。
#. 增大 ``netdev_max_backlog`` 之类参数不能修复 NAPI CPU 不足或应用消费慢。
#. TCP Buffer 和 Congestion 参数需要结合 RTT、BDP、Loss、Pacing 和对端行为。
#. 只优化吞吐可能恶化交互流量的 Tail Latency。
#. 安全参数不是普通性能旋钮。
#. 关闭 Mitigation、LSM、IOMMU、Audit 或权限限制会改变威胁模型，必须单独评审。
#. 安全退让带来的性能收益不能只用业务延迟衡量，还要记录攻击面变化。
#. Debug 开关和 Trace 也会改变性能；测量工具开销必须纳入基线。
#. Function Graph、全量 Tracepoint、Audit 和高频 Printk 可显著扰动热路径。
#. 先使用低成本聚合统计，再逐步启用精确追踪。
#. 追踪窗口应尽量短，过滤到目标 PID、CPU、设备、Cgroup 或事件。
#. 对比实验必须使用相同观测配置，否则工具开销差异会污染结果。
#. 参数修改后首先确认实际值和目标对象状态。
#. 然后确认预期中间变量按假设变化。
#. 最后确认用户可见指标改善且副作用可接受。
#. 若中间变量未变化，说明参数作用域、生命周期或实现假设错误。
#. 若中间变量变化但业务不改善，说明该路径不是主瓶颈或存在新的下游瓶颈。
#. 若业务改善但副作用恶化，需按服务目标权衡，而不是只报告平均值提升。
#. 平均延迟下降而 p99 上升通常不是成功。
#. 吞吐提升但错误、Drop、OOM 或 Recovery 变差也不是成功。
#. 多租户系统要观察邻居工作负载，不能把资源从别人抢走当作整机优化。
#. Cgroup、NUMA、IRQ Affinity 和共享设备会让局部参数影响其它租户。
#. Canary 结果不能直接代表全量，规模扩大后锁、队列和 Cache 行为可能非线性变化。
#. 扩大实验应分阶段进行，每阶段重新确认基线和停止条件。
#. 调优成功后应形成可重复配置，而不是保留人工 Shell 历史。
#. 持久化前要验证重启、模块重载、设备热插拔和服务重启后的应用顺序。
#. 配置应注明适用 Kernel/Hardware/Workload 范围和回滚值。
#. 调优原因和证据应与配置放在同一版本管理中。
#. 参数升级审查必须检查默认值、单位、废弃、替代接口和实现变化。
#. 新内核可能已修复旧问题，使历史参数成为负优化。
#. Firmware 和驱动升级也会改变 Queue、Power、Interrupt 和 Error Recovery 行为。
#. 持续监控应验证收益仍存在，并识别 Workload 演化。
#. 参数不是“一次设置永久正确”；容量、流量和硬件变化会使最优点移动。
#. 若调优只在异常窗口有效，可考虑自动控制，但必须避免振荡和反馈失稳。
#. 自动调参需要清晰 Sensor、Controller、Actuator、Bound 和 Fail-safe。
#. 不应让多个控制器同时写同一个参数而无协调。
#. 回滚后应继续观察足够窗口，确认系统真实恢复而非仅参数文本恢复。
#. 设备或协议状态若无法在线恢复，应执行受控 Reload/Reset/Restart。
#. 修改造成数据完整性风险时，优先停止写入和保护数据，不应继续追求性能证据。
#. 调优失败记录同样有价值，应保存假设、值、时间线和为什么无效。
#. 负结果可以防止团队重复进行同一无效实验。
#. 性能回归测试应覆盖已固化参数，避免应用或内核升级后悄然失效。
#. 关键参数应设置配置漂移监控。
#. 诊断当前异常时先确认参数是否被意外修改，而不是默认其仍为基线值。
#. 参数变更事件应关联 Audit、Configuration Management 和部署 Generation。
#. Live Tuning 不能修复所有问题；代码缺陷、容量不足、坏硬件和错误架构应回到根因层处理。
#. 参数只能改变已有机制的策略边界，不能创造不存在的并行度、内存或设备能力。
#. 正确终点可能是“保持默认值”，因为测量表明参数不是瓶颈。
#. 稳定调优流程是：症状 → 路径假设 → 基线 → 单变量 → 验证 → 回滚/固化 → 长期复查。
#. 精确工具字段、参数、统计和回滚行为具有内核版本、设备与发行版差异。
#. 稳定源码阅读顺序是：Tunable Interface → Parse/Store → Scope/Lifetime → Subsystem Use → Metrics → Rollback/Teardown。

必背路径
--------

受控实验：

::

   固定业务症状和时间窗口
   → 建立应用与内核基线
   → 提出参数到路径的可验证假设
   → 确认 Scope、Lifetime、Reversibility、Persistence
   → 保存原值并准备停止条件
   → 一次修改一个变量
   → 观察中间状态、目标指标和副作用
   → 回滚或进入下一阶段

写回延迟实验：

::

   记录请求率、p99、Dirty/Writeback、vmstat、I/O PSI、diskstats
   → 排除设备 Error/Reset
   → 选择一个 Writeback Tunable
   → 保存旧值并写入测试值
   → 保持同类负载窗口
   → 比较脏页峰值、设备排队、读写延迟与错误
   → 无收益或副作用超限则立即回滚

参数验证：

::

   回读控制文件
   → 检查目标 Namespace/Device/Queue 实际状态
   → 验证假设中的中间变量发生变化
   → 验证业务指标改善
   → 验证邻居和安全副作用
   → 记录 Kernel/Hardware/Workload Generation

固化与复查：

::

   受控实验重复成功
   → 写入正式配置源
   → 记录适用范围和回滚值
   → 验证重启/Reload/Hotplug 后顺序
   → 加入配置漂移与性能回归监控
   → Kernel/Firmware/Workload 变化后重新验证

必须区分
--------

利用率与饱和
   利用率描述资源忙碌程度；饱和描述工作已经排队且无法及时获得资源。

参数值改变与路径行为改变
   文件回读新值只是控制面事实；必须验证子系统状态和业务指标。

平均改善与尾延迟改善
   平均值下降可掩盖 p99、错误和邻居工作负载恶化。

回滚参数与恢复系统
   写回旧值可能不足以撤销已创建对象、队列、连接和硬件状态。

性能调优与安全退让
   关闭保护机制改变威胁模型，不能作为普通性能参数实验处理。

一句话结论
----------

Live Tuning 是带基线、单变量、验证和回滚的内核实验；找不到可重复证据的参数修改不应被固化。

来源
----

* AIBook 书籍：LinuxK；
* AIBook Part：Part 34，Kernel Parameters, Sysctl, Control Interfaces, and Runtime Tuning；
* AIBook 章节：Chapter 170，Tuning Safely on a Live System；
* 源文件：``docs/LinuxK/Part_34_Kernel_Parameters_Sysctl_Control_Interfaces_and_Runtime_Tuning/Chapter_170_Tuning_Safely_on_a_Live_System.md``；
* `固定提交中的完整章节 <https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_34_Kernel_Parameters_Sysctl_Control_Interfaces_and_Runtime_Tuning/Chapter_170_Tuning_Safely_on_a_Live_System.md>`_。