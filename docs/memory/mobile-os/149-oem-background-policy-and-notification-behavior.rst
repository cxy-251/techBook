第149章：OEM Background Policy and Notification Behavior
=========================================================

核心知识点
----------

* Android OEM 可以在 AOSP 的 Doze、App Standby、JobScheduler、Foreground Service、电池优化之上继续叠加厂商省电、进程冻结、自启动和通知策略。
* 自启动管理决定 App 在开机、系统事件或外部触发后是否允许拉起；后台冻结和进程清理决定离开前台后进程能否继续保留执行机会。
* 锁屏清理、深度省电、超级省电、智能冻结等厂商功能会改变标准 Android API 的实际执行时机，但不会改变 WorkManager / JobScheduler 的抽象语义。
* Push delivery 取决于平台推送通道。具备 GMS 的设备常使用 FCM；部分 OEM 还提供厂商推送服务，以减少 App 自建长连接并适配本机后台策略。
* 厂商推送与普通 App 长连接的关键差异是系统信任与常驻资格：系统级通道更容易在深度省电下保持，而第三方私有连接可能被暂停或回收。
* Whitelist、Protected App、Battery Optimization Exemption 会改变后台调度与休眠限制，但它们应被视为用户/系统策略例外，不是默认架构依赖。
* Camera、Location、Network、Bluetooth 等敏感能力可能被 OEM 施加更严格的后台访问、扫描频率和用户提示策略。
* Foreground Service 在不同 OEM 上通常仍具有较强持续执行资格，但启动限制、通知展示、后台清理和用户手动关闭行为可能存在差异。
* WorkManager / JobScheduler 在真实设备上仍受 OEM scheduler、battery manager、standby bucket、系统版本和用户设置共同影响，因此“同一代码不同品牌表现不同”是系统策略差异，不一定是 API bug。
* 排查通知不达时，应区分 server push、平台/厂商 push channel、系统接收、后台拉起、notification permission/channel、OEM notification manager 与用户设置。
* 排查后台任务不运行时，应同时检查 AOSP 策略和 OEM 附加策略，尤其是自启动、后台运行、电池优化、锁屏清理、应用保护和通知权限。
* OEM 行为评估应围绕可观察证据：后台任务时间线、通知送达率、wakeups、battery stats、进程状态和用户设置，而不是用“杀后台严重”这类模糊结论。

关键路径
--------

OEM 后台执行：

::

   App schedules Work / Job / Foreground Service
   → AOSP lifecycle + Doze + standby + quota
   → OEM battery / autostart / freeze policy
   → user whitelist / protected-app settings
   → execute / delay / freeze / kill
   → App retries or restores state

通知送达：

::

   server event
   → FCM or OEM push service
   → system push channel
   → OEM background policy
   → notification permission + channel
   → OEM notification UI / user settings
   → shown / delayed / suppressed

概念辨析
--------

* **AOSP Policy 与 OEM Policy**：AOSP 提供标准后台调度框架，OEM 可以在其上增加更严格的电池、进程和通知控制。
* **Process Alive 与 Task Guaranteed**：进程存活不等于任务一定运行；正确任务应依赖持久化调度和恢复机制，而不是进程常驻。
* **FCM/OEM Push 与 App Long Connection**：前者是系统或平台认可的共享推送通道，后者是普通 App 自己维持的连接，更容易受后台策略限制。
* **Battery Optimization Exemption 与 Foreground Service**：豁免调整部分省电限制，Foreground Service 通过用户可见性获得持续资格；两者不是同一种机制。
* **OEM Difference 与 Platform Fragmentation**：行为差异来自系统版本、厂商策略、GMS/推送生态和用户设置共同作用，不能只归因于硬件品牌。

本章结论
--------

Android 真实后台行为应按 ``Standard Android Policy → OEM Added Policy → User Settings → Push/Task Mechanism → Observable Result`` 阅读。跨设备可靠性的核心不是寻找厂商白名单，而是使用平台认可的任务和推送模型、持久化状态、允许延迟与重试，并把 OEM 附加策略作为最后一层兼容变量。