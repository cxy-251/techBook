第153章：Apple Console, Instruments, MetricKit, sysdiagnose, Crash Logs
=======================================================================

核心知识点
----------

* Apple 调试面的稳定工具链是 ``Console / Unified Logging → Instruments → MetricKit → sysdiagnose → Crash / Spin / Jetsam Reports``，不同工具负责不同时间尺度和责任边界。
* Console / Unified Logging 主要回答“什么时候发生了什么”。``subsystem``、``category``、level、privacy、process/thread 与 signpost 是建立可筛选事件时间线的关键字段。
* ``os_signpost`` / Points of Interest 可把一次业务操作标成明确起止区间，使日志、Instruments 和生产指标可以围绕同一个功能窗口对齐。
* Instruments 适合可复现问题。Time Profiler 查 CPU 热点与等待，Allocations / Leaks 查内存，Energy 查唤醒和资源活动，Core Animation / Metal System Trace 查图形与 GPU。
* ``MetricKit`` 面向生产环境聚合指标和诊断 payload，可观察 hang、crash、CPU、memory、disk write、network、thermal 等趋势；它是趋势入口，不是完整单次现场。
* ``sysdiagnose`` 是设备级诊断包，用于保存日志、进程、spindump、power、network、thermal、crash 和系统配置等全局上下文。数据量大，必须以明确时间窗口筛选。
* Crash Log 用于异常终止；Spin / Hang Report 用于长时间无响应；Jetsam Report 用于内存压力下的系统终止。三者表现都可能是“App 消失”，责任边界完全不同。
* Apple crash 分析应先确认 exception / termination reason、triggered thread、thread backtrace、binary images、device/OS version，再做 symbolication。
* ``dSYM`` 与二进制 UUID 必须匹配对应构建，才能把地址稳定还原为函数名和源码位置。错误符号比没有符号更危险。
* Apple 平台大量 daemon、内核和驱动细节不是公开应用契约。诊断结论应区分“工具直接观察到的事实”和“根据时间关系推断的系统内部行为”。
* 生产诊断最可靠的闭环是：MetricKit 发现趋势 → 找到可复现场景 → 用 signpost 固定窗口 → Instruments 细化资源热点 → crash/sysdiagnose 补全异常与整机上下文。

关键路径
--------

可复现性能问题：

::

   user action
   → Unified Logging + signpost defines interval
   → Instruments records same interval
   → Time Profiler / Allocations / Energy / Core Animation / Metal
   → identify CPU / memory / I/O / GPU / wait bottleneck
   → verify with App and Framework state

线上异常：

::

   MetricKit trend or user report
   → identify app version / device / OS / scenario
   → crash / hang / jetsam diagnostic
   → symbolicate with matching dSYM
   → collect sysdiagnose when whole-device context matters
   → correlate with reproducible Instruments trace

概念辨析
--------

* **Console 与 Instruments**：Console 记录事件和时间点，Instruments 解释时间与资源消耗。
* **MetricKit 与 sysdiagnose**：MetricKit 是 App 级聚合与诊断趋势，sysdiagnose 是某台设备某次采集的全局现场。
* **Crash 与 Jetsam**：crash 是异常执行导致终止，jetsam 是系统因内存压力回收进程。
* **Spin/Hang 与 Crash**：spin/hang 重点是线程为何不响应，crash 重点是为何异常终止。
* **公开证据与私有实现**：公开工具输出可作为稳定事实，Apple 私有服务名称和内部协议不应被当作长期调试接口。

本章结论
--------

Apple 调试应按 ``Event → Reproduction Timeline → Production Trend → Device Context → Termination Evidence`` 组织。Console 定事件，Instruments 定耗时和资源，MetricKit 定线上趋势，sysdiagnose 定整机环境，Crash/Spin/Jetsam 定异常类型，再用正确符号完成源码归因。