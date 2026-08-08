第199章：Choosing Data Access, Mutation, Transaction, and Consistency Strategies
================================================================================

核心知识点
----------

* 数据策略从 source of truth 开始。订单、支付、库存、文件、搜索索引、客户端缓存可能由不同系统拥有，冲突时必须知道相信谁。
* ORM、query builder、raw SQL 应匹配 query complexity，而不是形成宗教式单选。简单 CRUD、动态过滤、复杂 join/报表/锁语义适合不同抽象层。
* Type-safe data API 不能替代 database constraint、runtime validation、query plan 和实际事务语义。
* Transaction strategy 要匹配业务原子性。先写出业务不变量，再决定哪些写入必须同事务提交、哪些只能最终一致或补偿。
* 单数据库事务无法覆盖 payment provider、object storage、queue 等外部系统；跨系统一致性通常需要 state machine、outbox、reconciliation 或 compensation。
* Isolation level、unique constraint、row lock、optimistic version、serialization retry 都是表达并发不变量的工具，选择取决于具体写入冲突。
* Mutation 必须设计 duplicate、retry 和 partial failure。浏览器双击、网关重试、serverless timeout、worker replay 都可能让同一用户意图重复到达。
* Idempotency key 用来识别同一用户意图，重要交易写入应让相同 key 返回同一逻辑结果，而不是重复创建事实。
* “已保存”“处理中”“同步中”是不同 consistency promise。UI 文案必须与后端真正保证的持久化和恢复语义一致。
* File/large asset path 应独立设计：二进制放 object storage，数据库保存 metadata/ownership/version；上传、转码、清理和 CDN 分发拥有自己的生命周期。
* Runtime topology 会改变 data access。Node、serverless、edge、queue、replica、global database 会影响连接、延迟、事务和一致性。
* 数据架构最终用 failure recovery 衡量：超时、冲突、重复写、迁移失败、权限变化、第三方状态分叉时能否恢复到唯一可解释事实。

关键路径
--------

交易写入：

::

   user intent + idempotency key
   → validation + auth
   → read authoritative state
   → local database transaction
   → commit durable local facts
   → call/observe external system
   → state machine / outbox / reconciliation
   → invalidate read models/cache
   → UI reflects confirmed consistency state

数据访问选择：

::

   query/business invariant
   → choose ORM/query builder/raw SQL
   → inspect generated SQL
   → inspect indexes/locks/isolation
   → test concurrency and retry
   → observe production query/transaction evidence

概念辨析
--------

* **Source of Truth 与 Read Model**：前者决定最终事实，后者是为读取优化的可重建副本。
* **Database Transaction 与 Distributed Transaction**：普通事务只覆盖其数据库边界，外部服务需要额外协调协议。
* **Idempotency 与 Deduplication**：幂等关注同一意图重复执行仍得到稳定结果，去重只是其中一种实现。
* **Strong Consistency 与 User Promise**：一致性不是越强越好，应匹配产品对“已完成”的承诺和失败成本。
* **ORM Abstraction 与 Database Reality**：ORM 提供开发抽象，索引、锁、隔离和执行计划仍由数据库决定。

本章结论
--------

数据架构应按 ``Authority → Query Boundary → Business Atomicity → Mutation Idempotency → Cross-System Consistency → Recovery`` 设计。工具选择必须服务事实所有权和失败恢复；只有在重复、超时、并发和部分失败下仍能收敛，数据路径才真正可靠。