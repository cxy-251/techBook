第139章：Apple URLSession, Network.framework, NEProvider, TLS, System Policy
=============================================================================

核心知识点
----------

* Apple 网络主链可抽象为 ``App → URLSession / Network.framework → System Network Services → Path/Trust/Extension Policy → Kernel Network Stack → Interface``。
* ``URLSession`` 面向 HTTP/HTTPS、缓存、cookie、认证、后台上传下载与系统托管任务；Network.framework 更接近 connection、listener、path 与协议栈控制。
* App 声明网络意图，系统决定实际路径。Wi-Fi、cellular、VPN、Low Data Mode、接口成本和网络可达性都由系统统一评估。
* ``URLSessionConfiguration.background`` 把长时间上传/下载交给系统托管，使传输生命周期与 App 进程生命周期分离。
* ``allowsCellularAccess``、``allowsExpensiveNetworkAccess``、``allowsConstrainedNetworkAccess`` 等配置表达业务是否接受蜂窝、高成本或受限路径，而不是直接指定网卡。
* ``NWConnection`` 暴露连接状态，``NWPath`` 暴露路径状态、接口类型、``isExpensive``、``isConstrained`` 等系统判断，适合自定义协议和长连接。
* TLS trust evaluation 是系统安全边界的一部分。证书链、主机名、系统 trust store、ATS、自定义 challenge handling 与 pinning 都可能影响连接。
* ATS 用于收束不安全传输和弱 TLS 配置。App 的例外配置应理解为安全策略例外，不是普通网络调优开关。
* Network Extension 提供 VPN、packet tunnel、content filter、DNS proxy 等受 entitlement 管理的扩展能力；普通 App 不直接接管全系统网络栈。
* VPN/过滤扩展可以改变 DNS、路由和流量可见性，导致同一 URL 在扩展启用前后表现不同。
* 后台网络仍受电源、Low Data Mode、路径成本、系统调度和任务类型约束；background session 也不等于立即执行。
* 排查 Apple 网络问题应先看 API/configuration，再看 ``NWPath``，再看 TLS/ATS、Network Extension，最后定位到接口、DNS、服务端或物理链路。

关键路径
--------

URLSession 请求：

::

   App creates URLSessionTask
   → session configuration expresses cost/background policy
   → system chooses path
   → DNS + connect
   → TLS trust evaluation / ATS
   → HTTP transfer
   → cache / redirect / retry / metrics
   → delegate or completion callback

后台上传：

::

   App creates background URLSession task
   → system persists transfer state
   → App may suspend/terminate
   → system waits for eligible network/power window
   → transfer proceeds outside App process lifetime
   → system relaunches/notifies App for completion handling

概念辨析
--------

* **URLSession 与 Network.framework**：前者偏 URL/HTTP 任务，后者偏连接、协议和路径级控制。
* **Expensive 与 constrained**：expensive 表示路径成本高，constrained 表示用户/系统要求减少数据使用；语义不同。
* **Background transfer 与 background execution**：系统可继续托管传输，不代表 App 进程获得无限后台 CPU。
* **TLS trust 与 ATS**：trust 判断服务器身份是否可信，ATS 是更高层的平台传输安全策略。
* **Network Extension 与普通 socket**：扩展拥有受 entitlement 控制的网络中介能力，普通 App 只通过公开网络 API 发起请求。

本章结论
--------

Apple 网络模型的核心是 ``App Intent → Framework → System Path/Trust Policy → Extension Boundary → Kernel/Interface``。App 可以表达连接需求和成本容忍度，实际路径、安全判断、后台时机和扩展介入由系统统一控制。