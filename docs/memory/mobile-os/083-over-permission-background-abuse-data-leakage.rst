第083章：Over-Permission, Background Abuse, Data Leakage
========================================================

核心知识点
----------

* 移动平台安全风险常发生在“合法能力被扩大使用”之后：权限范围过宽、后台执行脱离用户意图、数据出口失控、IPC 代理身份错位都会让正常 API 变成风险路径。
* Over-Permission 的判断应同时看四层：安装包声明了什么、用户授予了什么、代码实际调用了什么、数据最终保存或传输了什么。最小权限要求四层尽量对齐。
* 权限应与具体用户动作绑定。能通过 picker、单次位置、近似位置、有限照片库等更窄能力完成的任务，不应默认申请全量权限。
* Background Abuse 的核心是持续资源使用失去用户可感知理由。持续定位、录音、网络心跳、WakeLock、Alarm、Foreground Service 和通知都必须与真实任务语义一致。
* 后台权限和后台执行是两个边界：拥有定位权限不等于可以无限后台采样；系统还会依据前后台状态、电量、网络、热状态和用户可见提示限制任务。
* Data Leakage 往往发生在合法读取之后。文件、剪贴板、照片、联系人或位置可以被授权读取，但若进入日志、共享目录、崩溃报告、分析 SDK 或不必要的网络上传，就跨出了原授权目的。
* 第三方 SDK 与宿主 App 共用宿主身份和权限面。SDK 的数据访问、日志、网络出口和权限声明都应被视为 App 自身安全责任。
* Confused Deputy 指高权限 service / provider 代低权限调用者执行操作，却没有正确绑定 caller identity、权限和参数范围，导致攻击者借代理越权。
* IPC 边界上的核心规则是“服务端信任 IPC 提供的真实 caller identity，而不是客户端自报身份”，并在清除或切换身份前完成授权检查。
* 平台补救包括权限撤销、一次性授权、精度降级、后台限制、隐私指示器、访问历史、通知控制和应用商店治理。App 必须把撤销视为正常运行状态。

关键路径
--------

Over-Permission：

``User Feature → Permission Request → Grant → Actual API Use → Data Retention / Network Export``

每一段都要问：是否存在更窄能力、是否仍服务当前用户任务、是否需要继续保存或上传数据。

后台滥用：

``App leaves foreground → Background API / Foreground Service / Background Mode → System Scheduler → Sensor / Network / CPU Wakeup → User-visible Indicator / Notification → Continue, Throttle or Revoke``

数据泄漏：

``Protected Data → Legitimate Framework Access → App Memory → File / Clipboard / Log / SDK / IPC / Network Sink``

Confused Deputy：

``Untrusted Client → IPC → Privileged Service → Wrong or Missing Caller Check → Service Uses Own Privilege → Protected Resource``

正确服务路径应是：

``IPC Caller Identity → Permission / Entitlement / Scope Check → Parameter Validation → Resource Operation → Audit / Result``

概念辨析
--------

* **Permission Abuse 与 Exploit**：前者可能完全使用公开 API，只是范围、频率或目的超出用户预期；后者通常依赖实现漏洞绕过既有边界。
* **Background Task 与 Background Abuse**：导航、音乐、上传等真实用户任务可以合法后台执行；失去任务语义后仍持续采集或保活才进入滥用风险。
* **Data Access 与 Data Use**：被授权读取不等于被授权无限保存、组合、上传或交给第三方 SDK。
* **Confused Deputy 与 Caller Spoofing**：前者是高权限代理错误使用自己的权限；caller spoofing 是攻击者伪造身份。安全服务必须同时防止二者。
* **Permission Revocation 与 App Error**：撤销是平台正常状态变化，App 应降级、停止资源使用并保存一致状态，而不是把它当成异常不可恢复条件。

本章结论
--------

移动安全设计的目标不是“把权限都申请成功”，而是让每项能力只在必要时间、必要范围、必要数据上工作，并让数据出口与用户意图保持一致。安全审查应沿“声明 → 授权 → 使用 → 后台持续 → 数据出口 → IPC 代理”逐层检查，任何扩大都必须有明确用户价值和服务端约束。