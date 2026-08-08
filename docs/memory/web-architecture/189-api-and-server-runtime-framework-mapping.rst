第189章：API and Server Runtime Framework Mapping
=================================================

核心知识点
----------

* Server framework 的核心作用是把 HTTP ``method / URL / headers / cookies / body / connection context`` 映射成 middleware、handler、serializer、stream 和 error boundary。
* 比较 server framework 时，第一步先定位 runtime adapter：Node、serverless、edge、Bun、Deno、Workers 等底层环境会改变 request/response、streaming、env 与生命周期能力。
* Express 以 middleware chain 为核心。注册顺序就是语义，body parser、request id、session/auth、router 与 error middleware 的前后关系会直接改变请求结果。
* Express 的灵活性意味着 ``req/res`` 可被多层修改；排查时必须从入口按 middleware 顺序还原上下文字段、header 与提前结束响应的位置。
* Fastify 更强调 route schema、hook、plugin encapsulation、serialization 与 logger，使输入、输出和插件作用域更早成为显式 contract。
* Fastify plugin tree 决定 hook、decorator 与 schema 对哪些 route 可见，适合按业务域隔离 server capability，但调试必须知道 route 所属 encapsulation context。
* Hono 等 Web Standard 风格框架更接近 ``Request / Response``，更容易映射到多种 runtime；可移植性仍受 runtime 的 Node API、filesystem、socket 与 connection 能力约束。
* Full-stack framework 的 route handler 把 API endpoint 放到应用路由附近，但仍承担普通 server duty：auth、schema、status/header、stream、logs、cache 与错误语义。
* Server function/server action 可以隐藏 HTTP endpoint 形状，却不能消除网络、serialization、retry、idempotency、authorization 与 cache invalidation。
* Streaming response 一旦发送 headers，后续错误通常无法重新改写 status/body；前置校验、abort、日志和客户端恢复必须在设计中明确。
* Body size、parser、schema failure、auth failure、domain error、database timeout、stream abort 应在不同阶段形成可解释 status/error code。
* 一个安全的 server abstraction 必须保留可观测性：route、request id、trace id、runtime、status、duration、error phase 与 release 应可追踪。

关键路径
--------

Server request：

::

   HTTP request
   → runtime adapter
   → body/parser + request context
   → middleware/hooks
   → auth + validation
   → route handler
   → service/data boundary
   → serialization/stream
   → HTTP response

失败路径：

::

   malformed/body too large
   → parser/schema error
   → auth/permission error
   → domain/database error
   → response/stream error
   → framework error boundary + logs

概念辨析
--------

* **Runtime 与 Framework**：runtime 提供执行和网络能力，framework 组织请求处理；同一 framework 可落在不同 runtime。
* **Middleware 与 Business Logic**：middleware 适合横切请求能力，领域规则仍应放在可信 service/use-case 边界。
* **Schema Validation 与 Authorization**：schema 证明输入形状有效，authorization 判断主体是否能对目标资源执行操作。
* **Route Handler 与 Server Function**：前者显式暴露协议 endpoint，后者可以隐藏调用外形，但底层 server 责任相同。
* **Response Error 与 Stream Error**：headers 发送前可返回结构化 HTTP error；stream 开始后更多依赖中断、日志和客户端恢复。

本章结论
--------

Server framework 应按 ``Runtime Adapter → Middleware/Hook → Validation/Auth → Handler → Data/Service → Response/Stream → Error`` 映射。API 写法是否简洁是次要问题，真正重要的是请求各阶段的顺序、权限、失败语义和可观察性是否清楚。