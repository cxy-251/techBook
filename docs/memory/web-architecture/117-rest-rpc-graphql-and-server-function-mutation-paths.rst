REST, RPC, GraphQL, and Server Function Mutation Paths
======================================================

核心知识点
----------

* REST、RPC、GraphQL 与 Server Function 的主要差异在调用边界，不在持久化责任；四者最终都要进入可信 server boundary 完成校验、授权、事务、副作用、缓存失效和结果回写。
* REST 用 resource + HTTP method 表达意图，适合资源边界清晰、需要充分利用 status、cache、gateway 与日志语义的系统。
* RPC 用 procedure/action 名称表达业务命令，适合领域动作明确、内部系统和强业务流程；它仍然是跨网络调用，不具备本地函数的可靠性假设。
* GraphQL mutation 用 schema 定义输入、操作和返回 selection，可精确返回写入后的 UI 所需字段；业务错误和系统错误应有稳定区分。
* Server Function 把客户端引用映射到服务端执行位置，能缩短 full-stack 开发路径，但不会消除 HTTP、序列化、CSRF、权限、重试与缓存边界。
* 架构选择应围绕 contract、调用方数量、跨语言需求、缓存/网关能力、错误模型、schema 演进和 UI reconciliation，而不是围绕“哪种写法更现代”。

关键路径
--------

``User Intent`` → 选择调用包装：REST endpoint / RPC procedure / GraphQL mutation / Server Function → 序列化输入并携带身份上下文 → server runtime 解析 → runtime schema → auth / policy → transaction → durable state → side effects → cache invalidation → 将 canonical resource、错误、redirect 或 revalidation signal 返回调用方 → UI reconciliation。

对发布文章一类写入，无论调用形态如何，都应返回足够证据，例如最终 ``status``、``version``、``publishedAt`` 或冲突信息。客户端必须能依据结果判断是确认乐观状态、显示字段错误、重新读取、跳转还是进入冲突恢复。

概念辨析
--------

* **REST vs RPC**：REST 优先公开资源与 HTTP 语义；RPC 优先公开业务动作。二者都可实现稳定 contract，也都可能设计混乱。
* **GraphQL schema vs business rule**：schema 定义可传输类型和操作形状；权限、事务、唯一性和业务状态仍由 resolver 后的服务端逻辑决定。
* **Server Function vs local function**：语法像函数调用，执行实际跨 runtime、网络和序列化边界。
* **transport contract vs durable semantics**：调用层负责“怎么表达写入”；数据库与业务层负责“什么事实真正成立”。
* **error channel vs recovery model**：状态码、RPC error code、GraphQL errors 或 action result 只是载体；UI 仍需知道字段、权限、冲突、暂时失败和下一步动作。

本章结论
--------

选择 mutation API 风格时，先把共同写入路径固定，再决定哪一种调用边界最适合系统契约。任何抽象只要不能清楚回答“输入如何可信、事实何时提交、失败如何恢复、缓存如何同步”，就没有真正简化写入架构。