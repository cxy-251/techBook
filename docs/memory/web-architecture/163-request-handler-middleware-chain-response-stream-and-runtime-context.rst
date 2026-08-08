第163章：Request Handler, Middleware Chain, Response Stream, and Runtime Context
================================================================================

核心知识点
----------

* Request handler 把 HTTP 输入转换成应用行为：method、URL、headers、cookies、body、abort signal、request id、region 和 deadline 都可能进入当前请求上下文。
* Middleware chain 是 handler 之前的控制流层，可承担 request id、日志、CORS、限流、认证、tenant、locale、body parsing、cache 判断和 redirect。
* Middleware order 是安全和资源控制契约。日志/错误捕获、协议判断、限流、认证、tenant、body parsing、业务 handler 的顺序会直接改变成本与权限边界。
* Middleware 可以短路请求。返回 ``401/403/429/redirect/preflight`` 后，后续 handler 不再执行，因此诊断时必须知道请求在哪一步结束。
* Request body 通常是一次性流；前置 middleware 读取 body 后，后续 handler 必须使用已解析结果、clone/tee 或其他显式策略。
* Runtime context 承载平台能力，例如 env、region、logger、request id、cache/database binding、deadline、``waitUntil`` 和 tracing span。
* Request 描述“调用方发来了什么”，context 描述“当前 runtime 允许做什么”；把二者混成全局状态会模糊生命周期与信任边界。
* Response stream 允许逐步输出 HTML、SSE、CSV、AI token 或大对象，同时必须处理客户端断开、backpressure 和平台 timeout。
* Response body 一旦开始发送，status、redirect 和部分 headers 就可能不可逆；错误策略必须在首字节发送前规划。
* Request handling 是完整 pipeline，而不是单个函数：platform entry、middleware、route、data access、stream、error boundary、logging、metric 和 close 都要闭环。

关键路径
--------

请求处理：

::

   platform entry
   → request id / outer error boundary
   → protocol/CORS/method checks
   → rate limit
   → auth + tenant
   → body parse
   → route handler
   → data access/business logic
   → response/stream
   → close log + metrics

Streaming response：

::

   decide status + headers
   → start body stream
   → produce chunks
   → respect backpressure/abort signal
   → close or encode stream-level error

概念辨析
--------

* **Request 与 Runtime Context**：request 来自调用方，context 来自平台、框架和前置 middleware。
* **Middleware 与 Handler**：middleware 改写或短路路径，handler 承担最终业务处理。
* **Middleware Order 与 Code Order**：顺序是运行时控制流和安全契约，不只是代码组织风格。
* **Buffered Response 与 Stream**：前者在发送前仍可整体改写，后者一旦发送首字节就进入部分不可逆状态。
* **Abort 与 Error**：abort 常代表调用方取消或连接断开，error 代表处理失败；恢复语义不同。

本章结论
--------

服务端请求应按 ``HTTP Input → Middleware Control Flow → Runtime Context → Handler → Response Commitment`` 阅读。稳定系统必须明确谁读取 body、谁建立身份、谁能短路、何时响应变得不可逆，以及日志如何覆盖整条 pipeline。