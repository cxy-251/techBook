第172章：ftrace、Function Graph Tracing 与 Tracepoints
====================================================

本章必须记住
------------

#. ftrace 是 Linux 内核内置的运行时追踪框架，用来证明某条函数路径、状态事件或延迟窗口在实际运行中发生过。
#. ftrace 不只是 Function Tracer；它还承载 Function Graph、静态 Tracepoint、Event Tracing、Latency Tracer、Filter、Trigger、Instance、Snapshot 与 Boot-time Tracing。
#. 源码说明某条路径“可能存在”，Trace 记录说明该路径在当前 Kernel、配置、过滤器和时间窗口中“被实际记录”。
#. tracefs 通常挂载在 ``/sys/kernel/tracing``；旧系统可能通过 ``/sys/kernel/debug/tracing`` 提供兼容入口。
#. ``available_tracers`` 列出当前内核可用 Tracer；``current_tracer`` 选择当前 Tracer；``tracing_on`` 控制是否继续写 Ring Buffer。
#. ``trace`` 是可重复读取的缓冲快照；``trace_pipe`` 是消费式实时流，读取后记录不会以相同方式继续保留。
#. ``tracing_on=0`` 主要停止写入 Ring Buffer，不保证所有已启用探针和事件完全没有运行开销。
#. 追踪前必须明确问题类型：函数是否进入、调用嵌套和耗时、对象状态事件、调度时间线、启动期路径或最大延迟。
#. Function Tracer 回答“哪些函数入口被命中”。
#. Function Graph Tracer 回答“某个入口内部调用了什么、嵌套关系和可见返回耗时是多少”。
#. Tracepoint Event 回答“某个子系统定义的状态变化发生时，关键字段是什么”。
#. Function Trace 依赖编译器插桩、架构支持和 Ftrace 配置；不是所有函数都可追踪。
#. ``available_filter_functions`` 是当前可被 Function Tracer 过滤选择的重要运行时列表。
#. ``set_ftrace_filter`` 选择要记录的函数集合；``set_ftrace_notrace`` 排除函数。
#. Function Graph 可用 ``set_graph_function`` 限制展开入口，用 ``set_graph_notrace`` 排除子树，精确接口依版本而定。
#. 不设置过滤器直接追踪全部函数会产生巨大数据量和明显运行扰动。
#. 正确顺序是：停止记录 → 选择最小函数/事件 → 清空旧缓冲 → 开始记录 → 运行最小负载 → 停止记录 → 保存 Trace。
#. 清空 ``trace`` 只清除当前 Instance 的记录，不会自动关闭已启用 Event、Tracer 或 Probe。
#. Function Tracer 输出中的 Task、PID、CPU、Flags、Timestamp、Function 与 Caller 是解释入口的基本字段。
#. 函数名出现只证明该入口被记录，不证明它是性能瓶颈，也不证明其所有分支都执行。
#. Caller 字段或调用图提供入口来源，但受编译优化、Tail Call、Inline、No-trace 标记和架构 Unwinder 影响。
#. Function Graph 的 Duration 是追踪配置下的观测时间；它可能包含被抢占、中断、调度切出或 Tracer 自身成本。
#. 不能把 Function Graph 某一行 Duration 直接当成函数纯 CPU 执行成本。
#. Graph 缩进表示记录到的调用包含关系，不自动表达对象所有权或同步因果。
#. ``max_graph_depth`` 可限制展开深度，减少数据量和开销。
#. 函数过滤器应从明确入口开始，例如失败系统调用、驱动 Probe、Block Request 或网络收包函数。
#. 对极高频函数追踪时应缩小到特定 PID、CPU、Cgroup、Event Trigger 或短窗口。
#. 静态 Tracepoint 是源码中预先定义的稳定事件 Hook，关闭时通常只有极低条件检查成本。
#. Tracepoint 名通常采用 ``subsystem:event``，例如 ``sched:sched_switch``、``block:block_rq_issue``、``net:*``。
#. ``available_events`` 列出可用事件；``events/<system>/<event>/format`` 描述字段、类型与 Print Format。
#. 解释 Event 前必须先读 ``format``，不能凭输出列名猜测字段单位与语义。
#. Event ``enable`` 控制记录；``filter`` 根据事件字段筛选；``trigger`` 可在事件发生时执行 Snapshot、Stacktrace、Enable/Disable 其它 Event 等动作。
#. Event Filter 比录制后 grep 更可靠，因为它在写入 Ring Buffer 前减少无关事件和开销。
#. Filter 字段必须来自该 Event 的 ``format``；不同内核版本字段可能新增、改名或改变布局。
#. Tracepoint 是面向内核与工具的事件 ABI，但稳定性需按具体事件文档判断，不能假设所有字段永久不变。
#. 同名 Tracepoint 在不同 Kernel Release 上可能具有不同字段集合，自动化应保存 Kernel Release 与 Event Format。
#. 调度问题通常需要同时观察 ``sched_wakeup``、``sched_wakeup_new``、``sched_switch``、迁移或 Runtime 事件。
#. ``sched_switch`` 说明 CPU 从 Prev Task 切到 Next Task，不直接说明 Prev 为什么长期未运行。
#. Wakeup 到实际 Switch-in 的时间差可以估算调度等待，但必须用 Task Identity、CPU 和时间戳正确关联。
#. PID 会复用；长时间采集还应保存 Comm、Start/Generation、Cgroup 或业务实例信息。
#. Block I/O 需要把 Submit、Insert、Issue、Complete 等事件按 Request/Device/Sector/时间线关联。
#. 网络 Tracepoint 只覆盖其定义点，Drop 还可能发生在 NIC、Driver、NAPI、协议栈、qdisc、Socket 或对端。
#. Power、IRQ、Workqueue、RCU、Memory、Filesystem 等子系统也有各自事件族，应从对象路径选择事件。
#. Tracepoint 记录发生在当前执行上下文中；字段获取、Ring Buffer 写入和 Stacktrace Trigger 会增加热路径成本。
#. Event 打开成功不表示工作负载触发了它；没有记录时要检查路径、Filter、CPU Buffer、Instance 和时间窗口。
#. Per-CPU Ring Buffer 能降低全局锁竞争，但读取时需要按时间戳合并多个 CPU 记录。
#. 多 CPU 时间戳通常可比较，但 Clock Source、Trace Clock 与跨 CPU 同步方式必须确认。
#. ``trace_clock`` 选择 Local、Global、Mono、Boot 等时间基准，具体可用项依内核而定。
#. 改变 Trace Clock 会影响时间解释，采集记录必须保存所用 Clock。
#. Ring Buffer 容量有限；高频事件会覆盖旧记录。
#. Buffer 覆盖意味着 Trace 中最早记录不再存在，不能把现存第一行当作事件真正起点。
#. ``buffer_size_kb``、Per-CPU Size 和 Overwrite 模式影响保留窗口与内存成本。
#. 扩大 Buffer 只能延长保存窗口，不能修复无边界事件选择。
#. Snapshot 用于在 Trigger 条件满足时冻结一份缓冲副本，适合捕获罕见异常前后的短现场。
#. Trigger 可在某 Event 上执行 ``snapshot``、``stacktrace``、``traceon``、``traceoff`` 或启停其它 Event；精确语法有版本差异。
#. Trigger 的工程价值是让异常自身控制采集窗口，避免长期全量追踪。
#. 设计 Trigger 时要验证触发次数、重入、Buffer 容量和清理方式。
#. Trace Instance 提供独立 Buffer 与控制目录，使多个诊断任务可以隔离 Tracer、Event 和 Filter。
#. Instance 隔离追踪配置，不隔离被观测内核路径，也不消除多个 Tracer 对系统的总开销。
#. 删除 Instance 前应关闭 Tracing、Event 和 Probe，停止读取者并保存结果。
#. Boot-time Tracing 用于普通用户态尚未启动前的初始化、Initcall、设备 Probe 和早期延迟。
#. Bootconfig/Ftrace Boot 配置可在内核启动时建立 Instance、Event、Filter 与 Trigger，语法随版本演进。
#. 启动期追踪必须提前预留 Buffer 并控制事件量，否则可能增加启动时间或覆盖关键早期记录。
#. Function Tracer 与 Kprobe 不同：Function Tracer依赖可追踪函数插桩；Kprobe 可在更多指令位置建立动态探针，但风险和限制更高。
#. Static Tracepoint 与 Kprobe 不同：Tracepoint 字段由子系统作者定义；Kprobe 需要分析寄存器、参数和版本相关结构。
#. ftrace 与 eBPF 可以共享 Tracepoint、Kprobe 等 Attach Point，但 Program、Map、Verifier 和输出机制属于 eBPF 体系。
#. ftrace 与 perf 也可共享 Tracepoint 数据源；ftrace 更适合直接路径时间线，perf 更适合采样、计数和聚合。
#. Trace Output 是观测结果，不是完整真实世界。Filter、Dropped Event、Overwrite、Disabled CPU 和工具读取速度都会造成缺口。
#. 不能看到函数不等于函数没执行；它可能被 Inline、Notrace、优化、过滤或当前 Tracer 不支持。
#. 看到函数执行也不等于它造成故障；必须结合对象字段、返回值、事件顺序和用户症状。
#. Tracing 会改变时序，尤其对锁竞争、竞态、IRQ、NMI 和微秒级延迟问题。
#. Heisenbug 场景应从低成本 Event/Counter 开始，再逐步增加 Function/Graph/Stacktrace。
#. 追踪目标应以问题假设驱动，例如“Task 被唤醒后在 Runqueue 等待”或“Request 在 Issue 前排队”。
#. 没有明确问题的全量 Trace 通常得到不可解释的大量数据。
#. 采集前应记录 Kernel Release、Config、Tracefs Mount、Current Tracer、Enabled Events、Filters、Clock、Buffer Size 和 Instance。
#. 采集后应立即保存 ``trace``、Event Format、配置文件和工作负载时间窗口。
#. Trace 文本通常不是跨版本稳定机器 ABI；长期工具应使用 Perf Data、Trace-cmd、libtraceevent 或正式接口并保留元数据。
#. ``trace-cmd`` 可封装 Event 录制和 ``trace.dat`` 保存，但底层判断仍是 Tracepoint、Buffer、Filter 与时间线。
#. ``kernelshark`` 等可视化只能帮助浏览记录，不能替代对象和源码语义。
#. Tracefs 写操作通常需要特权，并受 Lockdown、Securityfs、Mount Namespace 和 LSM 限制。
#. 容器中看到的 Tracefs 常被隐藏或只读；容器内 Root 不等于可追踪宿主全局内核。
#. 生产系统追踪应限定 Owner、窗口、对象范围、最大数据量和自动回滚。
#. 忘记关闭 Function Tracer 或高频 Event 会形成持续性能回归，应监控 Tracing 状态漂移。
#. 关闭顺序通常是：``tracing_on=0`` → Disable Events/Probes → ``current_tracer=nop`` → 清理 Filter/Trigger → 保存/清空 Buffer。
#. 仅设置 ``current_tracer=nop`` 不一定关闭 Event Tracing；Event Enable 状态必须单独检查。
#. 仅关闭 Event 不一定移除动态 Probe；Kprobe/Uprobe Event 还需按其控制接口注销。
#. ftrace 不提供崩溃后完整内存对象；如果系统 Panic 后无法导出 Trace，应结合 Pstore、Kdump 和 Vmcore。
#. Pstore 可保存部分 Ftrace 片段，但容量和后端配置有限，精确能力依目标系统。
#. 源码阅读顺序是：问题假设 → Tracepoint/Function 入口 → Tracefs 控制 → Filter/Trigger → Ring Buffer → 输出字段 → 返回源码对象验证。

