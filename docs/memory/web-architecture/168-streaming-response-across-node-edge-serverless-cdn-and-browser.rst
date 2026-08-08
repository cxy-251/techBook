第168章：Streaming Response Across Node, Edge, Serverless, CDN, and Browser
============================================================================

核心知识点
----------

* Streaming response 的目标是在完整结果尚未生成时先交付部分可用 body，例如 HTML shell、SSE、AI token、日志或分块报表。
* Streaming 是否真正有效取决于整条 response path：应用 runtime、serverless/edge 平台、CDN/proxy、compression/security gateway、browser consumer 都必须保留增量语义。
* 应用代码调用 ``write()`` 或返回 ``ReadableStream`` 只能证明源头支持分段输出，不证明用户会逐步看到内容。
* Node Streams 与 Web Streams 是不同但相关的流模型。Node 生态以 ``Readable/Writable/Duplex/Transform`` 为主，Fetch/edge/browser 更常使用 ``ReadableStream/WritableStream/TransformStream``。
* Backpressure 是 streaming 正确性的核心：下游消费速度低于生产速度时，生产端必须减速、暂停或排队，避免无界内存增长。
* Serverless 平台可能限制持续时间、连接、payload、buffering 和计费窗口；“平台支持 stream”不代表任意长连接都适合该 runtime。
* Edge 可以更快发出首字节，但若后续 chunk 依赖远端数据库或重型服务，持续输出仍受跨区域 RTT 和资源上限影响。
* CDN、反向代理、压缩层或安全网关可能缓冲 body，导致首字节之后迟迟没有可见 chunk；必须端到端实测。
* Browser 侧消费方式也影响渐进体验：HTML parser、Fetch reader、SSE/EventSource 等对象处理 chunk 的时机不同。
* Response 一旦发送首个 body chunk，status、redirect 和部分 headers 就可能不可修改；错误必须通过后续 chunk、stream-level event、fallback UI 或连接关闭表达。
* Client abort 应尽可能向上游传播，停止数据库读取、AI generation、大对象读取等无效工作。
* Streaming observability 应记录 first-byte、chunk cadence、buffering point、abort、backpressure、complete/incomplete 状态，而不只记录总 duration。

关键路径
--------

端到端 Streaming：

::

   browser request
   → CDN/proxy
   → Node/edge/serverless runtime
   → upstream data source
   → runtime produces chunks
   → proxy forwards without harmful buffering
   → browser progressively consumes
   → UI updates

错误边界：

::

   decide status + headers
   → commit response
   → stream chunks
   → if later failure:
      encode stream-level error / fallback / close
   → client detects incomplete stream
   → retry or recover

概念辨析
--------

* **Chunked Production 与 Progressive Delivery**：源端分块生成不代表用户端逐步收到，必须看完整链路。
* **Node Stream 与 Web Stream**：对象模型不同，可互转，但 backpressure 和平台适配要明确。
* **TTFB 与 Completion Time**：streaming 可提前首字节和可见内容，不一定缩短完整任务总时间。
* **Streaming 与 Long-Running Job**：持续响应适合有限在线输出，超长任务通常更适合 queue/job + object storage/status channel。
* **Connection Close 与 Business Error**：连接中断可能来自平台、网络或客户端取消，不一定能携带完整业务错误结构。

本章结论
--------

Streaming 应按 ``Producer → Runtime → Proxy/CDN → Browser Consumer → Backpressure/Abort`` 阅读。真正的能力不是“代码能返回 stream”，而是整条链能持续、可观测地传递 chunk，并在首字节发送后仍有明确的错误与取消恢复协议。