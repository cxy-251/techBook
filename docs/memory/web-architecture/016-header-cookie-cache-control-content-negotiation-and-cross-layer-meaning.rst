Header, Cookie, Cache-Control, Content Negotiation, and Cross-Layer Meaning
===========================================================================

核心知识点
----------

* HTTP headers 是 browser、CDN、proxy、server、cache 和 security policy 共同读取的控制平面；body 主要承载 representation 或 mutation payload。
* ``Content-Type`` 决定内容如何解释，``Content-Encoding`` 说明传输编码，``Cache-Control`` 与 validator 决定副本复用，``Vary`` 决定缓存变体维度。
* Cookie 是 request-bound state：浏览器保存它，并按 domain、path、Secure、SameSite 等规则自动附加到后续请求；服务器拥有 session 的真实业务含义。
* ``HttpOnly`` 限制脚本读取 cookie，``Secure`` 限制安全传输，``SameSite`` 影响跨站请求是否自动携带 cookie；这些属性属于浏览器强制的安全边界。
* HTTP cache 是分布式副本系统。``max-age``、``no-cache``、``no-store``、``ETag``、``Last-Modified`` 等决定副本新鲜度与重新验证路径。
* ``no-cache`` 表示可存储但使用前必须验证；``no-store`` 才是要求不要存储。二者语义不同。
* Content negotiation 通过 ``Accept``、``Accept-Language``、``Accept-Encoding`` 等请求信息选择 representation；若响应因此变化，缓存键必须与 ``Vary`` 或平台规则保持一致。
* 个性化响应与 shared cache 的边界必须明确，否则 cookie、locale、authorization 等状态可能造成缓存污染或用户数据泄漏。

关键路径
--------

Header 控制路径：

``Browser Request Headers → Proxy/CDN → Cache Decision → Server Representation/Policy → Response Headers → Browser Parse/Cache/Cookie/Security State``

Session cookie：

``Login Mutation → Server creates session → Set-Cookie → Browser cookie jar → later request auto-attaches Cookie → Server restores/validates identity``

缓存验证：

``cached representation + ETag → request If-None-Match → server compares current version → 304 reuse or 200 replacement``

内容协商：

``Accept* request headers → server/CDN chooses representation → Vary records selection dimensions → cache stores correct variant``

概念辨析
--------

* **Header vs Body**：header 主要控制如何解释、缓存、授权和传输；body 主要携带内容本身。
* **Cookie vs Local Storage**：cookie 会自动进入匹配请求；localStorage 等需要脚本主动读取，不天然属于 HTTP request context。
* **Cookie vs Session**：cookie 常只保存 session 标识；真正的用户身份、权限和会话状态应由服务器验证和拥有。
* **no-cache vs no-store**：前者允许存储但要求验证；后者要求不保存副本。
* **ETag vs Cache-Control**：Cache-Control 决定新鲜度和复用策略；ETag 提供 representation 版本验证依据。
* **Content-Type vs Content-Encoding**：前者说明内容是什么，后者说明传输前如何编码。
* **Vary vs 任意缓存键**：Vary 告诉通用 HTTP cache 哪些请求 header 会改变响应表示；平台 CDN 还可能有额外 cache-key 规则。

本章结论
--------

Headers 决定 HTTP 交互如何跨层被解释。Cookie、cache、content negotiation 和安全策略都依赖这些控制字段。设计响应时必须同时考虑身份状态、缓存副本、representation 变体和浏览器强制行为，否则一个看似正确的 body 仍可能在其他用户、语言、缓存或安全上下文中产生错误结果。