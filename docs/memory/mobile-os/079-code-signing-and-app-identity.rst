第079章：Code Signing and App Identity
=====================================

核心知识点
----------

* Code Signing 把“一个包文件”变成“系统可识别、可追责、可更新的 App 主体”。它同时服务完整性、发布者身份、安装准入和更新连续性。
* Android 的稳定身份核心是 ``package name + signing identity + installed UID / package record``；Apple 的稳定身份核心是 ``Bundle ID + Team ID + code signature + provisioning / entitlement context``。
* 证书证明签名主体，package / Bundle ID 证明应用命名空间，Team ID 或 signing certificate 证明开发者归属，profile / entitlement 描述可请求的受控能力。它们承担不同职责。
* 第一次安装时，系统先验证包内容和签名，再创建应用身份记录、数据目录、UID / container 和权限状态。后续系统服务依赖的是安装后的身份，不会重新相信 App 自己声称的字符串。
* 更新不是简单“覆盖文件”，而是身份延续判断。新版本必须被系统认可为原 App 的合法继任者，才能继续使用原数据目录、授权状态和密钥访问关系。
* Android 更新通常要求 package identity 与签名连续性成立；Apple 更新需要 Bundle / Team / signing / profile 等身份链保持可接受关系。
* Signature permission、Keychain access group、App Group、共享数据或受控 entitlement 等机制都建立在可靠 App Identity 之上。
* 签名错误、profile 错误、权限错误属于不同阶段：签名与 profile 多发生在构建、安装或启动准入；runtime permission 则发生在已安装 App 的能力调用阶段。

关键路径
--------

首次安装：

``Developer Key / Certificate → Signed Package → Installer Verification → Package / Bundle Identity Record → UID or Container → Sandbox → Runtime Permission / Entitlement Checks``

应用更新：

``New Signed Version → Existing Identity Lookup → Version + Signature Continuity Check → Replace Code → Preserve Data / Grants / Key Access → Launch``

运行期能力调用：

``Process → IPC Caller Identity → System Service maps caller to installed App identity → Permission / Entitlement / User Consent → Capability``

排查无法安装或无法更新时，先确认包名 / Bundle ID，再确认签名主体与证书链，再确认 profile / entitlement / 版本关系；只有安装和启动都通过后，才进入 runtime permission 和业务路径。

概念辨析
--------

* **Code Signing 与 Encryption**：签名主要证明来源和完整性，不负责隐藏代码或数据内容。
* **Package / Bundle ID 与 Display Name**：显示名称可随版本改变；package / Bundle ID 才是长期应用命名空间。
* **Certificate 与 App Identity**：证书是身份证据之一；完整 App Identity 还包含包标识、团队、安装记录和运行上下文。
* **Signing Continuity 与 Data Migration**：签名连续性让系统允许继承原身份；数据 schema 能否正确迁移仍由应用自己负责。
* **Install Trust 与 Runtime Permission**：前者回答“这段代码能否作为该 App 进入设备”；后者回答“已安装 App 此刻能否使用某项能力”。

本章结论
--------

移动平台用 Code Signing 建立 App 的长期身份锚点，再把沙箱、数据目录、权限、密钥和更新关系挂到这个身份上。分析安装、升级或共享能力问题时，应先证明“新代码仍然是同一个受信主体”，再讨论运行期授权和资源访问。