第139章：SQL, NoSQL, ORM, Query Builder, and Type-Safe Data Access
==================================================================

核心知识点
----------

* SQL 与 NoSQL 首先代表不同数据建模假设。SQL 强调 relation、constraint、transaction 与组合查询；NoSQL 可能强调 document、key-value、column、graph 或特定访问模式。
* 选存储模型应先写出业务写路径、读 shape、一致性承诺和扩展方式，再选择 SQL/NoSQL；“哪个更现代”不是有效架构依据。
* ORM 把 application object/model 映射到 table、column、relation 和 query，降低 CRUD 与映射成本，但不会消除 join、N+1、transaction、lock、index 与 query-plan 成本。
* ORM 调用必须还原成真实数据库动作：访问哪些表、产生几条查询、加载哪些 relation、是否进入同一 transaction、是否使用正确 index。
* Query builder 更接近 SQL shape，适合复杂 join、aggregation、report、window、conditional query 与明确字段投影，同时可保留参数化和类型检查。
* Raw SQL 提供最大表达力，也要求调用方自己管理 parameter binding、result mapping、schema drift 与数据库特定语义。
* Type-safe data access 可减少 column 名、parameter 与 result shape 的编译期漂移，但编译通过不能证明 runtime row、migration、permission、transaction 或 query performance 正确。
* Data layer 的稳定职责是连接 domain meaning 与 storage reality。上游暴露业务意图，下游明确 query、transaction、constraint、pagination、freshness 与错误映射。
* Repository/data access abstraction 不应把成本完全隐藏。事务需求、主库/副本新鲜度、锁、分页、批量加载和潜在大查询应在接口或命名中可见。
* 简单 CRUD、复杂报表、多表事务、全文搜索、多租户过滤与实时读取对访问工具要求不同，同一项目可在不同路径使用不同抽象层。

关键路径
--------

数据访问还原：

::

   use case / domain command
   → repository or data-layer method
   → ORM / query builder / raw query
   → real database statements
   → index / constraint / transaction / lock
   → row/document result or database error
   → map to domain result

工具选择：

::

   access pattern + consistency + query complexity
   → choose storage model
   → choose access abstraction
   → preserve transaction and cost visibility
   → measure generated query and plan

概念辨析
--------

* **SQL 与 NoSQL**：是数据模型与访问假设的差异，不是“传统 vs 新式”的简单替代关系。
* **ORM 与 Database**：ORM 是映射层，database 仍拥有约束、事务、索引和执行计划。
* **Query Builder 与 ORM**：query builder 通常更显式表达 query shape；ORM 更偏向对象/关系映射和模型操作。
* **Type Safety 与 Runtime Correctness**：类型安全减少接口漂移，不能替代 runtime validation、database constraint 和权限校验。
* **Repository 与 CRUD Wrapper**：repository 应表达用例数据需求与一致性边界，而不是把所有表操作包装成通用 CRUD。

本章结论
--------

数据访问层应按 ``Domain Intent → Query Shape → Database Reality → Domain Result`` 设计。ORM、query builder 和类型系统是表达工具；真正稳定的架构必须让事务、索引、约束、查询成本与权限边界始终可观察、可测试、可优化。
