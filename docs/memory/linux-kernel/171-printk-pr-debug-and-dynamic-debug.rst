第171章：printk、pr_debug 与 Dynamic Debug
=========================================

核心知识点
----------

``printk`` 首先写入内核日志缓冲
   日志调用不会直接等价为屏幕输出。记录先进入 Printk Ring Buffer，再由 Console、``/dev/kmsg``、``dmesg`` 或用户态日志服务读取。

日志等级表达严重性与输出策略
   ``pr_err``、``pr_warn``、``pr_info``、``pr_debug`` 分别面向失败、降级、低频状态和按需调试。Console Level 主要控制控制台可见性，不证明 Callsite 是否执行。

日志必须携带对象与状态
   有效记录应包含对象身份、生命周期阶段、关键状态、负 Errno 和后续行为。只写“failed”无法连接调用链、设备和恢复路径。

设备日志应保留设备上下文
   驱动优先使用 ``dev_err``、``dev_warn``、``dev_info``、``dev_dbg``，使消息与具体 ``struct device``、总线路径和实例关联。

Printk 记录不是全局因果时钟
   多 CPU、IRQ、Worker 和硬件事件可并发发生。相邻文本只表示记录接近，不能单独证明调用关系或真实事件先后。

Dynamic Debug 控制具体 Callsite
   启用 ``CONFIG_DYNAMIC_DEBUG`` 后，``pr_debug``/``dev_dbg`` Callsite 可按模块、文件、函数、行号、格式串或 Class 精确开关，而不必打开整个驱动的全部输出。

动态调试只增加证据，不改变路径事实
   Query 写入成功只说明匹配规则被接受；没有输出还可能是路径未发生、过滤未匹配、缓冲被覆盖或构建配置不支持。

高频事件不适合逐条文本日志
   Packet、Request、Page、IRQ 等高频路径应优先使用 Counter、Tracepoint 或 Histogram。逐事件格式化与控制台输出会放大 CPU、锁和 I/O 成本。

限速保护的是日志系统
   ``*_ratelimited`` 限制重复消息，``*_once`` 只保留首次证据。它们不会修复事件源，也不能替代真实发生次数统计。

日志可见性受多层策略影响
   ``dmesg_restrict``、Capability、LSM、Lockdown、容器挂载和用户态日志过滤都可能限制读取。读不到日志不表示 Ring Buffer 中没有记录。

崩溃路径需要冗余证据
   Panic、Hard Lockup 或内存破坏可能让普通日志不完整，因此关键现场还需 Pstore/Ramoops、Kdump、Vmcore、Serial 或 BMC 通道。

关键路径
--------

普通日志路径：

::

   pr_err / dev_warn / printk Callsite
   → 组合 Level、对象和 Errno
   → 写入 Printk Ring Buffer
   → Console 按阈值输出
   → dmesg / devkmsg / journald 读取
   → 与 CPU、PID、对象和时间线关联

Dynamic Debug：

::

   pr_debug / dev_dbg Callsite 注册
   → dynamic_debug/control 中按 File/Func/Module/Format 选择
   → +p 开启最小 Callsite 集合
   → 执行目标负载并采集日志
   → -p 关闭并保存 Query 与时间窗口

日志风暴控制：

::

   发现高频重复消息
   → 判断是否应改为 Counter/Tracepoint
   → 必须保留时增加 Rate Limit
   → 缩小字段与对象范围
   → 验证 CPU、Ring Buffer、Console 和持久化开销

概念辨析
--------

* Ring Buffer 与 Console：前者保存内核记录；后者只是按等级输出记录的消费者。
* ``pr_err`` 与 ``pr_debug``：前者记录默认必须保留的失败事实；后者记录按需打开的路径细节。
* 日志顺序与因果顺序：文本顺序不能替代跨 CPU、异步任务和硬件完成关系。
* Rate Limit 与故障频率：限速减少输出量，不表示故障次数下降。
* Printk 与 Tracepoint：Printk 是自由文本证据；Tracepoint 是结构化事件，适合关联和统计。

本章结论
--------

``printk`` 的价值是在有限运行扰动下保存对象、阶段、状态和错误；Dynamic Debug 进一步把证据采集缩小到具体 Callsite，而不是把日志量本身当作可观测性。