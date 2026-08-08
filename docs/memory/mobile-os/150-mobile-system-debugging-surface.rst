第150章：Mobile System Debugging Surface
=========================================

核心知识点
----------

* Mobile System Debugging Surface 指系统向开发者开放的观察入口，包括断点、日志、trace、metrics、crash report、bug report、sysdiagnose、service dump、kernel event 与设备诊断包。
* 调试对象应按层分解：``App → Framework → System Service / Daemon → Kernel → Driver → Hardware``。一个用户现象只有被映射到具体层级后，证据才有意义。
* App 层能直接观察自身线程、生命周期、状态机、API 返回值和业务日志；Framework 层提供权限、session、callback、error 等公开状态；System 层掌握资源所有权、队列、策略与跨进程状态。
* Kernel / Driver 层主要解释调度、内存、IPC、I/O、DMA、设备中断和硬件启动延迟。普通量产 App 对这部分的可见性通常受权限和平台策略限制。
* ``Logs`` 适合回答“发生了什么事件”；``Trace`` 适合回答“时间耗在哪里”；``Metrics`` 适合回答“问题是否稳定存在”；``Crash Report`` 适合回答“异常终止现场是什么”；``Bug Report / sysdiagnose`` 适合回答“当时整机状态是什么”。
* 调试前应先固定统一时间基准，例如点击时刻、resume 时刻、第一帧到达时刻、请求开始/结束时刻；不同来源的证据只有放到同一时间窗口中才能建立因果关系。
* Debug build、release build、production device 的可观察性不同。符号、日志级别、权限、采样开销、隐私脱敏都会影响可获得证据。
* 缺少某条日志不能直接证明对应代码没有执行；日志是主动记录的观察点，未记录路径仍需用 trace、stack、state 或 dump 补证。
* Android 调试面更开放，常见入口包括 logcat、dumpsys、bugreport、Perfetto、tombstone 与 AOSP 源码；Apple 更依赖 Console、Instruments、MetricKit、crash logs、sysdiagnose 与公开 Framework 行为。
* 调试工具不是根因本身。稳定流程是先提出一个可验证问题，再选择能回答该问题的最小证据，逐层缩小责任范围。

关键路径
--------

从用户现象到责任层：

::

   user-visible symptom
   → define exact time window
   → App logs / callbacks / thread state
   → Framework state / error / lifecycle
   → System Service or daemon state
   → trace IPC / scheduling / queue wait
   → kernel / driver / hardware evidence if needed
   → correlate all evidence on one timeline
   → assign responsibility boundary

证据选择路径：

::

   what happened?      → logs
   where was time spent? → trace
   how often?          → metrics
   why did process terminate? → crash report
   what was whole-device state? → bugreport / sysdiagnose

概念辨析
--------

* **Log 与 Trace**：log 是离散事件记录，trace 是带持续时间、调度状态和跨线程关系的时间线。
* **Metric 与现场证据**：metric 用于量化趋势和影响范围，不能替代单次复现的因果时间线。
* **Crash 与 Hang**：crash 是异常终止，hang/ANR 是响应失败；前者先看终止原因，后者先看应响应线程在等待什么。
* **App-Level 与 System-Level Debugging**：App-Level 验证应用是否正确发起和处理请求，System-Level 验证系统是否接受、调度、限制或延迟该请求。
* **可观察事实与实现推断**：公开工具直接给出的状态属于事实；私有 daemon、driver 内部机制若无法直接验证，应只作为推断而非稳定接口。

本章结论
--------

移动系统调试的核心不是“多开几个工具”，而是 ``现象 → 时间窗口 → 层级 → 最小证据 → 跨层时间线 → 责任边界``。任何卡顿、黑屏、权限失败、耗电或硬件异常，都应先确定哪个层级需要被证明，再选择日志、trace、metrics、crash 或设备诊断包完成证据闭环。