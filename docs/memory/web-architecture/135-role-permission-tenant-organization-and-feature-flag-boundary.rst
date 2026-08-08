第135章：Role, Permission, Tenant, Organization, and Feature Flag Boundary
========================================================================

核心知识点
----------

* Role 是粗粒度身份属性，Permission 是操作级能力，Tenant/Organization 是数据与成员作用域，Feature Flag 是运行时能力开关；四类对象不能混成一个布尔权限。
* Role 常表达 owner/admin/editor/member/viewer 等身份，但必须带 scope。用户可能在不同 organization 中拥有不同 role，因此 role 应归属 membership，而非全局 user 字段。
* Permission 更接近 ``subject + action + resource + context``，例如 ``user:invite``、``invoice:read``、``project:archive``；它适合统一驱动 API、UI capability 和后台任务。
* Tenant/Organization 决定数据隔离、成员关系、计费、配置、域名和资源归属。请求中的 organization slug 只是输入，服务端必须解析成可信 id 并在所有后续查询中保持作用域闭合。
* 多租户系统的关键风险是跨租户数据混入。数据库 query、cache key、background job、audit log、search index 都必须携带正确 tenant/organization scope。
* Feature Flag 不只是 UI 显示开关。它可能改变 API、schema、experiment、部署路径和权限行为，因此必须在可信 runtime 中参与 capability 计算。
* UI 是否显示按钮应从可信策略派生；但前端 capability 仍是快照。执行 mutation 时必须重新计算 tenant、membership、permission、subscription、flag 与资源状态。
* 权限会随时间变化：成员被移除、role 改变、订阅过期、tenant 冻结、flag 关闭、资源转移后，session、cache、UI 和 API 都需要重新评估。
* Cache key 至少要覆盖会影响权限的作用域，例如 user、tenant、organization、policy version、membership version、flag version；跨租户共享缓存是直接的数据泄漏路径。
* 权限架构本质也是数据架构：membership 表、resource owner、relation、policy、audit 和 cache schema 共同决定授权是否可证明。
* 稳定策略应“集中语义 + 局部上下文”：集中定义 action/permission 与决策规则，每个调用点提供当前资源、tenant 和业务状态。

关键路径
--------

SaaS 能力判断：

::

   trusted identity
   → tenant / organization resolution
   → membership + scoped role
   → permission mapping
   → resource ownership / business state
   → subscription / feature flag
   → allow or deny operation
   → tenant-scoped database write
   → audit + capability refresh

权限变化传播：

::

   membership / role / plan / flag changes
   → bump policy or membership version
   → invalidate trusted caches
   → session/request reloads current policy
   → API re-evaluates
   → UI capability converges

概念辨析
--------

* **Role 与 Permission**：role 是粗粒度身份集合，permission 表达具体可执行动作。
* **Tenant 与 Organization**：两者都可形成作用域；具体产品可能一一对应，也可能一 tenant 多 organization，但数据归属必须明确。
* **Feature Flag 与 Authorization**：flag 控制能力是否开放，authorization 决定主体是否有权执行；flag 不能绕过权限。
* **UI Capability 与 Operation Permission**：UI capability 用于展示，operation permission 在可信运行时决定真实操作。
* **Global Role 与 Scoped Role**：全局管理员与组织管理员的资源集合不同，role 名称必须和 scope 一起解释。

本章结论
--------

权限系统应按 ``Identity → Tenant/Organization → Membership/Role → Permission → Resource Context → Feature/Plan → Data Scope`` 阅读。真正可靠的授权不是一张 role 表，而是身份、关系、资源归属、运行时策略、缓存和审计共同形成的可验证数据路径。