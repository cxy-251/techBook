第133章：NFC, Secure Element, Wallet, Payment Boundary
=======================================================

核心知识点
----------

* NFC 的同一次“碰一碰”可能走完全不同的系统路径：reader/writer、card emulation、Secure Element、Wallet/payment。先判断角色，再判断权限与路由。
* 稳定硬件链是 ``RF/Antenna → NFC Controller → System NFC Service → Host App or Secure Element/Wallet``。Controller 负责近场链路，系统负责路由和策略。
* Reader/writer 模式中，手机主动发现 tag；Card emulation 模式中，外部终端把手机当作一张卡，系统必须决定 APDU 路由到 host 还是 off-host secure element。
* NDEF 是常见标签数据格式，message 由 record 组成，可表达 URI、文本、MIME 或外部类型。它解决 payload 语义，不解决支付安全。
* Tag dispatch / reader session 的核心是“短时、前台、用户可感知”的受控访问。物理发现、session 生命周期和应用 payload 解析是不同层。
* HCE 把 APDU 路由到主 OS 上的 host service；Secure Element 把凭证和密码学操作隔离在更强安全边界内。两者的密钥位置和系统控制权不同。
* AID 用于 card application 选择。支付、门禁、交通和会员卡可以都使用 card emulation，但默认应用、AID 冲突、交易类别和平台策略不同。
* 支付凭证不应等同于真实银行卡号或普通 tag 数据。Wallet/SE 常保存设备化 token、动态交易材料和受控凭证状态。
* Android 常见 reader 路径是 ``NfcAdapter → NFC Service → HAL/vendor stack → Controller → Tag``，HCE 路径则通过 ``HostApduService`` 处理被系统路由的 APDU。
* Apple Core NFC 主要提供受控 reader session；Wallet、Secure Element 和支付凭证属于更严格的平台控制面，普通 App 并不获得通用 SE 控制权。
* NFC 访问经常要求前台 session、用户手势、设备支持、entitlement/permission 与系统 UI；这些条件比“硬件支持 NFC”更接近真实能力边界。
* NFC 兼具硬件能力、身份凭证和支付安全三种角色，因此它的系统策略比普通近距离数据传输更严格。

关键路径
--------

标签读取：

::

   user brings phone near tag
   → NFC controller detects/activates tag
   → system NFC service
   → NDEF / tag technology parsing
   → foreground dispatch or reader session
   → App validates payload
   → business result

支付/凭证：

::

   terminal initiates contactless session
   → NFC controller
   → route by AID / platform policy
   → HCE host service or Secure Element / Wallet
   → credential + cryptographic transaction state
   → APDU response
   → terminal/network verification

概念辨析
--------

* **NFC tag 与 card emulation**：tag 模式读取外部载体，card emulation 让手机向外部 reader 响应为一张卡。
* **NDEF 与 APDU**：NDEF 是标签内容格式，APDU 是卡片应用命令/响应单元；层级和用途不同。
* **HCE 与 Secure Element**：HCE 由主 OS/App service 处理 APDU，SE 把凭证和密码学逻辑放在隔离安全环境。
* **Reader session 与 payment session**：普通 reader session 服务 tag 读取，支付会话还受 Wallet、凭证、默认应用和金融网络规则约束。
* **NFC hardware support 与 app capability**：设备有 NFC controller，不代表任意 App 都能使用支付、SE 或后台读卡能力。

本章结论
--------

NFC 的稳定模型是 ``Near-Field Link → System Routing → App/Wallet/SE Capability → Security Policy``。判断一次 NFC 失败时，应先确定当前是 tag、HCE 还是 Secure Element 路径，再检查前台会话、权限/entitlement、AID 路由、凭证状态和终端协议，而不是把所有问题归结为“手机 NFC 不工作”。