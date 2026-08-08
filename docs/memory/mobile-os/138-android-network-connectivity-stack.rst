第138章：Android Network Connectivity Stack
=============================================

核心知识点
----------

* Android 网络主链可压缩为 ``App → ConnectivityManager → ConnectivityService → NetworkStack / DnsResolver / netd → Kernel Network Stack → Interface``。
* ``ConnectivityManager`` 是 App 侧入口，``ConnectivityService`` 才是系统网络状态、默认网络选择和网络请求匹配的中心。
* Wi-Fi、cellular、VPN 等通过统一网络对象向系统注册状态；``NetworkAgent`` 承载具体网络的能力、链路属性和评分，系统再做跨网络选择。
* ``NetworkCapabilities`` 需要同时看 transport、``INTERNET``、``VALIDATED``、``CAPTIVE_PORTAL``、metered、VPN 与受限属性，不能只看“已连接”。
* ``VALIDATED`` 表示系统最近实际验证了通用互联网可达性；门户 Wi-Fi 可以已经关联、完成 DHCP，却仍不具备正常外网能力。
* ``NetworkCallback`` 是 App 观察网络变化的稳定模型。``onAvailable`` 只表示网络出现，能力变化与失去网络需要分别处理。
* 默认网络不是固定 Wi-Fi 优先。系统会结合 network score、validation、成本、用户偏好、VPN、企业策略和请求约束选择。
* DnsResolver 按网络上下文执行解析；不同 ``Network`` 可以有不同 DNS。VPN、Private DNS 与 per-network resolver 会改变解析结果和失败边界。
* ``netd`` 与系统网络配置桥接内核 routing、UID rules、DNS、VPN 与接口策略；底层实现可随 Android 版本演进，但责任层保持稳定。
* ``VpnService`` 让 VPN App 建立 tun 虚拟接口；always-on、lockdown、per-app allow/deny 会改变哪些 UID 的流量必须进入 VPN。
* Data Saver、metered network、background data policy 与 UID firewall 会让“网络本身可用但某 App 后台不能联网”成为正常结果。
* 网络诊断应先确认 App 当前使用哪一个 ``Network``，再看 capabilities、DNS、VPN、UID policy，最后才看内核接口与物理链路。

关键路径
--------

默认网络选择：

::

   Wi-Fi / Cellular / VPN network agent reports state
   → ConnectivityService
   → NetworkCapabilities + score + validation
   → policy / user / VPN constraints
   → choose eligible/default Network per UID
   → publish callback to App
   → DNS + routing bound to that Network

后台受限路径：

::

   App moves to background
   → Data Saver / metered / UID policy check
   → ConnectivityService/netpolicy/netd rule
   → traffic allowed, delayed or blocked
   → App sees timeout/failure despite physical network remaining online

概念辨析
--------

* **Network 与 interface**：``Network`` 是 Android 系统网络对象，interface 是更底层的内核收发接口。
* **INTERNET 与 VALIDATED**：前者表示配置用途，后者表示系统探测确认了实际互联网连通。
* **onAvailable 与 usable Internet**：回调出现不代表 DNS、TLS 或目标服务一定可用，仍需结合 capabilities。
* **VPN transport 与 physical transport**：VPN 是逻辑网络，可以承载在 Wi-Fi 或 cellular 之上。
* **Metered 与 blocked**：metered 表示流量成本属性；是否真的禁止后台流量还取决于 Data Saver 与 UID policy。

本章结论
--------

Android 网络问题应沿 ``Network → Capabilities → DNS/VPN → UID Policy → Kernel/Interface`` 定位。真正决定 App 请求路径的是 ConnectivityService 发布给该 UID 的网络视图，而不是单个 Wi-Fi、蜂窝接口是否存在。