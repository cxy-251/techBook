第141章：Background Networking, Push, Power, Data Saver
=========================================================

核心知识点
----------

* 后台网络的核心不是“还能不能联网”，而是系统如何在生命周期、电量、流量成本、任务截止时间和用户可见性之间调度联网机会。
* 前台请求通常由用户动作驱动，系统可以立即投入资源；后台请求需要转换成可延迟、可恢复、可约束、可持久化的任务。
* 后台上传、下载、周期同步、缓存刷新、推送触发更新应按业务紧迫度、数据量、网络成本和是否需要用户立即知道来分类。
* Push Notification 的主要价值是替代高频轮询：服务端先告诉系统“有变化”，设备再决定展示通知、短暂唤醒 App 或延迟处理。
* 推送不是无限后台执行权。静默推送适合短小状态刷新，不适合长期下载、频繁轮询替代或绕过系统后台限制。
* 大文件后台传输应优先交给系统托管机制，例如 Android 的持久任务/约束调度或 Apple background URLSession，使任务生命周期不依赖 App 常驻。
* Retry 必须配合 backoff。弱网、DNS、TLS、服务端限流等错误具有持续性，立即连续重试会放大 radio wakeup、流量和服务器压力。
* 网络可用性需要同时看 validated、metered/expensive、constrained、roaming、Data Saver/Low Data Mode 和后台 UID policy。
* Data Saver / Low Data Mode 表达用户希望减少数据消耗；App 应减少预取、降低媒体质量、暂停大文件自动同步，而不是只在完全断网时降级。
* Wi-Fi only、cellular allowed、roaming allowed 是产品策略与系统网络状态的组合，不应硬编码成单一“有网就传”。
* 后台任务需要持久化业务状态：对象 ID、文件、版本、幂等 token、重试次数和最后错误，才能在进程被杀、网络切换和设备重启后恢复。
* 用户可见通知、进度和设置提示是后台网络策略的一部分。系统限制发生时，产品应表现为“稍后继续/等待合适网络”，而不是伪装成服务器故障。

关键路径
--------

后台同步：

::

   business event
   → persist work state
   → declare constraints/deadline/retry policy
   → system scheduler
   → lifecycle + battery + network-cost policy
   → eligible execution window
   → DNS/TLS/transfer
   → success or backoff/retry
   → update persistent state and user-visible result

推送触发：

::

   server detects change
   → platform push service
   → system receives payload
   → notification or short background opportunity
   → App updates small metadata
   → heavy transfer is delegated to scheduled/background transfer

概念辨析
--------

* **Background networking 与 background execution**：联网机会只是后台执行的一部分，App 进程并不因此获得永久运行权。
* **Push 与 polling**：push 由服务端事件触发共享系统通道，polling 由客户端周期主动查询；后者更容易制造无效唤醒。
* **Retry 与 backoff**：retry 是再次尝试，backoff 决定等待多久；没有 backoff 的重试会形成请求风暴。
* **Metered 与 constrained**：metered/expensive 强调成本，constrained/Data Saver/Low Data Mode 强调用户要求减少数据使用。
* **Immediate task 与 deferrable task**：用户正在等待的请求追求即时结果，自动备份/预取更适合接受系统择机执行。

本章结论
--------

后台网络应设计成 ``Persistent Work → System Scheduling → Network/Power Policy → Transfer → Recoverable State``。推送用于通知变化，系统托管任务负责重传和大文件，Data Saver/Low Data Mode 决定降级边界；正确目标不是后台常驻，而是在合适窗口可靠完成业务。