第081章：Apple Code Signing, Entitlement, Sandbox, Keychain, Secure Enclave
=========================================================================

核心知识点
----------

* Apple 应用安全链可按 ``Code Signing → Entitlement → Sandbox → TCC / User Consent → Keychain → Secure Enclave`` 阅读，各层分别解决代码身份、受控能力、资源边界、隐私授权、秘密存储和硬件隔离。
* Code Signing 把 Mach-O、embedded framework、Team ID、Bundle ID 与 entitlement 绑定到可校验身份中，是安装、启动、动态库加载和能力授权的前提。
* Entitlement 是签入代码身份的受控能力声明。工程中的配置只表示“请求”，provisioning / 平台策略与最终签名结果才决定运行时是否真正拥有该 entitlement。
* Sandbox 为第三方 App 建立默认受限边界。App 可直接访问自己的 container；访问 App Group、外部文档、系统服务或特殊资源需要 entitlement、用户选择、sandbox extension 或对应 framework。
* TCC 类隐私控制负责相机、麦克风、定位、照片、联系人等用户数据的授权状态。用户可在系统设置中撤销或缩小授权范围。
* Entitlement 与 TCC 是两层不同条件：前者是平台能力资格，后者是用户对敏感数据或传感器的许可。某些能力需要两者同时成立。
* Keychain 用于保存 token、密码、私钥引用等敏感小数据，并按 application identifier、access group、Data Protection 属性和访问控制策略判断调用方。
* App 与 Extension 共享 Keychain 或数据必须由同一身份体系和明确 group entitlement 支撑，不能依赖普通文件路径或进程继承。
* Secure Enclave 是独立硬件安全域，适合保护设备密钥、生物认证相关密钥操作、passcode / keybag 相关状态和不可直接导出的密钥材料。App 通常请求“用密钥做运算”，而不是读取密钥本体。
* 锁屏状态、用户认证、设备迁移、备份与 Secure Enclave 绑定会改变 Keychain item 或密钥的可用性，因此“数据还在”不代表“当前一定能解密或使用”。

关键路径
--------

受控平台能力：

``Signed App → Entitlement Check → Sandbox Boundary → Framework / XPC → System Daemon → Capability``

隐私数据访问：

``App → Public Framework → Usage Description / Authorization State → TCC-like Policy → Service / Daemon → Scoped User Data``

Keychain：

``App Identity → Security / Keychain API → Access Group + Protection Class + User Authentication Check → security service → Keychain Item``

硬件密钥：

``App → Keychain / Crypto API → Access Control → Secure Enclave → Sign / Decrypt / Key Agreement → Result``

排查共享失败时先检查签名身份、Team ID、entitlement 与 group；排查隐私资源先检查用户授权和生命周期；排查密钥先检查 access group、保护等级、认证状态和硬件绑定。

概念辨析
--------

* **Code Signing 与 Entitlement**：签名证明代码身份并保护 entitlement 不被任意篡改；entitlement 描述该身份被允许请求的受控能力。
* **Sandbox 与 TCC**：Sandbox 限制进程默认访问面；TCC 控制特定用户数据和隐私传感器授权。
* **App Group 与 Keychain Access Group**：前者主要提供共享 container 等应用组能力；后者控制哪些签名主体可访问同一组 Keychain item。
* **Keychain 与 Secure Enclave**：Keychain 是秘密数据与密钥引用的系统存储/访问服务；Secure Enclave 是硬件隔离执行环境。Keychain item 不一定都位于 Secure Enclave。
* **User Authentication 与 Data Protection**：认证可以作为某次密钥使用门槛；Data Protection 描述设备锁定状态下数据何时可解密，两者可组合使用。

本章结论
--------

Apple 平台把应用安全拆成连续判定点：先确认代码是谁，再确认它具备什么平台能力，再用 sandbox 收缩默认访问面，再由用户授权开放隐私数据，最后把高价值秘密交给 Keychain 与 Secure Enclave。定位失败时应沿这条链逐层确认，而不是把 entitlement、隐私权限和密钥保护统称为“权限问题”。