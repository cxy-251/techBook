第135章：Apple Capability Path Framework, Entitlement, Daemon, Driver
======================================================================

核心知识点
----------

* Apple 设备能力的稳定阅读模型是 ``App → Public Framework → Entitlement/Privacy/Lifecycle Policy → System Daemon → XNU / IOKit / DriverKit Boundary → Hardware``。
* Core Location、Core Motion、Core Bluetooth、Core NFC 等 Framework 提供高层对象、状态枚举与 callback；普通 App 不直接访问 GNSS、sensor hub、Bluetooth/NFC controller 或设备节点。
* Framework 入口把硬件异步性包装成 delegate、closure、notification 或 query result。App 处理的是能力状态与事件，而不是中断、寄存器或 controller command。
* Entitlement、code signature、bundle identity、sandbox、Info.plist purpose string 与用户授权共同决定 App 是否有资格请求某类能力。
* TCC/Privacy authorization 表达用户对 camera、location、Bluetooth、motion 等敏感能力的授权状态；系统 daemon 在真正资源访问前仍会结合调用者身份再次执行策略。
* Framework 到 daemon 的跨进程服务边界负责把调用者身份、请求参数、前后台状态和系统资源状态合并。具体 daemon 名称和 IPC 细节并非公开 API 契约。
* Core Location 公开的是位置、accuracy、authorization、background semantics；底层 GNSS、Wi-Fi、cellular、motion fusion 和缓存由系统服务协调。
* Core Bluetooth 公开 central/peripheral、service/characteristic 和 connection state；controller、radio scheduling、多 App scan 合并与功耗由系统持有。
* Core NFC 主要公开 reader session/tag 能力；Wallet、Secure Element 与支付凭证处于更严格的 entitlement、平台控制和用户交互边界。
* Core Motion 公开 raw/fused motion、pedometer、activity 等能力，底层 sensor hub、采样和融合由系统统一管理。
* Background Mode 不等于永久后台执行权。它只声明某类系统允许的持续能力，真正唤醒、回调频率、资源保留仍由平台策略决定。
* Apple 能力错误应优先按 ``denied / restricted / unavailable / powered-off / timeout / session invalidated`` 等状态归因到授权、系统策略、硬件状态、会话或环境，而不是猜测私有实现。
* IOKit/DriverKit/XNU 代表能力落入设备与内核边界的位置；公开 App 能观察到的是 Framework 结果，私有驱动拓扑不应被当作稳定应用契约。
* Apple 的总体模型是“受控开放”：硬件先成为系统服务能力，再通过签名、隐私、生命周期和 Framework 表面按条件开放给 App。

关键路径
--------

通用能力请求：

::

   user action / App request
   → Core Location / Motion / Bluetooth / NFC
   → declaration + entitlement + privacy authorization
   → framework sends service request with caller identity
   → system daemon checks TCC / lifecycle / resource state
   → driver/kernel boundary
   → hardware / firmware
   → daemon normalizes result/error
   → framework callback/status
   → App

失败定位：

::

   framework status/error
   → authorization denied/restricted?
   → required entitlement/purpose string/background mode?
   → foreground/session timing valid?
   → system capability enabled and hardware available?
   → resource busy / radio powered off / weak signal / timeout?
   → only then inspect deeper platform-specific evidence

概念辨析
--------

* **Framework 与 daemon**：Framework 是公开 App API，daemon 代表系统服务所有者；二者通过跨进程边界隔离 App 与硬件资源。
* **Entitlement 与 privacy authorization**：entitlement 来自签名和能力声明，privacy authorization 来自用户/系统隐私决策；两者可同时成为前置条件。
* **Sandbox 与 TCC**：sandbox 约束进程一般资源访问，TCC 更专注隐私敏感能力和用户授权状态。
* **Background Mode 与 unlimited background execution**：前者只是允许特定系统能力在后台继续受控工作，不代表 App 获得无限 CPU 或永久进程存活。
* **Public API contract 与 private implementation**：Framework 行为、状态和文档是稳定边界，私有 daemon 名称、协议和驱动实现可随系统版本改变。

本章结论
--------

Apple 设备能力的核心模型是 ``Public Framework → Identity/Entitlement/Privacy → System Service → Driver/Kernel → Hardware``。App 获得的是经过系统中介和策略计算后的能力，而不是底层设备所有权；排查能力问题时，应优先从公开状态、授权、前后台会话和资源可用性定位，再进入更深层系统边界。