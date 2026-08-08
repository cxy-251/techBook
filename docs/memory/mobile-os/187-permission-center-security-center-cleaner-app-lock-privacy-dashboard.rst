第187章：Permission Center, Security Center, Cleaner, App Lock, Privacy Dashboard
=================================================================================

核心知识点
----------

* Android runtime permission 只是一层授权事实。真实能力还会经过 AppOps、具体 system service、前后台状态、传感器开关、电池/网络策略以及 OEM 附加控制。
* OEM Permission/Security Center 是平台治理聚合入口，通常把权限、通知、自启动、后台、电池、清理、病毒扫描、应用锁、隐私空间和敏感访问日志集中管理。
* 权限中心的 UI 负责写入策略状态；Location、Notification、Activity、Power 等系统服务才是调用发生时的执行检查点。
* Cleaner 主要处理缓存和可回收存储；Booster 主要影响进程和调度；Battery Manager 主要影响后台任务、网络、定位和唤醒预算。三者不能混为同一机制。
* App Lock 保护应用启动入口，不等价于加密应用全部数据；Private Space / 独立用户或 profile 更接近身份、进程、数据目录和权限状态隔离。
* Clone App/应用分身本质上需要新的用户/profile/UID 或厂商容器化身份，从而形成独立数据目录、账号和权限状态；它不是同一进程简单复制 UI。
* Privacy Dashboard、权限日志和相机/麦克风/定位指示器负责可见性与审计，重点是回答“哪个 App 在何时使用了什么敏感能力”。
* OEM 治理的风险是把安全、电池和清理过度耦合，导致标准 Android API 已获授权却仍出现后台、通知、定位或媒体行为差异。

关键路径
--------

敏感能力：

``App → Runtime Permission → Framework API → System Service + AppOps → OEM Policy → Resource``

OEM 设置写入：

``Security / Permission Center → Privileged API / OEM Service → Policy State / Whitelist → System Service Enforcement``

清理与后台：

``Cleaner / Battery Manager → Process / Cache / Background Policy → App Restart / Delay / Data Rebuild``

隔离空间：

``Launcher / User Selection → App Lock or Private Space → Authentication / User-Profile Boundary → Separate App State``

概念辨析
--------

* **Permission grant vs Effective access**：用户授权只是必要条件；调用时还可能被 AppOps、服务状态、生命周期和 OEM 策略限制。
* **Security Center vs 普通安全 App**：前者通常具有平台签名、privileged permission 或厂商私有接口，可修改系统级策略；普通 App 没有这种控制权。
* **Cleaner vs Memory Manager**：Cleaner 是用户/厂商主动治理入口；Android 内核与 Framework 本身已经有独立的内存回收和进程优先级机制。
* **App Lock vs Private Space**：App Lock 偏向启动前认证；Private Space 更接近独立身份和数据域。
* **Privacy indicator vs Permission**：指示器/日志负责告知和审计；permission/AppOps/service enforcement 负责真正放行或拒绝。

本章结论
--------

OEM 权限与安全中心应被视为“策略控制面”，而不是一个孤立应用。排查时要把每个 UI 开关翻译成它写入的系统状态，再追到真正执行该状态的 service。稳定判断链是 ``身份 → Permission/AppOps → OEM Policy → Background/Power/Notification → Kernel/Resource``，这样才能解释“权限已允许但能力仍不可用”的设备差异。