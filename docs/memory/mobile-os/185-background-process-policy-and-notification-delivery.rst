第185章：Background Process Policy and Notification Delivery
============================================================

核心知识点
----------

* 后台可靠性由进程状态、设备空闲策略、任务配额、网络保活、Push 通道、通知权限/渠道和 OEM 附加策略共同决定；“后台被杀”与“通知未到”不是同一个问题。
* Doze 是设备级空闲策略，限制网络、普通 Job、Sync 和 Alarm；App Standby / Standby Bucket 是 App 级活跃度策略，按用户使用频率分配后台预算。
* 高优先级 Push 只能提供短暂的处理窗口，适合产生用户可见通知，不等于长期后台执行权。
* OEM 常在 AOSP 基础上加入 Battery Saver、Auto-Start、Protected App、Whitelist、夜间冻结和一键清理；这些策略可能影响进程唤醒、网络、Job、Alarm 和推送送达。
* Push 链必须分为“服务端到设备”和“设备到通知”两段。FCM/OEM Push 负责事件下行；App 获得执行窗口后，NotificationManager 再根据通知权限、channel、勿扰和用户设置决定是否展示。
* IM、地图、音乐、健康、IoT 对后台连续性的要求不同，评估 OEM 策略应使用真实业务场景，而非只观察进程是否常驻。

关键路径
--------

实时消息：

``Server → FCM / OEM Push → Device Push Service → Doze / OEM Policy → App Processing Window → NotificationManager → Notification``

任务调度：

``App → WorkManager / JobScheduler / Alarm / FGS → App Standby + Doze → OEM Battery Policy → Execute / Delay / Drop``

用户恢复路径：

``Settings / Security Center → Auto-Start / Battery / Whitelist / Notification → System Policy State → Future Background Behavior``

故障定位顺序：

``Server Sent? → Push Reached Device? → App Woken? → Task Executed? → Notification Allowed? → User Saw It?``

概念辨析
--------

* **Doze vs App Standby**：Doze 管设备整体空闲；App Standby 管单个 App 的后台活跃度。
* **Process Alive vs Background Allowed**：进程仍在内存中，不代表网络、Job、Alarm 或定位一定可执行。
* **Push Delivery vs Notification Delivery**：Push 到达设备只是上游成功；通知还需 App 处理和系统展示权限。
* **Protected App vs 无限后台**：保护名单通常只豁免部分 OEM 附加限制，仍受 Android 权限、Doze、通知和前台服务规则约束。
* **FGS vs 常驻进程**：Foreground Service 是用户可见、受类型和策略约束的持续任务机制，不是绕过后台限制的永久保活手段。

本章结论
--------

后台问题必须按时间线追踪，而不是用“杀后台”概括。稳定模型是 ``Push / Scheduler → Android Base Policy → OEM Policy → App Window → Notification Policy``。先证明事件走到哪一层，再判断是系统空闲策略、OEM 白名单、自启动限制、网络保活还是通知权限导致延迟和丢失。