第137章：TCP IP, DNS, TLS, HTTP, Proxy, VPN
=============================================

核心知识点
----------

* 一次 HTTPS 请求应拆成 ``URL → DNS → Route/Socket → TCP/QUIC → TLS → HTTP → Proxy/VPN Policy`` 多个阶段；“网络失败”只是最终表象。
* Socket 是 App/Framework 与内核协议栈之间的核心抽象。内核维护协议状态、发送/接收缓冲区、端口、路由、拥塞控制、重传和接口选择。
* TCP 提供可靠有序字节流，UDP 提供无连接数据报；HTTP/1.1、HTTP/2 常运行于 TCP+TLS，HTTP/3 通常运行于 QUIC/UDP+TLS 1.3。
* DNS 负责把主机名映射到地址。解析结果受 per-network resolver、缓存 TTL、Private DNS、VPN DNS、企业 split DNS 和当前默认网络影响。
* DNS 结果与网络上下文必须一致。切换 Wi-Fi、蜂窝或 VPN 后，旧 DNS 结果、旧连接池和旧 route 可能形成短暂错位。
* TLS 负责版本、密钥、服务器身份和安全通道协商；系统 trust store、企业根证书、主机名校验、ATS/Network Security Config、pinning 都可能成为失败点。
* TLS 成功不等于 HTTP 成功。证书/握手错误属于安全连接阶段，401/403/404/429/5xx 属于 HTTP 应用协议阶段。
* HTTP 的连接复用、重定向、缓存、重试与协议版本会改变性能和错误传播；App 不应把所有请求都当作一次独立 socket。
* Proxy/PAC 会改变目标解析和连接路径；captive portal 会让链路已连接但互联网访问被登录页拦截。
* VPN 通过虚拟接口、路由和 DNS 接管流量。split tunnel、per-app VPN、always-on policy 会让不同 App 或不同目的地址走不同路径。
* 同一设备上“浏览器能访问但某 App 失败”时，应检查 App identity、证书策略、代理/VPN、per-app policy 与 DNS，而不是只检查 Wi-Fi 图标。
* 排查顺序应从最早失败阶段开始：解析是否成功、连接是否建立、TLS 是否完成、HTTP 是否返回、代理/VPN 是否改写路径。

关键路径
--------

HTTPS 请求：

::

   App URL
   → framework network API
   → resolve host with current network context
   → create socket / choose route
   → TCP connect or QUIC path
   → TLS handshake + trust evaluation
   → HTTP request/response
   → framework callback

VPN/代理路径：

::

   App request
   → system/app proxy and PAC evaluation
   → VPN/per-app routing policy
   → DNS selection or rewrite
   → physical/virtual interface
   → remote endpoint
   → response returns through same policy context

概念辨析
--------

* **DNS 与 routing**：DNS 解决“目标地址是什么”，routing 决定“通过哪条接口到达它”。
* **TCP 与 TLS**：TCP 提供可靠传输，TLS 在其上建立加密与身份认证；HTTP/3 则把 TLS 集成到 QUIC。
* **TLS error 与 HTTP status**：TLS 失败时 HTTP 业务通常尚未开始；HTTP 状态码说明安全通道已足以承载应用协议。
* **Proxy 与 VPN**：proxy 代理特定应用协议/连接，VPN 在更低层通过虚拟接口与路由接管流量。
* **Connected Wi-Fi 与 Internet access**：链路、IP 配置和门户登录都可能成立程度不同，只有系统 validation 更接近真实外网可用性。

本章结论
--------

网络请求必须按阶段定位：``DNS → Socket/Route → Transport → TLS → HTTP → Proxy/VPN``。移动 OS 把这些阶段放入当前网络、用户策略和应用身份中执行，因此同一 URL 在不同 Wi-Fi、蜂窝、企业网络或 VPN 环境下可以出现完全不同结果。