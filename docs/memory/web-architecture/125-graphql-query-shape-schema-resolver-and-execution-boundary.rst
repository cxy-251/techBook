GraphQL Query Shape, Schema, Resolver, and Execution Boundary
=============================================================

核心知识点
----------

* GraphQL 把 API contract 的中心从 URL/method 转移到 schema、operation、selection set、resolver 和 execution result；单一 ``/graphql`` endpoint 不代表后端执行路径只有一条。
* schema 定义可公开能力：root operation、type、field、argument、nullability、deprecation 与 directive；客户端只能在 schema 允许范围内决定单次 response shape。
* selection set 可以降低固定 endpoint 的 overfetch/underfetch，但会把执行成本隐藏在字段树中；服务端必须限制深度、列表规模、query complexity、timeout 与可调用 operation。
* resolver 把字段选择转换成真实后端访问；context 承载 session、tenant、logger、database client、loader 等 request-scoped 状态，也是字段级权限的重要入口。
* N+1 与 resolver waterfall 是 execution problem。DataLoader/request-scoped batching、预取、聚合查询与 query planning 用于减少重复后端访问，不能只看 GraphQL HTTP 请求数量。
* GraphQL 允许部分 ``data`` 与 ``errors`` 共存；null propagation、error path 与业务错误 envelope 必须让客户端能区分局部失败、权限失败和整体失败。
* normalized cache 的实体身份通常依赖 ``typename + id`` 或等价 key；schema 字段、mutation result 与 cache identity 必须能支持写后 reconciliation。

关键路径
--------

``Browser Operation → Parse/Validate Against Schema → Root Resolver → Nested Resolvers → Auth/Loader/Backend → Execution Result(data/errors) → Client Normalized Cache → UI``。

性能分析时把 selection tree 还原成 backend call graph：``field → resolver → service/db/cache``。若一个列表中的 N 个节点触发 N 次相同类型 lookup，应在 request scope 内批处理或改写读取边界。

权限分析不能停在 root field。任何敏感 field 都要保证无论从哪个父对象或 operation 进入，都遵守相同授权与字段裁剪规则。

概念辨析
--------

* **一个 GraphQL request vs 一次 backend query**：前者只有一个 HTTP 请求；后者可能展开成许多数据库或服务调用。
* **schema type vs database model**：schema 是公共 contract；数据库模型是内部持久化结构，两者不应直接绑定。
* **nullable field vs error**：null 可能表示业务缺失、权限裁剪或 resolver failure；contract 必须明确客户端如何解释。
* **client-specified shape vs unlimited query**：客户端可选择字段，不等于服务端应允许无限深度和无限 fan-out。

本章结论
--------

GraphQL 的核心是“schema 定义能力，client 定义本次投影，resolver 执行真实系统路径”。设计与排障必须同时检查 schema contract、resolver call graph、权限、批处理、错误传播和缓存身份。