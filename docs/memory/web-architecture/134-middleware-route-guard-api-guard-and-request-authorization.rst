第134章：Middleware, Route Guard, API Guard, and Request Authorization
======================================================================

核心知识点
----------

* Authorization 属于可信边界。浏览器隐藏按钮、前端 route guard 只能改善体验，最终权限必须在 server、API、database policy 或其他受控 runtime 中重新判断。
* 稳定授权输入可以抽象为 ``subject + resource + action + context``。角色只是 subject/context 的一部分，资源归属、tenant、业务状态和认证强度同样可能决定结果。
* Middleware 适合早期、粗粒度请求决策：是否存在 session、tenant/host 解析、locale、A/B routing、header rewrite、维护模式、明显未认证请求的 redirect/reject。
* Middleware 通常不适合承担复杂资源级授权，尤其在 edge/runtime 受限时；它常看不到完整数据库资源、事务状态和业务上下文。
* Route guard 保护页面级入口，例如是否能进入组织设置、项目管理或 onboarding 页面。它可以生成可信 capability 快照供 UI 展示。
* API guard 保护操作级入口。即使页面允许访问，真正执行 update/delete/export/invite 等动作时仍必须重新检查当前主体、资源、动作与上下文。
* Resource ownership 必须进入授权判断。仅检查“已登录”或“role=admin”容易产生 IDOR/BOLA 类越权；查询条件应同时约束 resource id 与 tenant/user/organization scope。
* Guard 放置位置决定失败形状：middleware 常 redirect/early reject；route guard 生成 401/403/404 页面；API guard 返回稳定 JSON/RPC error；database policy 负责最后的数据隔离。
* UI capability 应由可信策略派生，但它只是快照。角色变更、组织移除、资源锁定、订阅过期后，API 仍以执行时重新计算的策略为准。
* 授权规则既要集中，以便复用、测试和审计；也要接收局部资源上下文。只有集中 role 表而没有资源事实，同样无法形成正确授权。
* 缓存也是权限边界。页面、query cache 或 capability cache 必须包含 user/tenant/policy version 等作用域，避免旧权限被跨用户或跨租户复用。

关键路径
--------

页面到操作授权：

::

   browser navigation
   → middleware early gate
   → restore trusted identity
   → route guard(page-level access)
   → render trusted capabilities
   → user mutation request
   → API guard(subject, resource, action, context)
   → tenant-scoped database query/mutation
   → audit log + response

资源级授权：

::

   request resource id
   + trusted identity
   → load resource inside tenant/user scope
   → evaluate ownership + role + permission + business state
   → deny by default or perform operation

概念辨析
--------

* **Middleware 与 API Guard**：middleware 适合早期粗筛，API guard 负责具体操作和资源级权限。
* **Route Guard 与 Authorization**：route guard 只证明可以进入页面，不证明页面里的每个 mutation 都被授权。
* **Role 与 Resource Ownership**：role 给出粗粒度身份，ownership 决定当前资源是否处于该主体可操作范围。
* **UI Capability 与 Server Policy**：UI capability 是可信策略的展示快照，server policy 是执行时最终事实。
* **403 与 404**：403 明确表示拒绝；对敏感资源也可用 404 隐藏资源存在性，但内部仍应记录真实授权失败原因。

本章结论
--------

请求授权应按 ``Early Gate → Identity → Page Access → Operation Guard → Scoped Data Access → Audit`` 分层。页面守卫不能替代 API 权限，角色不能替代资源归属；最终写入必须在可信边界用当前资源事实重新计算授权。