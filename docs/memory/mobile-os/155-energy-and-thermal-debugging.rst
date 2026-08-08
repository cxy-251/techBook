第155章：Energy and Thermal Debugging
======================================

核心知识点
----------

* Energy debugging 是跨层归因问题。用户看到的是掉电、发热、掉帧、相机降级或后台任务延迟，系统内部对应 CPU、wakeups、network、location、sensor、display、thermal 与调度策略的共同变化。
* 能耗排查的第一原则是先固定时间窗口，再把资源指标映射到责任主体。脱离时间线的“CPU 高”“网络多”“温度高”都不能直接构成根因。
* ``CPU time`` 表示线程获得的执行时间；还需结合 frequency、scheduler state、前后台状态判断它是否真正构成功耗热点。
* ``Wakeups`` 的关键是频率。短任务如果高频唤醒，也会破坏 deep idle residency，使 CPU、radio 和整机长期停留在更高功耗状态。
* ``Network bytes`` 不能单独代表网络功耗。信号质量、radio wakeup、连接保持、tail time、小包频率、失败重试与蜂窝/Wi-Fi 类型共同决定能耗。
* ``Location`` 与 ``Sensor`` 应区分硬件持续采样和 App 回调频率。高 accuracy、高 frequency、低 batching latency 都可能增加硬件活动与主处理器唤醒。
* ``Display time``、brightness、refresh rate、GPU workload 与前台图形链共同构成显示能耗；屏幕关闭后的后台耗电应把 display 因素剥离后再分析。
* ``Thermal state`` 不是单纯温度读数，而是系统已经进入温控决策的抽象状态。热策略可能导致 CPU/GPU 降频、刷新率下降、相机降级、网络吞吐收缩和后台任务延迟。
* Thermal debugging 必须区分 ``temperature fact → thermal state → policy action → user-visible degradation`` 四层。开发者通常稳定可见的是 state 与最终降级结果。
* Android 常用 ``batterystats / Battery Historian / Perfetto / Power Stats`` 组合长周期归因与时间线；现代精细分析应更重视 Perfetto、Power Profiler 等可关联调度与频率的数据。
* Apple 常用 Instruments Energy、Xcode Organizer energy reports、MetricKit 与 ``ProcessInfo.thermalState``。具体热阈值属于平台和设备实现，不应假定为固定值。
* Background task、push、network、audio、location 经常形成串联能耗链，例如 ``location callback → CPU compute → disk write → network upload → retry → notification``，应按派生工作整体归因。

关键路径
--------

能耗归因：

::

   user reports battery drain / heat
   → define reproduction window
   → CPU time + scheduling + frequency
   → wakeup density
   → network bytes + radio activity
   → location / sensor sampling
   → display / GPU activity
   → thermal state and throttling
   → map spikes to App task / System Service / hardware activity

温控路径：

::

   sustained workload
   → hardware temperature rises
   → system thermal state changes
   → frequency / frame / camera / network / background policy adjusts
   → performance and UX degrade
   → App should reduce workload when possible

概念辨析
--------

* **High CPU 与 High Energy**：CPU time 高只是一个输入；频率、核心类型、执行持续时间与其它硬件同时活动才决定最终能耗。
* **Wakeup Count 与 CPU Usage**：低 CPU 平均使用率也可能因频繁短唤醒导致高耗电。
* **Network Bytes 与 Radio Cost**：相同字节数的批量传输和频繁小包传输，radio 能耗可能明显不同。
* **Temperature 与 Thermal State**：温度是硬件测量事实，thermal state 是系统综合后的策略状态。
* **Throttling 与 App Performance Bug**：同一代码在热状态下变慢可能是系统资源上限下降，不应仅按代码回归处理。

本章结论
--------

能耗与温控调试应沿 ``时间窗口 → 资源指标 → 唤醒/采样/传输频率 → Thermal State → 系统降级结果`` 阅读。真正需要优化的通常不是某个孤立 API，而是一串持续工作和唤醒如何让硬件无法进入低功耗状态，并最终触发温控策略。