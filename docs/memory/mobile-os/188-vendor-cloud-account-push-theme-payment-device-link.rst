第188章：Vendor Cloud, Account, Push, Theme, Payment, Device Link
===============================================================

核心知识点
----------

* OEM 服务层是叠加在 Android 之上的“第二平台层”：复用 Android 的账号、通知、网络、存储、NFC 和安全基础，再加入厂商身份、云端、推送、钱包、主题和多设备协议。
* Vendor Account 是生态身份根，绑定用户、设备、区域、云服务、应用商店、Push token、钱包资格和设备信任关系；退出账号会连带收缩多项厂商服务。
* Vendor Cloud 包含备份与同步。备份面向恢复点，同步面向多设备持续一致；相册、联系人、设置、设备查找等能力会跨越本地数据库、账号状态、后台策略、网络和云端存储。
* OEM Push 与 FCM 可以并存。两者的区别主要在云端通道和设备上的特权推送主体；业务后端往往需要维护多种 token 并按设备环境选择投递通道。
* Theme/Font/Wallpaper/Launcher 属于表层生态，但可以通过系统应用和资源机制影响桌面、锁屏、图标、字体、推荐位与交互入口。
* OEM Wallet/Payment 把厂商账号、NFC、Secure Element/TEE、支付 token、系统认证和风险控制连接成受控链路；普通 App 无法直接等价替代系统钱包权限。
* Device Link/多设备协同需要设备发现、账号身份、连接建立、权限确认、传输协议和目标设备能力共同成立，通常由厂商系统服务提供更深的平台集成。
* 厂商服务增强用户体验的同时，也提高迁移成本：Push、云数据、商店购买、钱包、主题和跨设备能力都会形成生态依赖。

关键路径
--------

账号与云：

``Settings / OEM App → Vendor Account → Device Trust / Service Token → OEM Cloud → Backup / Sync / Find Device``

推送：

``App Server → FCM or OEM Push Cloud → Google/OEM Push Process → Android Notification Policy → App / Notification``

钱包：

``Wallet App → Account / Identity → Payment Service → NFC Controller / Secure Element / TEE → Terminal``

多设备协同：

``User Intent → OEM Device-Link Service → Account Trust + Discovery → Transport → Remote Device Capability → Cross-Device Result``

概念辨析
--------

* **Backup vs Sync**：备份保存恢复点；同步持续传播变化并处理多端一致性。
* **FCM vs OEM Push**：二者都是消息下行基础设施；区别在服务提供方、设备长连接主体和区域生态。
* **Vendor Account vs Android App Account**：厂商账号可作为系统级生态身份；普通 App 账号只属于该应用或其服务域。
* **Theme ecosystem vs System policy**：主题主要改变视觉和入口，不应与后台、电源、权限等执行策略混同。
* **NFC access vs Payment capability**：拥有 NFC API 不等于拥有支付凭据、Secure Element 访问和系统钱包资格。
* **Device discovery vs Device trust**：发现附近设备只证明可见；跨端敏感操作还需要账号、认证、授权和安全通道。

本章结论
--------

OEM Android 的平台能力不止来自 AOSP 和 Vendor HAL。厂商账号、云、Push、钱包和多设备服务形成了独立生态控制面。分析时应把路径拆成 ``本地 Android 能力 → OEM 特权服务 → 厂商云端 → 身份/区域/硬件条件``，才能判断故障属于 Android 基础、OEM 系统服务、云端策略还是生态资格。