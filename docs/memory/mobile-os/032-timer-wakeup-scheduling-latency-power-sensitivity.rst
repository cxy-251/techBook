第032章：Timer, Wakeup, Scheduling Latency, Power Sensitivity
=============================================================

核心知识点
----------

* Timer 负责表达“何时需要处理”，Wakeup Source 负责表达“设备睡着时谁有资格把系统叫醒”；两者必须分开理解。
* Wall clock 适合闹钟、日历和用户指定时间；monotonic time 适合 timeout、frame deadline、重试和耗时测量，避免受到时区或校时影响。
* 高频、高精度、重复 timer 会频繁打断 CPU idle，增加唤醒、频率恢复和调度成本；允许 tolerance/batching 可以显著减少待机功耗。
* 移动平台会把普通后台同步交给 JobScheduler/WorkManager/BackgroundTasks 等可延迟机制，而不是承诺固定周期精确执行。
* Wakeup Source 可以来自 RTC、touch、charger、sensor hub、modem、Wi-Fi/Bluetooth 或系统 alarm。设备能在 active 状态产生 IRQ，不代表该 IRQ 被允许从深度 suspend 唤醒整机。
* 平台推送比每个 App 自建长连接更适合即时消息，因为系统能统一管理 radio 连接、唤醒优先级与后台执行窗口。
* WakeLock/power assertion 主要解决“醒来后保持系统完成一段工作”，不等于无限后台运行，也不等同于硬件唤醒来源。
* Scheduling Latency 指线程已经具备执行条件到真正获得 CPU 之间的等待；它受 IRQ/softirq、run queue、优先级、CPU idle exit、频率恢复和 thermal 状态影响。
* Tickless idle、深 C-state 和批量定时器能省电，但更深睡眠通常意味着更高 wake latency；移动系统持续在响应速度和能耗之间取舍。

关键路径
--------

后台同步：

::

   App schedules deferrable work
   → Framework scheduler
   → System Service batches constraints
   → Kernel timer / alarm state
   → device enters idle / suspend
   → maintenance window or legal wake source
   → CPU resumes
   → task receives limited execution window

即时消息：

::

   server push
   → platform push channel
   → modem / Wi-Fi wake event
   → Kernel resume
   → notification service
   → App callback if allowed

概念辨析
--------

* **Timer 与 Alarm**：普通 timer 常只在系统运行时触发；alarm 可以具备跨 idle/suspend 的系统语义，但是否真正唤醒仍由平台策略裁决。
* **Wakeup Source 与 WakeLock**：前者触发 resume，后者延缓再次 suspend；职责不同。
* **Timer deadline 与执行时间**：timer 到期只代表任务可被唤醒或排队，不保证线程立即获得 CPU。
* **精确定时与后台周期任务**：用户闹钟需要较强时间承诺；缓存刷新通常应允许系统合并和延迟。
* **低功耗与零延迟**：更深 idle 带来更低功耗，也增加恢复硬件、CPU 与调度上下文的成本。

本章结论
--------

移动系统的时间模型必须与电源模型一起阅读。分析通知晚到、后台同步延迟或触摸唤醒慢时，先区分 timer、wakeup source 和 scheduling latency，再确认系统当前 idle/suspend 状态与后台策略。精确唤醒是一种昂贵资源，平台会优先保留给用户可见、时间敏感的事件。