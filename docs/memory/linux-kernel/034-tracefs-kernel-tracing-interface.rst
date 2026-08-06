第034章：tracefs 与内核追踪接口
===============================

本章必须记住
------------

#. ``tracefs`` 是 Linux tracing 框架的文件系统接口，常见挂载点是 ``/sys/kernel/tracing``。
#. ``/sys/kernel/debug/tracing`` 是常见兼容路径；使用前应确认实际挂载点和文件系统类型。
#. tracefs 把 tracer 选择、事件开关、过滤条件、触发器、ring buffer 和输出入口暴露为可读写文件。
#. 静态源码只能说明某条路径可能存在；tracing 可以证明当前机器、配置和负载下某段函数或事件实际发生过。
#. ``available_tracers`` 列出当前内核可用 tracer，``current_tracer`` 表示当前选择，``nop`` 表示不使用专用 tracer。
#. ``available_events`` 列出可用静态事件，通常使用 ``subsystem:event`` 形式。
#. ``tracing_on`` 控制是否把新记录写入 tracing buffer；关闭它不等于删除已经记录的数据。
#. ``trace`` 适合读取当前 buffer 快照，``trace_pipe`` 适合持续消费新记录。
#. tracing buffer 通常按 CPU 组织；多 CPU 事件需要结合 CPU 编号和时间戳阅读。
#. buffer 的 ``overrun``、丢弃计数和容量决定证据是否完整；没有记录可能是未发生，也可能是被覆盖或过滤。
#. function tracer 记录函数入口，适合证明某些函数在运行时被调用以及调用者关系。
#. function graph tracer 同时观察函数进入和返回，能显示嵌套关系和大致持续时间。
#. function graph 的 duration 可能包含任务睡眠、抢占或中断时间，不能直接等同于函数纯 CPU 执行成本。
#. 判断延迟时应结合 ``sched_switch``、IRQ 和其它事件，区分函数在 CPU 上执行与任务被切走等待。
#. ``available_filter_functions`` 表示当前构建中可由 ftrace 过滤的函数；函数未出现可能来自内联、优化、架构或配置限制。
#. ``set_ftrace_filter`` 缩小函数范围，``set_ftrace_notrace`` 排除函数，``set_ftrace_pid`` 限定目标进程。
#. Tracepoint 是源码中预先放置的结构化观察点；它比普通函数入口更直接表达调度、块 I/O、网络、IRQ 和内存事件语义。
#. 事件目录通常位于 ``events/<system>/<event>/``，包含 ``enable``、``format``、``filter`` 和 ``trigger``。
#. 使用事件前应先读取 ``format``，确认字段名称、类型和过滤表达式可用范围。
#. 事件过滤在内核中减少无关记录，通常比采集所有数据后在用户态筛选更节省 buffer 和处理成本。
#. Trigger 可以在满足条件时启停 tracing、保存 snapshot、记录 stack trace 或执行其它动作。
#. Tracing 是系统状态修改，会增加运行开销，并可能改变竞态、延迟和调度时序。
#. 全局 function tracing 或大量高频事件容易迅速填满 buffer；可靠做法是先限制 PID、函数、事件和持续时间。
#. 一次 tracing 实验必须保存 tracer、过滤器、事件开关、buffer 大小、内核版本和复现动作，才能重复和比较。
#. 实验结束后应关闭 tracing、恢复 ``nop``、清空过滤器和事件开关，避免后续实验互相污染。
#. trace 输出证明观察点被执行并给出局部时序，不能自动证明事件之间存在因果关系。
#. 源码解释机制，trace 给出实际路径，``/proc`` 和 sysfs 给出对象状态，日志给出异常时间线；四者应组合使用。

必背路径
--------

开始 tracing 前：

::

   找到实际 tracefs 挂载点
   → 读取 available_tracers 和 available_events
   → 明确要验证的源码判断
   → 选择函数 tracer 或结构化事件
   → 限定 PID、函数、事件和时间范围
   → 检查 buffer 容量与 per-CPU 状态

一次安全实验：

::

   关闭 tracing_on
   → 清空旧 trace buffer
   → 设置 current_tracer 或事件 enable
   → 设置函数、PID 或事件字段过滤
   → 打开 tracing_on
   → 执行一次最小复现动作
   → 立即关闭 tracing_on
   → 保存 trace、配置和环境信息
   → 清除 tracer、事件与过滤器

函数路径验证：

::

   在 available_filter_functions 确认目标函数
   → set_ftrace_pid 限定进程
   → set_ftrace_filter 限定入口
   → 选择 function 或 function_graph
   → 执行目标操作
   → 从任务、PID、CPU、时间和调用关系读路径
   → 结合 sched 事件判断等待与执行时间

事件追踪：

::

   在 available_events 找到 subsystem:event
   → 读取事件 format
   → 写入 filter 缩小对象范围
   → enable 目标事件
   → 必要时设置 trigger 或 snapshot
   → 复现问题
   → 按时间顺序组合多个事件
   → 检查 dropped 和 overrun

必须区分
--------

* 源码路径与运行路径：源码表示可能分支；trace 表示本次运行实际命中的观察点。
* 函数 tracing 与事件 tracing：函数 tracing 关注调用入口和嵌套；事件 tracing 关注预先定义的结构化语义与字段。
* ``trace`` 与 ``trace_pipe``：``trace`` 读取 buffer 快照；``trace_pipe`` 持续消费新记录。
* 函数持续时间与 CPU 执行时间：function graph duration 可能包含睡眠、抢占和中断，需要调度事件补证据。
* 没有记录与路径没有发生：过滤错误、buffer 覆盖、权限、配置和 tracer 能力都可能造成记录缺失。
* 时间相邻与因果关系：两个事件接近只能证明时序接近；因果关系还要由对象、调用链和状态转换证明。

一句话结论
----------

``tracefs`` 把内核运行路径变成可过滤的函数与事件时间线；可靠 tracing 必须缩小范围、检查丢失、记录配置，并把运行证据重新映射到源码和对象状态。
