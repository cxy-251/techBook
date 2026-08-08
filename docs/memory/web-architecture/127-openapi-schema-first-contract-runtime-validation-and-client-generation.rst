OpenAPI, Schema-First Contract, Runtime Validation, and Client Generation
=======================================================================

核心知识点
----------

* OpenAPI 把 HTTP API 的 path、method、parameter、request body、response、schema、security 与 error shape 变成机器可读 contract artifact，可被文档、mock、gateway、SDK generator、测试与安全扫描共同消费。
* schema-first 的价值是让公共 contract 在实现前进入评审；重点不是“先写 YAML”，而是提前固定资源、错误、分页、认证、兼容和暴露边界。
* code-first 可以从 route、runtime schema 或 framework metadata 生成 OpenAPI，减少重复定义；风险是把 ORM model、内部 DTO、临时字段等实现细节误提升为公共 contract。
* public contract schema 与 implementation schema 必须区分。内部对象可以更宽，跨网络 representation 应按调用者、权限、隐私和长期兼容要求裁剪。
* runtime validation 用 contract/schema 检查真实 request/response；生成文档本身不能证明生产 handler、middleware、exception mapper 与 gateway 行为符合 spec。
* client generation 把 contract 进入开发工作流，可生成类型、调用器、mock 与测试；生成代码仍需面对 auth、timeout、retry、unknown enum、version drift 等运行时问题。
* contract artifact 必须进入 CI：schema diff、breaking-change 检查、contract test、runtime sample validation 与文档/SDK generation 应围绕同一版本链工作。

关键路径
--------

``API Requirement → Contract Artifact → Review/Diff → Server Implementation + Runtime Validation → Gateway/Middleware → Generated Client → HTTP Runtime → Contract Test/Telemetry``。

schema-first 时先评审边界再实现；code-first 时必须反向审查生成结果，确认 public representation 没有被内部模型污染。

发布前检查 ``spec → generated client → deployed server`` 是否同版本；发布后通过 contract test 和 telemetry 证明实际 status、error、field 与 security behavior 没有漂移。

概念辨析
--------

* **OpenAPI vs HTTP runtime**：OpenAPI 描述 contract；HTTP server 执行真实行为，二者需要测试证明一致。
* **schema-first vs code-first**：区别是 contract 的主要 authoring 入口，不是优劣阵营；关键是 ownership、review 和 drift control。
* **runtime schema vs business rule**：schema 检查结构、类型和局部约束；权限、库存、唯一性等仍依赖业务和持久化状态。
* **generated client vs guaranteed compatibility**：生成代码减少手写漂移，但旧 SDK、旧 bundle 和服务器演进仍需要兼容策略。

本章结论
--------

OpenAPI 的真正价值是把 API boundary 变成可审查、可生成、可验证的工程 artifact。它应连接设计、实现、客户端、测试与发布，而不是在代码完成后生成一份静态说明。