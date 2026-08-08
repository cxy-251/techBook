第082章：App Store, Certificate, Installation Policy, Platform Trust
===================================================================

核心知识点
----------

* 移动平台安全链在安装前就开始：``Developer Identity → Code Signing → Distribution Channel → Review / Scan → Installer Policy → Installed App Identity → Sandbox / Permission``。
* Distribution 负责把第三方代码带入设备，同时承担开发者身份绑定、恶意软件过滤、版本治理、撤回和风险提示等准入职责。
* 商店审核、恶意软件扫描、安装器校验、运行时沙箱是四个不同控制点。通过 App Store / Play 审核不代表运行时自动获得敏感权限。
* Certificate / signing key 解决代码来源和完整性；package / Bundle identity 解决“这是哪个 App”；安装器再结合版本、签名连续性、设备兼容性、来源和组织策略决定是否允许安装。
* Android 分发可以来自 Play、OEM 商店、企业 MDM、ADB 或其他来源。不同来源会触发不同的安装来源授权、Play Protect、企业策略和用户警告。
* Apple 分发可通过 App Store、TestFlight、开发调试、企业 / MDM 等路径。不同渠道使用不同证书、profile、设备资格和信任条件，但运行时仍回到统一 code signing、entitlement 和 sandbox 模型。
* Installation Policy 是设备本地最后准入点。它检查包结构、签名、版本、已有安装记录、系统版本、profile / entitlement、设备管理策略等。
* 更新必须延续原身份，否则系统会拒绝覆盖，防止恶意包继承旧 App 的数据目录、授权和密钥关系。
* MDM 能把应用安装、删除、数据共享、VPN、证书和账号要求纳入组织策略。此时“能否安装”不仅由个人用户决定。
* Platform Trust 是一条贯穿链：Secure / Verified Boot 保证系统自身可信，应用分发链保证进入系统的第三方代码可识别、可约束、可撤回。

关键路径
--------

公共商店分发：

``Developer Build → Sign → Store Upload → Review / Malware Scan → Store Delivery → Installer Verification → App Identity Record → Launch → Runtime Permission / Sandbox``

Android 非商店来源：

``APK Source App → Source Installation Permission → Package Installer → Signature / Version / Compatibility Check → Play Protect / Device Policy → Install or Block``

Apple 测试或企业路径：

``Signed Build → Certificate / Provisioning Profile → TestFlight / MDM / Enterprise Channel → Device Trust / Policy → Installation → Code Signature + Entitlement Validation → Launch``

排查失败时先确定阶段：下载前失败看渠道与审核；安装中失败看签名、版本、来源和设备策略；首次启动失败看 code signing、profile、entitlement 与 sandbox；功能调用失败再进入运行时权限。

概念辨析
--------

* **Review / Scan 与 Code Signing**：审核和扫描判断行为风险；签名证明代码来源与完整性。恶意软件也可以拥有合法签名，因此两者必须并存。
* **Certificate Chain 与 App Update Identity**：证书链证明签名主体可信；更新还要满足该主体与旧 App 身份的连续关系。
* **App Store Review 与 Runtime Security**：商店审核是安装前治理；sandbox、permission、TCC、AppOps 等是设备运行期 enforcement。
* **Sideloading 与 Unsigned Code**：侧载表示非默认商店分发，不等于可以跳过平台签名和安装器检查。
* **Developer Mode 与 Production Trust**：开发模式放宽调试和安装入口，不应被理解为正式分发身份或运行时权限的替代物。

本章结论
--------

移动平台通过分发链把“第三方代码能否进入设备”纳入整体信任模型。正确分析安装问题时，应把渠道治理、签名身份、安装器准入、组织策略和运行时安全分开；只有前一层明确放行，后一层才有机会继续执行。