第162章：JavaScript Server Runtime Node.js, Bun, Deno, and Host Capability
=========================================================================

核心知识点
----------

* Server runtime 把 ECMAScript 语言能力连接到浏览器之外的 host environment，使 JavaScript 能处理 HTTP、读取环境变量、访问数据库、文件系统和内部网络。
* Runtime capability 决定代码真正能做什么。``fs / TCP / DNS / TLS / crypto / process / env / native addon / stream / worker / Web API`` 都属于宿主能力，而非 JavaScript 语言本身。
* Node.js、Bun、Deno、edge worker、serverless function 即使都运行 JavaScript，也拥有不同的 API、权限、生命周期、模块兼容性和资源限制。
* 同一段源码能通过语法检查，不代表能跨 runtime 直接运行；``process.env``、``node:fs``、native addon、长 TCP 连接和进程级状态都可能成为迁移断点。
* Server runtime 通常处于 trusted execution boundary，可访问 session secret、database URL、private token 和内部服务，但必须把这些能力隔离在不可公开的产物与日志之外。
* Browser 负责用户意图和公开请求；server runtime 负责可信身份验证、授权、数据访问、业务判断和 response generation。
* 长生命周期 server process 可以复用 connection pool、module cache 和 in-memory object，同时也必须处理 memory leak、stale connection、crash 和 rolling deployment。
* Serverless/edge 的实例生命周期更弱，不能把“进程内对象存在”当成 durable state；跨请求状态应放到数据库、cache、KV、queue 等外部边界。
* Framework 的 route handler、loader、server action、middleware 能做什么，最终取决于它被构建到哪个 runtime target。
* Runtime 选型应从所需 host capability 反推，而不是从框架名字反推。

关键路径
--------

服务端请求：

::

   browser request
   → HTTP/runtime entry
   → request handler
   → secret/session verification
   → database/internal service
   → application logic
   → response/stream
   → browser

Runtime 兼容检查：

::

   source module
   → list required host capabilities
   → target runtime
   → verify API/permission/lifecycle support
   → verify dependency/native-module support
   → verify timeout/state/stream behavior

概念辨析
--------

* **ECMAScript 与 Host API**：前者定义语言语义，后者定义文件、网络、进程、环境变量等外部能力。
* **Server Runtime 与 Server Framework**：runtime 提供执行环境，framework 封装 request/route/middleware 等开发模型。
* **Trusted Runtime 与 Trusted Input**：server 环境更可信，不代表客户端输入可信；输入仍需验证和授权。
* **Process State 与 Durable State**：进程内状态可丢失，数据库/存储才承担持久事实。
* **Runtime Compatibility 与 Syntax Compatibility**：语法可执行不代表依赖的宿主能力存在。

本章结论
--------

服务端 JavaScript 应按 ``Language → Host Capability → Runtime Lifecycle → Trust Boundary → External State`` 阅读。真正决定架构的不是“都用 JavaScript”，而是代码最终在哪个 runtime 执行、能调用哪些宿主资源，以及这些资源失败后由谁恢复。