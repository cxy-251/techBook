第190章：Data Layer Tooling and Query Boundary Mapping
======================================================

核心知识点
----------

* 数据层工具的目标是把应用意图转换成可验证、可执行、可迁移、可观察的 database operation；工具名不能替代对 query、transaction、constraint 和 migration 的理解。
* 一条稳定写入路径应为 ``unknown request → runtime validation → auth/tenant → query construction → transaction → database constraint → error mapping → cache invalidation``。
* TypeScript type 只保护编译期代码，HTTP body、third-party payload 和数据库旧数据仍需要 runtime schema 验证。
* Database constraint 是最后的数据完整性边界。Unique、foreign key、not null、check、transaction isolation 不能因为 ORM 类型存在就删除。
* Prisma 更强调 schema-centered client generation，把 data model、generated client、migration 与常规 CRUD 查询集中到一个模型入口。
* Prisma 的类型安全边界不覆盖业务权限、运行时输入和真实 SQL 成本；复杂查询、索引、连接池与 transaction 仍必须观察数据库事实。
* Drizzle 更接近 SQL-like type-safe query construction，让表、字段、join、where 与返回列在 TypeScript 中更显式，便于把代码映射回真实 SQL。
* Traditional ORM、query builder、raw SQL 的抽象层不同。ORM 提供关系与对象映射，query builder 组织 SQL 结构，raw SQL 提供最直接控制；没有一种方式自动拥有最佳性能。
* ORM abstraction 必须用真实 SQL、query plan、index、rows scanned、N+1、connection pool 与 transaction metrics 验证。
* Validation tool 如 Zod、Valibot、JSON Schema、OpenAPI schema 位于 trust boundary；它们和 ORM/schema 解决的是不同问题。
* Migration 是 data contract 演化路径。新增/删除/改名字段、backfill、index、constraint 与代码版本必须按兼容窗口排序。
* Serverless/edge 会改变连接生命周期和驱动兼容性；数据工具选择必须同时考虑 runtime topology，而不是只比较 query API。

关键路径
--------

应用写入：

::

   HTTP/form input
   → runtime schema validation
   → permission/tenant check
   → ORM/query builder/raw SQL
   → transaction
   → database constraints
   → commit/error mapping
   → cache invalidation
   → response

数据工具评估：

::

   schema model
   → generated/typesafe query API
   → inspect emitted SQL
   → inspect index/query plan
   → inspect transaction semantics
   → inspect migration history
   → inspect runtime connection behavior

概念辨析
--------

* **Static Type 与 Runtime Validation**：静态类型约束源码，runtime validation 约束实际进入系统的数据。
* **ORM Schema 与 Database Schema**：ORM 模型是应用表达，真正持久约束最终由数据库 schema 决定。
* **ORM 与 Query Builder**：ORM 提供更高层对象/关系抽象，query builder 更直接表达 SQL 结构；边界和成本不同。
* **Raw SQL 与 Unsafe SQL**：直接写 SQL 不等于不安全，关键是参数绑定、权限、事务和可观测性是否正确。
* **Migration 与 Deployment**：migration 改变持久 contract，应用发布必须与旧/新 schema 的兼容窗口协同。

本章结论
--------

数据层应按 ``Trust Boundary → Query Shape → Transaction → Database Constraint → Migration → Runtime Topology`` 设计。好的工具不是隐藏数据库，而是让 schema、SQL、事务、验证、迁移和连接成本都更容易被看见和控制。