第005章：How Frameworks Package System Boundaries
==================================================

核心知识点
----------

* Framework 的本质是对 Web 系统边界的包装。组件、route、loader、action、middleware、schema、ORM、bundle、edge function 都是在重命名或组合已有运行时责任。
* UI Framework 主要封装 browser 内的 component、state、event 与 DOM update。它负责交互组织，不拥有数据库里的最终业务事实。
* UI state 应先判断是否只属于当前 document；若状态影响分享 URL、权限、库存、订单或跨设备一致性，就必须继续映射到 URL、server、database 或 cache。
* Full-stack Framework 封装 routing、server rendering、data loading、mutation、streaming、hydration、cache 与 error boundary，但代码仍会被拆到 browser/server/edge/build 等不同 runtime。
* Full-stack route 中的读路径和写路径责任不同：读路径可能缓存和预取；写路径必须处理 auth、validation、idempotency、transaction、cache invalidation 与失败恢复。
* Hydration 是 server output 与 browser runtime 的交接边界。两端初始状态、时间、locale 或数据快照不一致时，会产生 mismatch 与 UI 跳变。
* Server Framework 封装 request parsing、middleware、routing、response 与 error handling。Middleware 顺序实际构成 request context 的建立路径。
* API/RPC 工具封装 client-server contract，包括 schema、serialization、error shape、versioning 与 auth entry；contract 清晰不能替代 server-side authorization。
* ORM、query builder、database client、migration 与 query cache 分别包装 persistence、query、schema evolution 与 data-copy 边界；抽象不能取消事务和一致性问题。
* Build Tool 把源码 module graph 转换为 client/server/edge bundle、chunk、asset manifest、source map 等 artifact；代码是否进入 client bundle 本身就是安全边界。
* Hosting Platform 把 runtime、region、edge、cache、env、logs、release 与 rollback 打包成部署模型。框架代码相同，部署平台不同，真实能力和失败形态也会变化。
* 比较框架时应比较 boundary ownership、runtime capability、cache semantics、observability、escape hatch 与 failure recovery，而不是只比较 API 语法。

关键路径
--------

Framework 还原路径：

::

   framework feature
   → identify generated runtime
   → browser / server / edge / build?
   → identify request and state owner
   → identify serialization/cache boundary
   → identify failure/error boundary
   → map to underlying Web platform behavior

典型 full-stack mutation：

::

   browser event
   → framework action / API contract
   → server middleware + auth
   → domain logic
   → database transaction
   → response / redirect
   → cache invalidation / revalidation
   → browser state reconciliation

概念辨析
--------

* **Framework 与 Runtime**：framework 是开发抽象，runtime 才决定代码能否访问 DOM、filesystem、TCP、secret 或数据库。
* **UI State 与 Server State**：UI state 服务当前交互，server/database state 服务可信业务事实；query cache 只是服务端事实的客户端副本。
* **Loader 与 Mutation**：loader/read path 主要读取和组织数据，mutation/write path 会改变权威状态，需要更强的事务与恢复设计。
* **ORM 与 Database**：ORM 改善映射和类型体验，database 仍然拥有 transaction、constraint、index 与 concurrency semantics。
* **Hosting Platform 与 Framework**：hosting platform 决定实际 runtime、region、cache 和运维能力，framework 只能在这些能力上运行。

本章结论
--------

阅读任何 Web Framework，都应执行 ``Framework Term → Runtime → Boundary → State → Cache → Failure`` 的还原。真正成熟的抽象不是把边界彻底隐藏，而是让默认路径简单，同时保留清晰的可观察性、错误语义和必要的 escape hatch。