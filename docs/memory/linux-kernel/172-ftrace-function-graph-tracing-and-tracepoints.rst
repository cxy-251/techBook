第172章：ftrace、Function Graph Tracing 与 Tracepoints
====================================================

核心知识点
----------

ftrace 用运行记录证明真实路径
   源码只能说明某条路径可能存在；ftrace 记录说明它在当前内核、配置、过滤条件和时间窗口中实际发生。

tracefs 是控制与数据入口
   ``/sys/kernel/tracing`` 通常承载 Tracer、Event、Filter、Trigger、Instance 和 Per-CPU Ring Buffer。旧系统可能提供 Debugfs 兼容路径。

Function Tracer 记录函数入口
   它回答哪些可插桩函数被执行，以及调用者、Task、CPU 和时间戳。函数出现不表示它是瓶颈，也不证明所有分支均执行。

Function Graph 展开嵌套与返回
   Function Graph 记录调用层级和观测 Duration。Duration 可能包含抢占、中断、调度切出和追踪开销，不能直接视为纯 CPU 执行时间。

静态 Tracepoint 表达子系统事件
   ``sched:*``、``block:*``、``net:*`` 等事件由子系统作者定义字段和语义，比任意函数入口更接近稳定状态变化。

Event Format 是字段解释依据
   ``events/<system>/<event>/format`` 描述字段类型、偏移和打印格式。过滤、自动化和跨版本分析都必须保存当前 Format。

Filter 应在写缓冲前缩小范围
   Function Filter、Event Field Filter、PID/CPU/Cgroup 选择可减少无关记录。录制全部函数或全部事件通常只会制造覆盖与扰动。

Trigger 用异常本身控制采集
   Snapshot、Stacktrace、Trace-on/off 和 Event Enable/Disable Trigger 可在目标条件出现时冻结短现场，避免长期高成本追踪。

Trace Instance 隔离诊断任务
   Instance 提供独立 Buffer 和配置目录，使多个采集方案不共享控制状态。它不隔离被观测路径，也不消除总开销。

Per-CPU Buffer 不是无限历史
   高频事件会覆盖旧记录；现存第一行不一定是问题起点。Buffer Size、Trace Clock、Overwrite 和 Lost Record 都属于结果元数据。

Tracing 会改变被观察系统
   Function Graph、Stacktrace Trigger 和高频事件可显著改变 Cache、锁、中断和调度时序。竞态问题应从低成本 Counter 与 Tracepoint 开始逐步加深。

关键路径
--------

Function Tracing：

::

   明确目标入口
   → 从 available_filter_functions 验证可追踪性
   → tracing_on=0 并清空目标 Buffer
   → 设置 set_ftrace_filter / set_graph_function
   → 选择 function 或 function_graph
   → 短时运行目标负载
   → tracing_on=0 并保存 Trace 与配置

Tracepoint Event：

::

   从对象路径选择 subsystem:event
   → 读取 Event Format
   → 设置字段、PID、CPU 或 Cgroup Filter
   → Enable Event
   → 触发工作负载
   → Disable Event
   → 按对象 ID、CPU 和时间戳关联记录

异常捕获：

::

   选择代表异常的 Event
   → 设置精确 Filter
   → 配置 Snapshot / Stacktrace / Traceoff Trigger
   → 等待异常触发
   → 冻结并保存现场
   → 删除 Trigger、关闭 Event、恢复 Tracer

概念辨析
--------

* Function Tracer 与 Function Graph：前者记录入口；后者记录嵌套、返回和观测 Duration。
* Function 与 Tracepoint：Function 面向代码入口；Tracepoint 面向子系统定义的结构化事件。
* ``trace`` 与 ``trace_pipe``：前者读取当前缓冲快照；后者以流式方式消费新记录。
* Filter 与录制后 grep：Filter 在写入前减少事件和开销；grep 只能处理已经产生的数据。
* Trace 记录与完整事实：记录仍受过滤、覆盖、时钟、插桩和观测扰动限制。

本章结论
--------

ftrace 把路径猜测转换为带 CPU、Task、对象和时间线的运行证据；可靠使用依赖最小过滤范围、明确事件语义和对观测扰动的控制。