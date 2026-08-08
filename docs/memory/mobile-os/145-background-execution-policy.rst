第145章：Background Execution Policy
====================================

核心知识点
----------

* Background Execution 是系统授权资源，不是“App 退到后台后线程继续跑”。CPU、network、location、Bluetooth、audio、camera、notification 都进入独立策略边界。
* App Visibility 是后台资格的重要输入。前台可见、用户刚发起任务、媒体播放、导航、通话等状态更容易获得持续资源；低可见性维护任务更适合延迟执行。
* 用户可见长期任务、可延迟任务、定时任务、服务器触发事件和系统托管传输应使用不同模型，不能都用“保活”解决。
* Foreground Service / 用户可见长期执行适合导航、播放、通话、运动记录和主动大文件传输；它的代价是通知、服务类型、权限和用户可停止性。
* Background Task / Job 适合刷新、清理、同步、索引和可恢复处理；系统根据网络、充电、idle、quota、热状态和最近使用选择执行窗口。
* Push 用于把服务器侧“有新事件”交给设备；它提供通知或短暂处理机会，不等于无限后台执行权。
* Alarm 适合真正具有时间语义的提醒；普通同步和缓存维护不应依赖高频精确 Alarm。
* Network、Location、Audio、Bluetooth、Camera 的后台边界不同。敏感硬件通常还叠加隐私授权、用户提示、前台状态和资源占用约束。
* Scheduling Window、Batching 与 Backoff 是移动后台设计的核心。可延迟工作应合并执行，失败应退避，而不是持续轮询和立即重试。
* 后台执行同时受 Battery、Privacy、User Attention 三类预算约束：任务不能只满足“技术上能运行”，还要满足用户可解释性。
* 任务应被建模为实时、可延迟、可恢复、用户可见四类语义，并记录触发来源、资源需求、约束条件和恢复状态。
* Android 与 Apple 的具体 API 不同，但共同模型都是 ``App Intent → Framework Declaration → System Scheduler/Service → Policy Window → Execution Budget``。

关键路径
--------

后台资格判断：

::

   App leaves foreground
   → classify task semantics
   → declare service / job / background task / push / alarm
   → system checks identity + permission + lifecycle
   → battery + network + thermal + quota + user settings
   → execute now / defer / batch / reject
   → callback / notification / retry state

任务架构转换：

::

   business requirement
   → user-visible and time-critical?
   → yes: foreground/user-visible capability
   → no: can it wait?
   → yes: job/background task + constraints
   → server event needed?
   → push
   → exact user reminder needed?
   → alarm/local notification

概念辨析
--------

* **Background Thread 与 Background Execution**：线程是进程内部执行工具，后台执行资格由 OS 决定；进程被挂起后线程本身没有意义。
* **Foreground Service 与 Job**：前者服务用户可见长期任务，后者服务可延迟、约束化、批处理任务。
* **Push 与 Persistent Connection**：Push 让系统共享长连接并按事件唤醒 App，普通 App 自建常驻连接会受到更严格电源限制。
* **Alarm 与 Job**：Alarm 强调时间点，Job 强调条件满足后的执行窗口。
* **Permission 与 Execution Budget**：拥有权限只表示可以请求能力，不表示系统必须在后台立即、持续提供执行时间。

本章结论
--------

后台执行的稳定模型是 ``Task Semantics → Visibility → Capability Declaration → System Policy → Execution Window → Recovery``。正确架构不是寻找“永不被杀”的方法，而是把不同任务放进平台认可的执行模型，并保证任务可延迟、可分片、可重试、可恢复。