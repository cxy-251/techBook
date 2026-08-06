第173章：perf：CPU、Scheduler 与 Kernel Hot Paths
================================================

核心知识点
----------

``perf`` 统一多类事件源
   ``perf_events`` 通过 ``perf_event_open()`` 把硬件 PMU、软件事件、Tracepoint、Kprobe/Uprobe 等表示为可计数、采样和关联的 Event 对象。

Counting、Sampling 与时间线回答不同问题
   ``perf stat`` 统计事件总量；``perf record/report`` 观察样本集中位置和调用链；调度、锁与 Tracepoint 记录用于还原事件关系。

Event Scope 决定百分比含义
   Event 可绑定 Task、Thread、CPU、Cgroup 或整机。不同 Scope、CPU 集合、过滤条件和时间窗口下的 Overhead 不能直接比较。

采样比例不是精确函数耗时
   Cycles Sample 表示样本落点分布。短窗口、低频事件、采样周期和丢失记录都会影响比例，不能把百分比机械解释为函数消耗相同比例的 Wall Time。

Flat Hotspot 需要调用链解释
   同一底层函数可能来自多个子系统。必须结合 Caller/Callee、对象路径和工作负载，才能把锁 Slowpath、复制函数或页面操作归因到具体机制。

符号和调用栈是分析前提
   Kernel ``vmlinux``、Kallsyms、Module Debuginfo、Build ID、KASLR 和 Unwinder 必须匹配。``[unknown]`` 或断裂 Stack 表示证据不足。

On-CPU 与 Off-CPU 必须分开
   Cycles 主要观察正在 CPU 上运行的代码；I/O、睡眠锁、调度等待和 Cgroup Throttle 需要 Scheduler、Lock、Block 或应用事件补充。

调度延迟来自 Wakeup 到 Switch-in
   ``sched_wakeup`` 与 ``sched_switch`` 可估算 Runnable Waiting。长等待还要结合 Runqueue、Priority、Affinity、IRQ、CPU Offline 和 Cgroup Quota。

锁热点需要具体锁对象
   自旋 Slowpath 热点只证明 CPU 在等待；睡眠锁事件只证明 Task 被阻塞。根因必须连接锁地址、Owner、Waiter、持有路径和临界区。

PMU 是微架构证据
   Cycles、Instructions、Cache/TLB/Branch Event 必须按 CPU 型号和事件定义解释。通用名称不保证跨平台测量同一硬件现象。

Multiplexing 会产生缩放估计
   硬件 Counter 数量有限，Event Group 过多时会时间复用。``time_enabled``、``time_running`` 和 Scale 必须进入结果可信度判断。

性能结论必须按工作量归一化
   比较应同时记录吞吐、延迟、总 Cycles、Instructions、Context Switch 和每请求成本。函数占比升高可能只是其它路径减少。

关键路径
--------

CPU 热点定位：

::

   固定 Kernel、Workload、CPU 和时间窗口
   → perf stat 建立事件总量基线
   → 选择目标 Event 与 Scope
   → perf record 保存短时样本和 Call Graph
   → perf report 定位 Symbol 与调用来源
   → 回到源码和对象路径解释
   → 使用相同配置复测

调度等待分析：

::

   记录 sched_wakeup / sched_switch / migration
   → 按 TID、CPU 和时间戳关联
   → 计算 Wakeup 到 Switch-in
   → 区分 Runnable Waiting 与 Blocking Sleep
   → 检查 Runqueue、Priority、Affinity 与 Cgroup Throttle

锁竞争分析：

::

   Cycles 或 perf lock 发现等待热点
   → 展开等待者调用链
   → 定位具体 Lock 对象
   → 找 Owner 与持有路径
   → 测量等待次数、等待时间和临界区
   → 验证共享状态和 Cacheline 竞争

概念辨析
--------

* Counting 与 Sampling：Counting 给出总量；Sampling 给出事件在代码和调用链中的分布。
* Overhead 与绝对成本：Overhead 是当前聚合下的样本比例，不等于绝对 CPU 时间变化。
* On-CPU 与 Off-CPU：前者观察正在执行的代码；后者需要调度、锁、I/O 等等待事件。
* PMU 通用名与硬件事件：相同名称在不同 CPU 上的底层定义和精度可能不同。
* Hotspot 与根因：热点是源码阅读入口，只有连接对象、调用来源和系统状态后才形成原因。

本章结论
--------

``perf`` 把性能问题拆成事件总量、样本落点、调用来源、调度等待和硬件成本；任何热点结论都必须建立在正确 Scope、匹配符号和可比较工作负载上。