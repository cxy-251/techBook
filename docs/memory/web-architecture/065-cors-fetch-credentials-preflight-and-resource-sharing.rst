第065章：CORS, Fetch Credentials, Preflight, and Resource Sharing
=================================================================

核心知识点
----------

* CORS 是服务器对 Same-Origin Policy 的受控放宽：资源服务器通过响应头声明哪些 origin 可以读取响应，浏览器负责执行这项策略。
* 跨源请求有三个独立问题：请求是否发出、服务器是否执行业务、浏览器是否把响应暴露给 JavaScript。CORS 主要影响第三个问题。
* ``Access-Control-Allow-Origin`` 必须匹配允许的调用方。公开且无 credential 的资源可使用 ``*``；带 credential 的响应必须返回具体 origin。
* 当响应会随 ``Origin`` 改变时，共享缓存通常需要 ``Vary: Origin``，防止一个 origin 的 CORS 响应被错误复用给另一个 origin。
* 某些跨源请求会先发送 ``OPTIONS`` preflight。非简单 method、自定义 header、``application/json`` 等请求形状常会触发预检。
* Preflight 只确认“这个 origin 是否允许用这些 method/header 发后续请求”，它不是业务鉴权，也不应执行 mutation。
* ``credentials: include`` 会让跨源请求尝试携带 cookie 等 credential；服务器同时需要具体 ``Access-Control-Allow-Origin`` 与 ``Access-Control-Allow-Credentials: true``。
* Preflight 本身通常不依赖用户 session；CORS 协议处理应位于业务鉴权之前，actual request 再进入 authentication、authorization 与业务逻辑。
* CORS 不能代替 CSRF 防护。跨站请求可能携带 cookie，即使攻击页面无法读取响应，也可能触发状态修改。
* CORS 是部署契约：浏览器、API gateway、CDN、edge、serverless route、dev/preview/prod 域名都必须对 ``OPTIONS`` 和 actual response 保持一致策略。

关键路径
--------

无 preflight 的跨源读取：

``Page → fetch() → Browser 添加 Origin → API → Response + ACAO → Browser 校验 CORS → JavaScript 读取 Response``

带 preflight 的路径：

``Page → fetch(JSON/custom headers) → Browser → OPTIONS + Origin + Access-Control-Request-* → Server 返回允许范围 → Browser 校验 → Actual Request → Business Auth/Logic → Response → Browser 再校验 CORS → Page``

带 credential 的路径：

``credentials: include → cookie/credential 发送条件检查 → concrete ACAO + ACAC:true → Server session/auth → private response → Browser 决定是否暴露``

排查 CORS 时先看 Network：若有 ``OPTIONS``，先修 preflight；若 actual request 已发出，再检查 actual response 的 CORS headers、credential、``Vary`` 和缓存层。

概念辨析
--------

* CORS ≠ 服务器防火墙。它是浏览器读取策略；非浏览器客户端不受同一 SOP/CORS 执行模型限制。
* Preflight ≠ 业务请求。``OPTIONS`` 只确认后续请求形状是否允许。
* ``Access-Control-Allow-Origin: *`` ≠ 适用于登录接口。credentialed CORS 不能用 ``*`` 作为共享 origin。
* CORS 成功 ≠ 用户有权限。浏览器允许脚本读取响应后，服务器授权仍然决定能否读取或修改业务数据。
* CORS 失败 ≠ 请求一定没到服务器。actual request 可能已执行，只是响应没有被脚本读取。
* ``credentials: include`` ≠ cookie 一定发送。SameSite、Secure、第三方 cookie/partitioning 等浏览器规则仍会参与。

本章结论
--------

CORS 应记成“服务器声明、浏览器执行的跨源响应暴露协议”。判断顺序固定为 ``Origin → 是否 preflight → credential 模式 → 服务端允许范围 → actual request 鉴权 → 响应暴露 → cache key``。生产配置必须同时覆盖浏览器策略、网关/CDN 和所有部署环境，不能用宽泛通配策略掩盖边界设计。