必背路径
--------

Function Tracing：

::

   明确目标函数或入口
   → 查看 available_filter_functions
   → tracing_on=0
   → current_tracer=nop 并清空 trace
   → 写 set_ftrace_filter / set_graph_function
   → 选择 function 或 function_graph
   → tracing_on=1
   → 执行最小工作负载
   → tracing_on=0
   → 保存 trace、Clock、Filter 与 Kernel 信息

Tracepoint Event：

::

   从对象路径选择 subsystem:event
   → 读取 events/.../format
   → 设置字段 Filter
   → 清空目标 Instance Buffer
   → Enable Event 并开始记录
   → 触发工作负载
   → Disable Event
   → 按 CPU、PID、对象 ID 与时间戳关联

异常 Trigger：

::

   选择能代表异常的 Event 与字段
   → 设置 Filter
   → 配置 Snapshot/Stacktrace/Traceoff Trigger
   → 保持低成本等待
   → 异常事件触发并冻结现场
   → 保存 Snapshot 与配置
   → 删除 Trigger 并恢复状态

安全退出：

::

   tracing_on=0
   → Disable 全部目标 Event
   → current_tracer=nop
   → 清理 Function Filter、Event Filter 与 Trigger
   → 注销动态 Probe
   → 停止 trace_pipe Reader
   → 保存并删除临时 Instance

