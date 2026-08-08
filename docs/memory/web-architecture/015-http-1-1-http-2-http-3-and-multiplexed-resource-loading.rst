HTTP 1.1, HTTP 2, HTTP 3, and Multiplexed Resource Loading
==========================================================

核心知识点
----------

* HTTP/1.1、HTTP/2、HTTP/3 共享大部分 HTTP 语义；主要变化发生在消息如何映射到连接、frame、stream 和传输协议。
* HTTP/1.1 下大量小资源容易产生有限连接上的排队、重复 header 与握手成本，因此早期 Web 常通过合并 bundle、sprite 等方式减少请求数量。
* HTTP/2 使用二进制 framing 和 stream multiplexing，在同一 TCP 连接上并发承载多个请求响应，并通过 header compression 降低重复字段成本。
* HTTP/2 仍运行在 TCP 上；底层丢包恢复对所有上层 stream 不可见，因此一个 TCP 连接的丢包仍可能暂停多个 active stream。
* HTTP/3 把 HTTP 语义映射到 QUIC stream；不同 stream 不需要共享全局字节顺序，单个 stream 的丢包恢复通常不会阻断其他 stream 的推进。
* Multiplexing 降低了“请求数量本身”的成本，但没有消除资源发现、依赖图、优先级、缓存、JavaScript 执行和渲染阻塞。
* 现代 bundling 的重点从“尽量少请求”转向“控制 critical dependency graph、chunk 粒度、缓存复用与发现时机”。

关键路径
--------

HTTP/1.1：

``HTML → resource discovery → limited parallel connections → queued requests/responses → parse/execute/render``

HTTP/2：

``one TCP+TLS connection → multiple HTTP/2 streams → interleaved frames → shared TCP loss recovery``

HTTP/3：

``one QUIC connection → independent request streams → stream-level progress/loss recovery → HTTP semantics``

现代资源判断：

``resource discovery → cache lookup → protocol/connection → scheduling/priority → download → parse/execute/decode → user-visible result``

概念辨析
--------

* **HTTP 语义 vs HTTP 版本**：method、status、cache 等语义相对稳定；版本主要改变传输与 framing。
* **Multiplexing vs 无限并行**：多 stream 可以并发，但带宽、CPU、server、priority 和依赖关系仍是共享资源。
* **HTTP/2 HOL vs HTTP/3 HOL**：HTTP/2 消除了应用层响应串行，却仍受 TCP 级队头阻塞；HTTP/3 用 QUIC stream 缩小该影响。
* **请求少 vs 页面快**：减少请求在 HTTP/1.1 更直接有效；HTTP/2/3 下过度合并可能损失缓存粒度和按需加载能力。
* **Chunking vs Waterfall**：代码拆分本身不保证并行；若 chunk 只有前一段 JavaScript 执行后才被发现，仍会形成瀑布流。
* **协议升级 vs 自动性能优化**：h2/h3 改善传输条件，不会修复错误 cache、过大 bundle、晚发现 LCP 资源或长任务。

本章结论
--------

HTTP 版本演进改变了多资源传输的成本模型。HTTP/1.1 更敏感于请求数和连接排队，HTTP/2/3 更适合细粒度资源与多路复用；现代架构应围绕资源依赖图、发现时机、缓存粒度和执行成本设计，而不是只依据协议名称决定 bundle 策略。