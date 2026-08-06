第034章：tracefs 与内核追踪接口
===============================

核心知识点
----------

tracefs 是内核 tracing 的控制面
   ``tracefs`` 通常挂载在 ``/sys/kernel/tracing``，通过文件暴露 tracer、事件、过滤器、触发器、ring buffer 和输出接口。兼容路径 ``/sys/kernel/debug/tracing`` 仍可能存在。

Tracing 验证实际运行路径
   静态源码说明哪些分支可能存在；tracing 说明当前内核、配置、负载和时间窗口内哪些函数或事件实际发生。它是运行证据，不是源码解释的替代品。

函数 tracer 观察调用结构
   ``function`` tracer 记录函数入口，``function_graph`` 进一步记录进入、返回和嵌套关系。函数图中的持续时间可能包含睡眠、抢占和中断，不能直接等同于纯 CPU 执行时间。

Tracepoint 提供结构化事件
   Tracepoint 是源码中预先定义的语义观察点，常用于调度、IRQ、块 I/O、网络和内存路径。事件的 ``format`` 文件定义字段类型，是配置过滤条件和解释输出的依据。

过滤器和触发器用于缩小证据范围
   函数、PID、事件字段和 CPU 过滤可减少无关记录；trigger 可以在条件满足时启停 tracing、保存 snapshot 或记录调用栈。范围越小，开销和覆盖风险越低。

Trace buffer 有容量与丢失边界
   Buffer 通常按 CPU 组织，记录可能因覆盖、overrun、过滤或读取不及时而丢失。没有记录不一定表示路径没有发生，必须同时检查配置与丢失信息。

Tracing 会改变被观察系统
   全局函数追踪或大量高频事件会增加 CPU、内存和锁开销，并可能改变竞态与延迟。实验应限制对象、持续时间和复现动作。

可重复实验必须保存配置
   一次有效追踪需要记录内核版本、tracer、事件、过滤器、buffer 大小、目标 PID 和复现步骤。实验结束后要恢复 ``nop``、关闭事件并清理过滤器。

事件相邻不自动构成因果
   Trace 能给出观察点和局部时间顺序。因果关系仍需由对象身份、调用链、状态转换和依赖规则共同证明。

关键路径
--------

一次最小 tracing 实验：

::

   明确要验证的源码判断
   → 确认 tracefs 挂载点和可用 tracer、事件
   → 关闭 tracing_on 并清空旧 buffer
   → 设置 tracer、事件和过滤条件
   → 打开 tracing_on
   → 执行一次最小复现
   → 立即关闭 tracing_on
   → 保存 trace、配置和环境
   → 清除全部调试设置

验证函数路径：

::

   在 available_filter_functions 确认目标函数
   → 限定 PID 和函数范围
   → 选择 function 或 function_graph
   → 执行目标操作
   → 按任务、CPU、时间和嵌套关系阅读
   → 结合 sched 事件区分执行与等待

追踪结构化事件：

::

   在 available_events 选择 subsystem:event
   → 读取 format 确认字段
   → 设置事件 filter
   → 启用事件并复现
   → 按时间组合相关事件
   → 检查 buffer 覆盖和丢失

概念辨析
--------

源码路径与运行路径
   源码描述可能执行的分支；trace 描述本次运行命中的观察点。

函数 tracing 与事件 tracing
   函数 tracing 关注调用入口和嵌套；事件 tracing 关注预定义语义和结构化字段。

``trace`` 与 ``trace_pipe``
   ``trace`` 读取当前 buffer 快照；``trace_pipe`` 持续消费后续新记录。

函数持续时间与 CPU 执行时间
   Function graph duration 可能包含任务睡眠、抢占和中断，需要调度事件补充判断。

没有记录与路径未发生
   过滤错误、能力缺失、权限、buffer 覆盖和读取方式都可能造成记录缺失。

时间相关与因果关系
   时间接近只证明事件相邻；因果还要由相同对象和状态转换链证明。

本章结论
--------

``tracefs`` 把内核运行行为组织成可过滤的函数与事件时间线；可靠追踪必须缩小范围、检查丢失、保存配置，并把记录重新映射到对象和源码机制。