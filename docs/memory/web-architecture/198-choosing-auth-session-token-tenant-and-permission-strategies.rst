第198章：Choosing Auth, Session, Token, Tenant, and Permission Strategies
=======================================================================

核心知识点
----------

* Auth 策略先从主体清单开始：个人用户、组织成员、管理员、机器客户端、第三方应用、匿名访客和后台任务的身份路径不同。
* Authentication 判断“是谁”，session 延续认证结果，authorization 判断“能做什么”，tenant boundary 决定“在哪个组织/客户范围内”。
* Browser-centered Web 应用通常适合 server-authoritative session cookie；浏览器自动携带 cookie，server 每次重建 session、tenant 和 permission context。
* Session cookie 需要 HttpOnly、Secure、SameSite、轮换、idle/absolute timeout、revocation 与敏感操作重新认证；CSRF 仍需独立处理。
* Token 更适合 API、mobile、third-party 和 service-to-service 调用；必须明确 issuer、audience、scope、expiration、storage、refresh 和 revocation。
* Access token 应短生命周期；refresh token 是高价值凭据，需要更严格存储、轮换、撤销和异常检测。
* Token 不等于授权结论。Resource server 仍需验证 issuer/audience/expiration/scope，并结合 tenant、resource ownership 和 policy 决定操作权限。
* OIDC/SSO 适合企业身份、第三方登录和多应用 federation；外部 ``issuer + subject`` 只是身份映射入口，应用仍需维护内部 account/membership。
* Tenant 必须进入 URL/route、database predicate、cache key、background job、log、audit、billing 和 search/index 设计，不能只放一个 UI 下拉框。
* Permission model 要匹配资源和操作复杂度。简单角色、RBAC、resource ownership、ABAC/tenant policy 应按业务需要组合。
* Auth state 必须可恢复：session/token 过期、MFA、权限变化、logout、跨 tab 和 reauthentication 都要保留安全上下文与用户意图。
* Security strategy 必须按完整用户流测试，包括登录、退出、刷新、过期、越权、跨租户、CSRF、XSS 后果和敏感操作再认证。

关键路径
--------

浏览器请求：

::

   request + cookie
   → validate server session
   → identify user
   → resolve current tenant
   → load membership/permission
   → authorize resource + operation
   → read/write tenant-scoped data/cache
   → audit + response

Token API：

::

   Authorization token
   → verify issuer/signature/introspection
   → verify audience + expiry + scope
   → resolve subject/tenant
   → resource-level permission check
   → execute operation

概念辨析
--------

* **Authentication 与 Authorization**：前者确认主体，后者决定具体资源和操作权限。
* **Session 与 Cookie**：session 是服务端会话状态，cookie 常只是浏览器携带的 session identifier。
* **Token 与 JWT**：token 是凭据概念，JWT 只是其中一种可携带 claims 的格式。
* **Scope 与 Resource Permission**：scope 限制接口能力，资源权限仍需结合 tenant、ownership 和 policy。
* **Tenant 与 Role**：tenant 定义隔离范围，role 描述该范围内的粗粒度权限属性。

本章结论
--------

身份架构应按 ``Subject → Credential/Session → Tenant → Resource Permission → Data/Cache Boundary → Recovery`` 设计。Cookie、token、OIDC、RBAC 都只是实现机制；可靠系统必须让主体、租户、权限和过期恢复贯穿所有数据与运行时路径。