必须区分
--------

Function Tracer 与 Function Graph
   前者记录函数入口；后者记录入口、返回、嵌套和观测 Duration。

Function 与 Tracepoint
   Function 以代码入口为对象；Tracepoint 以子系统定义的结构化状态事件为对象。

``trace`` 与 ``trace_pipe``
   前者读取当前缓冲快照；后者实时消费新记录。

Filter 与事后 Grep
   Filter 在写入前缩小数据与开销；Grep 只能处理已经产生和保留下来的文本。

Ring Buffer 第一行与真实事件起点
   Buffer 可能覆盖旧数据，现存第一行不一定是故障开始位置。

Trace Duration 与纯执行时间
   Duration 可包含调度、中断、抢占与追踪开销，不能直接等同于函数 CPU 成本。

Tracer 关闭与 Event 关闭
   ``current_tracer=nop`` 不自动关闭已启用 Tracepoint Event。

路径存在与路径发生
   源码证明路径存在；运行 Trace 才证明当前窗口记录到它发生。

一句话结论
----------

ftrace 的核心价值是把“内核大概走了这条路”变成带对象、CPU 和时间线的运行证据，同时用最小过滤范围控制观测扰动。

来源
----

* 书籍：Linux Kernel AIBook；
* Part：Part 35 — Kernel Debugging, printk, Dynamic Debug, ftrace, perf, kdump, and crash；
* 章节：Chapter 172 — ftrace, Function Graph Tracing, and Tracepoints；
* 源文件：``docs/LinuxK/Part_35_Kernel_Debugging_printk_Dynamic_Debug_ftrace_perf_kdump_and_crash/Chapter_172_ftrace_Function_Graph_Tracing_and_Tracepoints.md``；
* 固定提交：``18386764582829f2b807b7b0947785eb77b50446``；
* 固定来源：``https://github.com/cxy-251/aiBook/blob/18386764582829f2b807b7b0947785eb77b50446/docs/LinuxK/Part_35_Kernel_Debugging_printk_Dynamic_Debug_ftrace_perf_kdump_and_crash/Chapter_172_ftrace_Function_Graph_Tracing_and_Tracepoints.md``。
