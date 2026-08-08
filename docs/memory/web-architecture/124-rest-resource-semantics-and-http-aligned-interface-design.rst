REST Resource Semantics and HTTP-Aligned Interface Design
=========================================================

核心知识点
----------

* REST 的核心不是“返回 JSON”，而是让资源身份、HTTP method、status code、representation、cache header 与 validator 共同表达稳定接口语义。
* URL 负责资源身份，query parameter 负责集合视图，request body 负责写入内容；把易变状态写进路径会让状态变化误变成资源身份变化。
* ``GET`` 应保持读取语义；``POST`` 常用于创建资源或提交命令；``PUT`` 表达完整替换；``PATCH`` 表达部分修改；``DELETE`` 表达删除或移除。method 语义影响安全性、幂等性、缓存与重试。
* 非幂等写入需要业务级 idempotency；条件更新需要 ``ETag`` / ``If-Match``、version 等前提，避免基于旧 representation 覆盖新事实。
* status code 是 contract surface：``201`` 表示创建、``202`` 表示已接受异步处理、``204`` 表示成功无 body、``401/403`` 区分身份与权限、``409/412`` 表达状态或前提冲突、``429`` 表达限流。
* REST 资源不必等于数据库表。取消、导出、审批等动作可以被建模为可寻址的 command/result resource，只要它们具有稳定业务含义。

关键路径
--------

``User Action → Browser/Form/Fetch → Method + URL + Headers + Body → Proxy/CDN/Gateway → Route Handler → Auth/Domain/Transaction → Status + Representation + Cache Headers → UI``。

读路径优先检查资源 URL、query、cache validator 与 response freshness；写路径优先检查 method 语义、幂等性、条件请求、事务提交和 mutation 后的缓存失效。

资源更新发生冲突时，客户端不能直接覆盖。稳定路径是 ``GET representation/version → PATCH/PUT with precondition → 412/409 on mismatch → reload/merge/retry``。

概念辨析
--------

* **resource vs database row**：resource 是公共 contract 中可命名对象；内部可由多个表、服务或计算结果组成。
* **POST vs PATCH**：POST 常让目标资源自行解释命令或创建子资源；PATCH 明确对已有资源应用部分修改。
* **idempotent method vs idempotent business operation**：协议语义只给出预期效果；实际副作用、邮件、支付和外部调用仍需业务去重。
* **404 vs 403**：404 表示不存在或安全地隐藏存在性；403 表示已识别主体但无权访问。选择必须成为稳定安全 contract。

本章结论
--------

REST 的价值来自让 HTTP 基础设施理解接口语义。资源身份、method、status、validator、cache policy 和错误表达必须一起设计，才能获得可靠的缓存、重试、并发控制和可观测性。