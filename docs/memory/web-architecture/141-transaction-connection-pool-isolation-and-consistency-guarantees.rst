第141章：Transaction, Connection Pool, Isolation, and Consistency Guarantees
============================================================================

核心知识点
----------

* Transaction 把多个数据库读写组织成一个 consistency boundary，使一组必须共同成立的状态要么整体 commit，要么整体 rollback。
* Transaction 边界应由业务不变量决定，而不是由函数长度决定。订单、订单项、库存预留、付款尝试等若共同支撑一个用户可见承诺，就应考虑进入同一数据库事务。
* ACID 分别保护不同失败维度：Atomicity 防部分成功；Consistency 保护约束与不变量；Isolation 控制并发可见性；Durability 保证提交后可恢复。
* Isolation level 决定 concurrent transaction 可以观察什么。隔离越强，通常冲突、等待、serialization failure 和重试成本越高。
* 并发正确性不能只靠“先 select 再判断再 update”。条件更新、unique constraint、version column、显式锁或 serialization retry 常用于缩小 race window。
* Connection pool 是共享 runtime resource。Web server、serverless function、background worker、ORM 和 edge adapter 都可能争用有限数据库连接。
* 总连接量应按 ``实例数 × 每实例池上限`` 与 database max connection 一起设计；扩容只增加应用实例而不约束 pool，容易形成 connection storm。
* Long transaction 会延长 lock、connection、snapshot 与用户等待时间，增加 deadlock、timeout 和 contention 风险。外部 API、邮件、慢网络调用通常不应放进数据库事务。
* 数据库 transaction 只能原子覆盖数据库内部资源。支付、对象存储、queue、email、cache 等外部副作用需要 idempotency、outbox/event、compensation 与最终一致性设计。
* Consistency guarantee 应与用户可见承诺一致。余额、库存、权限等可能要求立即一致；搜索索引、分析、邮件与部分 cache 可以最终一致，但 UI 必须表达处理中或延迟。
* Serialization/deadlock retry 应只重试可安全重复的事务，并设置有限次数、jitter/退避与稳定业务错误；无界重试会放大负载。

关键路径
--------

数据库事务：

::

   trusted use case
   → acquire pooled connection
   → BEGIN
   → read/lock/validate current facts
   → perform constrained writes
   → database constraints + isolation
   → COMMIT or ROLLBACK
   → release connection immediately
   → trigger post-commit side effects

跨系统一致性：

::

   database commit
   → durable local state
   → outbox / queue / idempotent external call
   → payment / email / cache / index
   → retry or compensate on partial failure
   → expose confirmed / pending / failed state to UI

概念辨析
--------

* **Atomicity 与 Distributed Consistency**：数据库原子性只覆盖其 transaction 内部，不能自动回滚已经发生的外部网络副作用。
* **Isolation 与 Lock**：isolation 定义可见性和冲突语义，lock 是实现这些语义的机制之一。
* **Connection Pool 与 Database Connection**：pool 复用和限制连接，不会提升数据库本身能承受的 transaction throughput。
* **Strong Consistency 与 Everywhere Serializable**：强一致性应用于需要的业务承诺，不代表所有读取都必须使用最高隔离级别。
* **Retry 与 Idempotency**：retry 重新执行失败动作，idempotency 保证重复执行不会产生额外业务结果；二者需要配合。

本章结论
--------

一致性设计应按 ``Business Invariant → Transaction Boundary → Isolation/Concurrency Control → Connection Lifetime → Post-Commit Side Effects → User-Visible State`` 阅读。数据库事务解决局部原子性；现代 Web 的系统级可靠性还必须把连接资源、并发冲突、外部副作用和恢复策略一起设计。
