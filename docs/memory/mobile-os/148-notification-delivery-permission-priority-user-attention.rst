第148章：Notification Delivery, Permission, Priority, User Attention
=====================================================================

核心知识点
----------

* Notification 是系统管理的用户注意力通道，不是 App 自由绘制的后台 UI。系统统一控制授权、展示、声音、锁屏、横幅、摘要、专注模式和用户关闭行为。
* Notification Permission 决定 App 是否具备展示资格；渠道、类别、用户设置和系统模式进一步决定具体通知如何呈现。
* Local Notification 由设备本地按时间或条件触发；Remote Push Notification 由服务器经平台推送服务送达设备。二者最终都进入系统通知中心与用户注意力策略。
* Push delivery 应拆成多个阶段：server sends → platform push service → device receives → OS policy → notification shown / App given limited processing → user interaction。
* “推送送达”不等于“通知展示”。Focus、Notification Summary、静音、Doze、低电量、渠道设置、用户关闭通知都会改变展示时间和形式。
* Priority / Importance、Channel、Category、Interruption Level 表达不同平台上的注意力语义，影响声音、横幅、锁屏、中断程度和是否允许突破部分模式。
* 高优先级只应服务真正时间敏感、用户可见事件。把普通同步或营销信息标记为高优先级会造成打扰、额外唤醒和平台治理风险。
* Push 可以带来短暂后台处理机会，但 Notification 与 Background Execution 是两套边界。展示通知不等于 App 获得长期 CPU 或网络资格。
* 通知点击属于新的用户意图入口。系统可因用户交互提升 App 可见性和后续资源资格，但这应来自真实交互，而非利用通知“保活”。
* Notification Abuse 包括过度推送、误导内容、伪造紧急性、诱导打开和借高优先级绕过后台限制；平台会通过权限、审核、通道和服务端策略治理。
* Notification 同时连接 Power、Privacy、Attention：每次推送可能唤醒设备，payload 可能暴露敏感信息，展示又直接占用用户注意力。

关键路径
--------

远程通知：

::

   server event
   → platform push service
   → device system push channel
   → app identity/token validation
   → notification permission + channel/category policy
   → Focus / Doze / summary / user settings
   → show now / silently deliver / delay / suppress
   → user taps or dismisses
   → App receives interaction callback

本地通知：

::

   App schedules local notification
   → system persists trigger
   → time/calendar/location condition
   → notification policy evaluation
   → system UI presentation
   → user action

概念辨析
--------

* **Push Delivery 与 Notification Display**：前者表示设备收到平台推送，后者还需经过系统注意力策略。
* **Notification Permission 与 Channel/Category**：权限决定总体资格，渠道/类别决定某类通知的具体呈现与用户控制。
* **Priority 与 Urgency**：优先级是系统调度/展示语义，不应被业务随意滥用来制造“必须立即打扰”的效果。
* **Notification 与 Background Execution**：通知是用户注意力通道，后台执行是资源调度能力；二者可以关联，但不是同一个权限。
* **Local 与 Remote Notification**：本地通知无需服务器实时触发，远程通知依赖平台推送通道和设备连接状态。

本章结论
--------

通知链应按 ``Event → Push/Local Trigger → System Permission/Attention Policy → Presentation → User Interaction`` 阅读。真正可靠的设计不是追求“每条消息立刻弹出”，而是让通知的重要性、打扰程度、后台处理和用户控制与事件价值匹配。