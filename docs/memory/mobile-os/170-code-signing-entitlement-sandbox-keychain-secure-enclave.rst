第170章：Code Signing, Entitlement, Sandbox, Keychain, Secure Enclave
=====================================================================

核心知识点
----------

* Apple App 安全链可以按 ``Code Signing → Entitlement → Sandbox → TCC → Keychain → Secure Enclave`` 理解，每一层解决不同问题。
* Code Signing 把代码、Team ID、Bundle ID、证书、嵌入 framework 与 entitlement 绑定为可验证身份，是安装、启动和服务授权的基础。
* Entitlement 是签名中携带的受控能力声明，例如 App Groups、Keychain Access Groups、Push、Network Extension；源码里调用 API 不能替代 entitlement。
* Sandbox 把 App 限制在最小资源集合中，普通 App 只能访问自己的 container、授权的共享组、用户选择资源和系统代理能力。
* TCC 管理相机、麦克风、定位、相册、通讯录等隐私资源的用户授权；用户“允许”只改变该隐私授权状态，不会绕过签名、entitlement 或 sandbox。
* Keychain 以 item、access group、accessibility、access control 为核心保存秘密；主 App 与 Extension 共享秘密依赖匹配的签名身份与 access group。
* Secure Enclave 是硬件隔离安全域，可保护私钥和认证操作；App 通常拿到的是密钥引用和授权结果，而非导出硬件私钥原文。
* Provisioning Profile、Team ID、Bundle ID 和 entitlement 共同形成 App Identity，Debug/Release/Profile 差异会直接改变能力结果。

关键路径
--------

* App 准入路径：``bundle / executable → code signature verification → profile / entitlement → process identity``。
* 隐私资源路径：``Framework API → usage description → TCC state / prompt → system service check → camera/location/photos/...``。
* Keychain 路径：``App identity → keychain access group → item query → accessibility / access control → result``。
* Secure Enclave 路径：``Security framework → key reference + policy → LocalAuthentication / passcode state → Secure Enclave operation → success/error``。
* 主 App 与 Extension 共享数据时先区分 App Group container 与 Keychain Access Group：前者共享文件/偏好，后者共享秘密 item。
* 出现“本地可用、发布失败”时应检查最终签名产物与 provisioning entitlement，而不是只看 Xcode Capability 页面。

概念辨析
--------

* ``Code Signing`` 证明代码身份和完整性；``Provisioning Profile`` 约束某次签名/安装可携带的能力，两者相关但不等同。
* ``Entitlement`` 是平台资格；``TCC permission`` 是用户隐私授权。一个通过不代表另一个也通过。
* ``Sandbox`` 解决进程资源隔离；``Keychain`` 解决秘密持久化，不能把 Keychain 当作普通 App container 文件。
* ``Keychain access group`` 与 ``App Group`` 都支持跨 target 共享，但共享资源类型和服务完全不同。
* ``Secure Enclave`` 不是所有 Keychain 数据的存储位置；它主要提供隔离密钥和安全操作能力。

本章结论
--------

Apple App 安全不是一个“权限开关”，而是一条连续信任与能力检查链。排查受控能力时，先确认签名身份，再确认 entitlement，随后检查 sandbox 与 TCC，最后检查 Keychain item 条件或 Secure Enclave 认证策略。把这些层级分开，才能解释用户已授权但 API 仍失败、Extension 无法共享数据、分发版本能力变化等问题。