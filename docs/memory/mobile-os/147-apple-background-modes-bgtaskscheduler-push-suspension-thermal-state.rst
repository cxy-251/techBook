第147章：Apple Background Modes, BGTaskScheduler, Push, Suspension, Thermal State
================================================================================

核心知识点
----------

* Apple 后台执行的稳定模型是 ``App Lifecycle → Suspension by Default → Approved Background Capability / BGTask / Push / Background URLSession → System Policy Window``。
* 普通 App 离开前台后，默认会进入后台并逐步被挂起。Suspension 表示进程状态可能保留，但普通代码执行暂停。
* Background Modes 只为系统认可的持续能力开放后台机会，例如 audio、location、Bluetooth、VoIP 等；声明 capability 不等于无限 CPU 时间。
* BGTaskScheduler 用于后台刷新与后台处理。App 提交任务意图、earliest begin time 和约束，系统根据使用习惯、电源、网络、温度等决定实际运行窗口。
* Background URLSession 把上传下载交给系统托管，使传输可在 App 挂起或退出后继续，并在完成时重新唤醒/回调 App 处理结果。
* Remote Notification / Silent Push 可以提供通知展示或有限后台处理机会；推送是否及时交付、是否唤醒 App 由系统预算、用户设置和设备状态共同决定。
* Silent Push 不是保活机制。高频、无用户价值的静默推送会被系统节流，并可能导致后台机会减少。
* Thermal State 是应用可见的降载信号。``nominal / fair / serious / critical`` 反映系统热压力，App 应主动减少计算、图形、网络、相机等高成本工作。
* Background Mode、BGTask、URLSession、Push 分别对应持续能力、延迟任务、系统托管传输和服务器事件入口，不能互相替代。
* 用户关闭 Background App Refresh、通知、定位或相关权限时，系统可能直接改变后台路径；能力是否声明与用户是否允许是两层条件。
* Apple 私有调度器、daemon 和进程 assertion 细节不是稳定 API；可靠判断应基于公开 lifecycle、task callback、error、thermal state 和系统设置。

关键路径
--------

BGTaskScheduler：

::

   App registers task identifier
   → submit refresh / processing request
   → earliest begin + constraints
   → App moves to background / suspension
   → system evaluates usage + battery + network + thermal
   → grants execution window
   → task handler runs
   → complete success/failure before expiration

Background URLSession：

::

   App creates background transfer task
   → system persists transfer
   → App may suspend/terminate
   → transfer continues when policy allows
   → system finishes transfer
   → relaunch/callback opportunity
   → App reconciles persistent state

概念辨析
--------

* **Background State 与 Suspension**：进入后台后可能短暂执行，Suspension 才表示普通代码被冻结。
* **Background Mode 与 BGTask**：Background Mode 服务特定持续能力，BGTask 服务系统择机执行的刷新/处理工作。
* **BGTask 与 Background URLSession**：前者给 App 一段执行窗口，后者把网络传输本身交给系统长期托管。
* **Silent Push 与 Guaranteed Wakeup**：静默推送只是后台机会，不保证每次立即唤醒或固定执行时长。
* **Thermal State 与 Performance Hint**：thermal state 是系统热压力反馈，App 应据此主动降载，但无法直接控制底层频率策略。

本章结论
--------

Apple 后台架构应按 ``Lifecycle → Capability Declaration → System Scheduling → Limited Execution Budget → Suspension/Recovery`` 理解。正确设计依赖系统认可的后台模式、可恢复任务、系统托管传输和热状态降载，而不是假设进程在后台持续运行。