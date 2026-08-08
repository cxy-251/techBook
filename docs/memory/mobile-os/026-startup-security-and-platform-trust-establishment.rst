第026章：Startup Security and Platform Trust Establishment
==========================================================

核心知识点
----------

* Startup Security 的产物不是一个单独布尔值，而是一组会被 kernel、system service、keystore、package manager、sandbox 和 App runtime 持续读取的信任事实。
* Trust Establishment 由硬件 root of trust、镜像签名、分区完整性、rollback state、device lock state、启动模式和用户数据密钥状态共同构成。
* Secure Boot / Verified Boot 证明“当前平台代码来自可接受来源且内容完整”；运行时安全再用 SELinux、sandbox、code signing、permission、entitlement 和 service policy 约束每一次访问。
* Android 的稳定链路可概括为 ``AVB result → kernel → init/SELinux → system_server → app identity/permission/keystore``。
* Apple 的稳定链路可概括为 ``Boot ROM/iBoot → XNU → launchd/system daemons → code signing/sandbox/Data Protection → app process``。
* Device Lock State、Developer Mode、User Trust 属于不同层级。Bootloader unlock 改变系统镜像接受范围；Developer Mode 开放调试能力；用户或风控系统是否信任设备还会读取更多完整性和策略信号。
* Recovery、DFU、fastboot、factory reset 等模式会改变平台控制权和用户数据可访问条件。进入恢复环境不等于能够读取原有用户数据。
* 用户解锁把启动完成的可信平台与用户数据密钥连接起来。开机成功但尚未解锁时，部分文件、KeyStore/Keychain 项和认证绑定密钥仍可能不可用。
* App 安装后的身份由签名、包记录、UID/entitlement、sandbox container 等对象建立。启动信任保证平台可信，应用身份再决定第三方代码处于什么边界。
* 敏感 App 的完整性检查可能在系统正常启动后仍拒绝功能，因为“系统能运行”和“当前设备满足某项高风险业务信任要求”不是同一个判断。

关键路径
--------

平台信任建立：

::

   hardware root of trust
   → verify boot chain and system images
   → check rollback + device state
   → kernel starts with verified state
   → runtime security policy loads
   → system services establish app identities
   → user unlock releases protected data classes
   → app runs inside signed sandbox identity

Android 运行时衔接：

::

   AVB / boot state
   → kernel + init
   → SELinux policy and properties
   → Zygote / system_server
   → PackageManager UID + signature
   → Permission/AppOps/Keystore checks
   → app capability result

敏感能力：

::

   app requests protected operation
   → verify caller identity
   → check permission / entitlement / device state
   → check user authentication and key policy
   → secure hardware operation if required
   → success or security failure

概念辨析
--------

* **Secure Boot 与 runtime security**：前者决定可信平台能否启动，后者决定已启动平台中的主体能访问什么。
* **Bootloader unlocked 与 Developer Mode**：前者改变系统镜像控制权，后者主要开放开发调试能力，两者风险边界不同。
* **Platform trust 与 App trust**：可信 OS 不代表每个 App 都可信；App 仍需独立签名身份、沙箱和权限控制。
* **系统已启动与用户数据已解锁**：平台运行条件成立不代表所有用户数据密钥已经可用。
* **Recovery access 与 data access**：恢复环境拥有系统维护权限，但数据保护机制可以继续阻止未授权读取用户数据。

本章结论
--------

启动安全最终要把“可信启动”转化为“可信运行环境”。硬件根信任、Verified Boot、rollback、device state 建立平台基础；SELinux/sandbox、应用签名、权限、密钥服务和用户解锁继续把这些事实落实到运行时。分析安全状态时，应区分平台是否能启动、设备控制权是否被降低、用户数据是否可解封、App 身份是否可信以及当前能力请求是否满足策略。