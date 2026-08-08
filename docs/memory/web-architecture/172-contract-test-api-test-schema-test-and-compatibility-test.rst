第172章：Contract Test, API Test, Schema Test, and Compatibility Test
====================================================================

核心知识点
----------

* Contract test 保护独立部署边界，验证 consumer 与 provider 对 request、response、error、header、version 和行为的共享理解仍然成立。
* Contract 的核心对象是跨 runtime 消息，而不是 provider 内部实现。浏览器/BFF、BFF/service、service/event consumer 都可以拥有独立 contract。
* API test 直接通过 HTTP 或等价协议入口验证 method、path、status、headers、body、auth、CORS、rate limit、idempotency 和 error shape。
* HTTP status、header 与 body 共同组成接口语义。只验证 JSON 字段会漏掉 cache、credential、redirect、CORS 和 retry 控制信号。
* Schema test 把“类型声明”变成运行时证据。TypeScript 只能约束源码调用，网络 JSON、事件 payload、数据库映射仍需 runtime schema 验证。
* Schema 应覆盖成功和失败两侧。错误路径如果返回 HTML、纯字符串或框架默认对象，会让客户端恢复逻辑产生二次故障。
* Compatibility test 保护 version skew：旧浏览器 bundle、旧 Service Worker、旧 CDN cache、新 server、旧 server 与新 client 可能同时存在。
* API 演进应优先 additive change、optional field、stable error code、deprecation 和兼容窗口，避免直接删除、改名或改变字段语义。
* Consumer-driven contract 让消费方明确自己真正依赖的字段和分支，provider 在发布前验证这些期望仍被满足。
* Failure cases 也是 contract：invalid input、401/403、409 conflict、timeout、duplicate request、stale version、rate limit 都需要稳定语义。
* Contract testing 的目标不是冻结接口，而是让接口能够在自动验证的兼容约束下持续演进。

关键路径
--------

接口发布验证：

::

   consumer expectations
   → executable contract/schema
   → provider implementation
   → protocol/API tests
   → old/new client-server combinations
   → CI/release gate

HTTP API 证据：

::

   method/path/headers/body
   → auth + validation
   → status + response headers
   → response/error schema
   → idempotency/cache/CORS behavior

概念辨析
--------

* **Contract Test 与 API Test**：contract test 保护通信双方的共享约定，API test 更关注实际协议入口行为。
* **Schema 与 Type**：schema 可在 runtime 验证真实数据，静态类型主要约束编译期源码。
* **Compatibility 与 Versioning**：version number 只是标识，compatibility test 才证明不同版本组合能否共存。
* **Consumer Contract 与 Provider Internals**：consumer 只应约束自己依赖的可观察行为，不应锁死服务内部实现。
* **Success Contract 与 Failure Contract**：错误 status、错误 body、retryability 和 conflict 语义同样是公开接口的一部分。

本章结论
--------

接口稳定性应按 ``Consumer Expectation → Protocol Contract → Runtime Schema → Version Compatibility → Release Gate`` 设计。可演进 API 不是靠文档约定，而是靠对真实消息、错误和旧版本组合的自动化证据持续证明兼容性。