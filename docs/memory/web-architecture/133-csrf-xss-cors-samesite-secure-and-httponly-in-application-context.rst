第133章：CSRF, XSS, CORS, SameSite, Secure, and HttpOnly in Application Context
==============================================================================

核心知识点
----------

* 应用安全必须把 browser rules、server checks、rendering context 与 deployment policy 放到同一请求路径中；任何单一机制都只能覆盖部分风险。
* CSRF 利用浏览器自动附带 cookie 的行为，让用户在已登录状态下向目标站点发送非预期写请求。服务端必须在 mutation 前验证请求来自受信流程。
* CSRF 防护可组合 SameSite、CSRF token、Origin/Referer、Fetch Metadata、用户确认与正确 HTTP method；核心原则是“有 cookie”不能等价于“用户主动执行”。
* XSS 把攻击者数据变成受信 origin 内的可执行脚本。根本防线是输出编码、安全 DOM sink、HTML sanitization、框架默认转义和 CSP，而不是只做输入过滤。
* HttpOnly 只能阻止 JavaScript 直接读取 cookie；XSS 仍可能在当前 origin 发起带 cookie 的敏感请求，因此 HttpOnly 不是 XSS 的完整解决方案。
* Secure 限制 cookie 通过安全传输发送；SameSite 约束跨站 cookie 行为。它们会直接影响 CSRF、OAuth/OIDC 回跳、支付回调和多域产品流程。
* CORS 控制“浏览器是否把跨源响应暴露给脚本”，不承担服务端身份鉴权。攻击者能否发请求与脚本能否读响应是两个问题。
* CSP 是脚本执行层防线，可限制 script source、inline execution、frame embedding 等；它是纵深防御，不能替代正确输出编码与服务端授权。
* 敏感 endpoint 应首先保持 HTTP 语义正确：GET/HEAD 不应改变关键服务端状态；写操作使用 POST/PUT/PATCH/DELETE 并执行 auth、authorization、CSRF 与业务校验。
* Cookie 属性、CORS、CSP、COOP/COEP、HSTS 等安全 header 必须与实际 auth、embedding、asset、redirect 和 deployment 架构一致；错误配置可能直接破坏合法流程。
* 稳定分析方法是先判断风险发生在哪个边界，再选择该边界真正能执行的控制，而不是堆安全 header。

关键路径
--------

受保护 mutation：

::

   browser user action
   → cookie / credentials / same-site rules
   → HTTP request
   → server session validation
   → CSRF / Origin / Fetch Metadata check
   → authorization + input validation
   → database mutation
   → response security headers
   → safe rendering in browser

XSS 风险路径：

::

   untrusted input
   → persisted or returned data
   → rendering context
   → text sink / attribute / URL / HTML / script
   → encode or sanitize for that exact context
   → CSP limits remaining execution surface

概念辨析
--------

* **CSRF 与 XSS**：CSRF 借用浏览器附带的凭据发请求；XSS 让攻击者代码在受信页面 origin 内执行。
* **CORS 与 Authorization**：CORS 是浏览器读取跨源响应的策略，authorization 是服务端是否允许当前主体访问资源。
* **HttpOnly 与 XSS 防护**：HttpOnly 降低 cookie 被读取的风险，不能阻止注入脚本代表用户发同源请求。
* **SameSite 与 CSRF Token**：SameSite 是浏览器发送规则，CSRF token 是应用写路径的请求绑定证据，两者可叠加。
* **CSP 与 Output Encoding**：CSP 限制脚本执行，output encoding/sanitization 阻止数据变成代码；职责不同。

本章结论
--------

应用安全应按 ``Browser Credential Rules → Server Request Validation → Resource Authorization → Safe Rendering → Security Headers`` 分层设计。CSRF、XSS、CORS、cookie attributes 和 CSP 必须各自解决对应边界的问题，组合后才能形成完整防线。