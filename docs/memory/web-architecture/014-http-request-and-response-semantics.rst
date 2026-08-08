HTTP Request and Response Semantics
===================================

核心知识点
----------

* HTTP request/response 是 browser、proxy、CDN、server、cache 和 client state machine 共同理解的跨 runtime 控制面。
* Request 由 method、target URL、headers、body 与当前请求上下文共同构成；Response 由 status、headers、body 与缓存/重定向/凭据语义共同构成。
* Method 表达操作意图。``GET`` 偏读取，``POST`` 偏提交处理，``PUT`` 偏完整替换，``PATCH`` 偏局部修改，``DELETE`` 表达删除；服务端实现应与安全性、幂等性和重试语义一致。
* Status code 不是装饰性数字，而是系统级控制信号：2xx 推进成功状态，3xx 改变位置或验证路径，4xx 表示请求/上下文不可接受，5xx 表示服务端或上游失败。
* Headers 传递内容类型、身份、前提条件、语言、缓存、版本和安全控制；body 只承担 representation 或 mutation payload 的一部分语义。
* 写入请求发生超时，并不等于服务器没有执行。需要幂等键、版本条件、唯一约束或后续状态查询来恢复不确定结果。
* Conditional request 如 ``If-Match`` + ``ETag`` 能把并发修改与资源版本显式连接，减少静默覆盖。

关键路径
--------

读取路径：

``User Intent → Browser → GET URL + Headers → Cache/CDN → Server → Database → Status/Headers/Body → Browser State → UI``

写入路径：

``User Action → POST/PUT/PATCH/DELETE → Identity + Validation + Preconditions → Durable Write → Response Status/Version → Cache/UI Reconciliation``

并发保护：

``GET resource + ETag v7 → user edits → PATCH + If-Match v7 → server compares current version → write or 412/409 → reread/merge``

失败恢复：

``network timeout → unknown server outcome → idempotency/version/status query → deterministic client state``

概念辨析
--------

* **Method vs URL**：URL 定位目标资源；method 表达希望对目标执行什么语义。
* **HTTP 成功 vs 业务成功**：收到 HTTP response 只说明协议交互完成；业务是否成功仍要看 status 和 representation。
* **安全 method vs 安全系统**：GET 的请求意图应是读取，但服务器实现错误仍可能产生副作用。
* **幂等 vs 可安全重试**：协议上的幂等语义有助于重试，具体业务仍需处理超时、并发和外部副作用。
* **401 vs 403**：401 主要指向认证/凭据问题；403 表示服务端理解请求但拒绝授权。
* **409 vs 412**：409 常表达资源状态冲突；412 明确表示请求给出的前提条件失败。

本章结论
--------

HTTP 的稳定性来自结构化语义。设计或排查接口时，应从 method + URL 开始，再看 request context、headers、body、status 与 response metadata；尤其在写入、并发和重试路径中，必须让协议语义与资源状态所有权保持一致。