第195章：Choosing REST, GraphQL, RPC, Server Function, or BFF
==============================================================

核心知识点
----------

* API 风格选择首先看契约所有权：谁定义、谁消费、谁能同步发布、谁承担兼容和失败恢复。
* REST 适合资源边界稳定、希望 HTTP method/status/cache/ETag/CDN/OpenAPI 等基础设施参与的系统。
* GraphQL 适合多客户端需要不同字段组合、schema 能集中治理的场景；代价集中在 resolver waterfall、字段级权限和缓存复杂度。
* RPC 适合动作导向、调用双方技术栈统一、内部协作紧密的系统；开发体验好，但需要版本、运行时校验和错误 contract。
* Server Function/Server Action 适合页面与服务端写入紧密绑定的 full-stack 应用，可减少 endpoint 样板，但不会消除网络、auth、validation、retry、idempotency 与 serialization。
* BFF 适合为某类前端聚合多个后端、裁剪字段、隐藏内部拓扑和统一权限/错误语义。
* Public API 的稳定性要求高于内部调用。第三方、多端、异步发布环境需要更强版本、文档、contract test 与弃用策略。
* API 选择最终要回答输入结构、输出结构、错误形态、权限语义、缓存语义、版本策略和可观察性。
* REST 的问题常出现在页面数据过碎或页面专用 read model；GraphQL 的问题常出现在 resolver/权限/缓存；RPC 的问题常出现在跨技术栈和长期兼容。
* BFF 可以优化浏览器路径，但不能把下游服务的不一致性和错误语义“藏掉”；它仍需定义聚合失败和部分降级。
* 同一系统可以组合多种契约：公开 REST/GraphQL、内部 RPC、页面 server function、前端 BFF 并不冲突。
* API 风格真正的成本往往在演进期暴露，因此选型要评估消费者扩散、团队边界和未来迁移。

关键路径
--------

API 选择：

::

   identify consumers
   → identify ownership/release cadence
   → identify data/action shape
   → identify HTTP/cache/version needs
   → identify permission/error requirements
   → choose REST/GraphQL/RPC/Server Function/BFF
   → define compatibility and observability

BFF 聚合：

::

   browser request
   → BFF auth + input validation
   → call REST/GraphQL/RPC/internal services
   → aggregate/crop result
   → normalize errors/cache policy
   → browser response

概念辨析
--------

* **REST 与 HTTP API**：REST 倾向把资源语义映射到 HTTP，本质不只是“返回 JSON”。
* **GraphQL 与 Flexible Backend**：GraphQL 让客户端选择字段，不代表后端可以忽略 schema、resolver 成本和权限治理。
* **RPC 与 Local Function**：调用语法像函数，不代表没有网络、版本、超时、序列化和重试边界。
* **Server Function 与 API-Free**：server function 只是隐藏 endpoint 形状，服务端责任仍完整存在。
* **BFF 与 Backend Replacement**：BFF 是前端专用保护/聚合层，不替代领域服务和数据事实。

本章结论
--------

API 风格应按 ``Consumer → Contract Ownership → Data/Action Shape → Version/Cache/Permission → Failure`` 选择。没有通用最优风格；关键是让契约稳定度和调用者关系匹配，并让隐藏的网络与演进成本保持可见。