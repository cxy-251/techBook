DNS, TCP, TLS, QUIC, and Connection Establishment
==================================================

核心知识点
----------

* HTTP 请求真正发送前，浏览器可能先经历 DNS、地址选择、TCP 或 QUIC 建连、TLS 信任建立与应用协议协商；很多“接口慢”实际发生在 HTTP 之前。
* DNS 把 host 解析为连接候选地址，并受到浏览器缓存、系统缓存、递归解析器、权威 DNS、TTL 与 CDN 调度共同影响。
* TCP 提供可靠、有序字节流。新连接需要握手，并受 RTT、丢包、重传、拥塞控制和连接复用影响。
* HTTPS 在 TCP 场景下通常继续经过 TLS；TLS 负责服务器身份验证、密钥协商和安全上下文建立，证书 host、有效期、链路信任任一失败都可在 HTTP 前终止请求。
* HTTP/3 运行在 QUIC 上。QUIC 把安全握手、多路复用、流量控制和丢包恢复整合到新的传输模型中，不再依赖 TCP 的单一有序字节流。
* 连接复用会显著改变后续请求成本：已有连接、DNS cache、TLS session 等状态可能让第二次请求远快于第一次。
* 多个 host 会扩大连接准备面；资源域名拆分必须同时考虑 DNS、连接、证书、协议和复用成本。

关键路径
--------

首次 HTTPS 请求：

``URL → Origin → Connection Reuse Check → DNS → Address Selection → TCP Handshake → TLS Handshake → ALPN → HTTP Request``

HTTP/3 路径：

``URL → Origin → DNS → QUIC Connection + TLS 1.3 → HTTP/3 Streams → HTTP Semantics``

资源多域名路径：

``HTML origin + static origin + API origin → independent/reused DNS and connections → protocol negotiation → resource/data delivery``

诊断顺序：

``origin count → DNS time → connect time → TLS time → protocol → connection reuse → request/response time``

概念辨析
--------

* **DNS 成功 vs 连接成功**：DNS 只返回地址候选，目标端口、路由、防火墙和服务器仍可能导致连接失败。
* **TCP vs HTTP**：TCP 提供传输字节流；HTTP 定义请求、响应、method、status、header 等应用语义。
* **TLS vs HTTPS**：TLS 提供加密和身份信任；HTTPS 是 HTTP 运行在受 TLS 保护的安全传输之上。
* **QUIC vs HTTP/3**：QUIC 是传输协议；HTTP/3 是 HTTP 语义在 QUIC 上的映射。
* **首次请求慢 vs 服务端慢**：DNS、握手和 TLS 都可能增加首访延迟，不能只看应用处理时间。
* **多域名并行 vs 免费并行**：新增 origin 可能增加独立 DNS、连接与 TLS 成本，必须用实际关键路径判断收益。

本章结论
--------

一次 Web 请求的网络成本从 URL 解析就开始。排查首屏或接口延迟时，应先确认 origin、DNS、连接复用、TCP/QUIC、TLS 与协议协商，再进入 HTTP 和业务处理；否则很容易把连接层问题误判成服务器应用问题。