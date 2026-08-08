第139章：Apple URLSession, Network.framework, NEProvider, TLS, System Policy
===============================================================================

核心知识点
----------

* Apple 网络主链可压缩为 ``App → URLSession / Network.framework → System Network Policy → TLS Trust / Network Extension → Kernel Network Stack → Wi-Fi / Cellular``。
* ``URLSession`` 适合 HTTP/HTTPS、缓存、cookie、认证、后台上传下载和系统托管任务；``Network.framework`` 更接近连接级控制，适合 TCP、UDP、TLS、自定义协议与 path 观察。
* App 表达的是 endpoint、task、是否允许 cellular/expensive/constrained path 等业务约束；系统决定实际路径、接口和调度时机。
* ``URLSessionConfiguration.background`` 把长时间上传下载交给系统托管，使网络传输生命周期与 App 进程生命周期解耦。
* ``allowsExpensiveNetworkAccess`` 与 ``allowsConstrainedNetworkAccess`` 分别表达是否接受高成本与受限路径；它们是业务约束，不是手动选网卡。
* ``NWPath`` 的 ``status``、``isExpensive``、``isConstrained`` 与 interface type 是系统对当前路径的公开判断，App 应据此降级或延迟任务。
* ``NWConnection`` 暴露 setup/waiting/ready/failed 等连接状态，使连接建立问题与应用协议问题可以分开定位。
* TLS trust evaluation 仍受系统 trust store、证书链、主机名、ATS、企业证书与 App 自定义 pinning 影响。换成 Network.framework 不会绕过平台信任模型。
* App Transport Security 是网络安全策略边界之一，要求安全传输配置符合平台默认安全要求；例外配置应被当作特殊兼容策略。
* Network Extension 提供 VPN、packet tunnel、content filter、DNS proxy 等受控扩展能力；普通 App 不直接接管系统全部网络栈。
* VPN 或过滤扩展介入后，App 的有效路径可以与物理 Wi-Fi/cellular 不同，排查时应同时看 extension 与 ``NWPath``。
* Background URLSession、push、低数据模式和电源状态共同决定后台网络执行机会；Background capability 不代表无限后台运行权。
* Apple 私有 daemon 和内部 IPC 不是稳定应用契约。可靠分析应以 Framework 状态、错误、task metrics、path 和系统策略为证据。

关键路径
--------

URLSession 请求：

::

   App URLRequest
   → URLSessionConfiguration
   → system path policy
   → DNS / connection establishment
   → TLS trust + ATS evaluation
   → HTTP transfer
   → cache / retry / background scheduling
   → delegate / completion

Network Extension 路径：

::

   App or managed policy enables extension
   → Network Extension provider
   → tunnel/filter/DNS policy
   → effective system path
   → kernel network stack
   → physical Wi-Fi / cellular
   → remote endpoint

概念辨析
--------

* **URLSession 与 Network.framework**：前者偏 URL/HTTP 任务和系统托管，后者偏连接、协议栈与 path 控制。
* **Expensive 与 constrained**：expensive 表示系统认为路径成本高，constrained 表示处于数据受限模式；语义不同。
* **Framework policy 与 interface selection**：App 声明能否接受某类路径，最终路由和接口仍由系统选择。
* **ATS 与 TLS**：TLS 是安全传输协议，ATS 是 Apple 对 App 网络安全配置施加的平台策略。
* **Network Extension 与 ordinary socket API**：扩展可参与 VPN/过滤/代理类系统能力，普通 App 网络请求只是被这些能力影响。

本章结论
--------

Apple 网络应按 ``API Intent → Path Policy → Trust/Extension Policy → Kernel Path → Interface`` 阅读。App 的正确职责是声明网络需求并处理系统状态，路径选择、TLS 信任、后台调度和 VPN/过滤边界由平台统一控制。