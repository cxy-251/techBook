第146章：Android Doze, App Standby, JobScheduler, WorkManager, WakeLock
======================================================================

核心知识点
----------

* Android 后台执行主链是 ``App → Work / Job / Foreground Service / Alarm / WakeLock → System Services → Doze / Standby / Quota / Power Policy``。
* Doze 面向整机长时间空闲。设备未充电、屏幕关闭并长期静止后，系统会限制后台 CPU、network、job、sync 和普通 alarm，并只在 maintenance window 中释放部分工作。
* WakeLock 不能绕过 Doze。它只在系统已经给予执行机会时帮助 CPU 保持清醒，不会自动恢复网络、job 配额或后台资格。
* App Standby 面向单个 App 的近期使用关系。系统根据用户最近交互、前台状态、通知交互等信号，把 App 放入不同 standby bucket，并据此调整 job、alarm、network 配额。
* JobScheduler 用 ``JobInfo`` 表达 network、charging、idle、battery、storage、deadline、backoff 等约束；系统负责批量调度和执行窗口。
* WorkManager 面向持久化、可重试、约束化的后台工作，并在不同 Android 版本上把执行映射到底层调度能力。它适合可靠完成，不保证精确执行时间。
* Foreground Service 适合导航、媒体、通话、运动记录和用户主动长期传输等可见任务。现代 Android 对 service type、启动时机、权限和通知要求越来越严格。
* AlarmManager 强调时间触发。Doze 会推迟普通 alarm；while-idle / exact 类能力有更严格用途、频率和权限边界。
* Work / Job 应支持分片、幂等、持久化进度和 backoff。一次后台窗口不能被假设为足够完成全部工作。
* BatteryStats 等系统统计会把 wakelock、job、alarm、network 与进程活动归因到 UID/App，是排查后台耗电的重要证据。
* OEM 仍可能在 AOSP 策略上叠加电池优化和进程冻结，因此“标准 API 使用正确”不代表所有设备执行时机完全一致。

关键路径
--------

WorkManager / JobScheduler：

::

   App enqueues persistent work
   → constraints + retry/backoff + persisted state
   → JobScheduler / system scheduler
   → standby bucket + quota + Doze state
   → network / charging / idle constraints satisfied
   → execution window
   → success / stop / retry
   → persist progress

Doze 路径：

::

   screen off + unplugged + idle
   → device enters Doze
   → network/jobs/sync/normal alarms deferred
   → maintenance window
   → queued work gets limited opportunity
   → back to Doze
   → user interaction/charging exits idle

概念辨析
--------

* **Doze 与 App Standby**：Doze 以整机空闲为中心，App Standby 以单个 App 的近期使用程度为中心。
* **JobScheduler 与 WorkManager**：JobScheduler 是平台原生调度接口，WorkManager 提供更高层持久化、依赖、约束和重试抽象。
* **Foreground Service 与 WorkManager**：前者适合用户可见长期任务，后者适合可延迟、可靠完成的后台工作。
* **WakeLock 与 Scheduler**：WakeLock 保持清醒，Scheduler 决定是否给任务执行机会；两者角色完全不同。
* **Exact Alarm 与 Background Job**：前者服务真实时间语义，后者服务条件满足即可执行的维护任务。

本章结论
--------

Android 后台问题应按 ``入口类型 → Doze / Standby → Constraint → Quota → Execution Window → WakeLock/Network → OEM Policy`` 排查。系统目标不是让 App 永久运行，而是把用户可见工作、可延迟工作和设备空闲功耗放进统一调度模型。