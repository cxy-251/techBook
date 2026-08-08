第140章：Schema, Migration, Data Evolution, and Application Compatibility
=========================================================================

核心知识点
----------

* Database schema 是长期 application contract，定义字段、类型、nullability、default、relation、index、constraint 与可查询结构；其寿命通常长于某次应用发布。
* Schema change 会同时改变 database structure 与 runtime assumption。旧 server、新 server、旧 browser bundle、background job、cache 和 API 可能在一段时间内同时运行。
* Migration 工具只保证“哪些变更按什么顺序执行”，不能自动证明应用、API、缓存和历史数据已经兼容。
* Rolling deployment、serverless、edge 与灰度发布要求 schema evolution 尽量 backward compatible；不能假设所有实例和客户端同时升级。
* 安全演化常使用 ``Expand → Migrate → Contract``：先新增兼容结构，再让新旧代码并存并迁移数据，最后删除旧字段和旧路径。
* 新增字段不代表历史数据已经满足新契约。Default 通常只影响未来写入，历史记录需要 backfill 或兼容读取策略。
* Backfill 是 schema evolution 的一部分。大表迁移应分批、幂等、可恢复，并观察 lock、CPU、I/O、replication lag 与剩余数据覆盖率。
* 破坏性变更应拆成可回滚步骤。典型策略包括 dual write、fallback read、shadow read、compatibility field 与延迟删除。
* Constraint 是持久化边界上的业务不变量保护，包括 unique、foreign key、not null、check 等；应用层 validation 与数据库 constraint 应互相补强。
* Schema drift 会向外扩散到 ORM model、API response、client type、static output、cache 和 UI；“数据库迁移成功”不等于“系统迁移完成”。
* 不可无损迁移的数据不能用猜测伪造事实，例如无法可靠从历史 display name 拆分 given/family name 时，应保留无损字段并允许后续可信补充。

关键路径
--------

在线 Schema 演化：

::

   add compatible structure
   → deploy code that reads old + new
   → dual-write or compatibility-write
   → backfill historical data in batches
   → verify coverage + errors + performance
   → move reads to new structure
   → stop old writes
   → remove old API/cache dependencies
   → contract old schema

发布兼容检查：

::

   oldest still-running code
   + newest code
   + mixed historical data
   + cached old payloads
   → find common contract
   → preserve rollback path

概念辨析
--------

* **Schema 与 ORM Model**：schema 是数据库持久契约，ORM model 是应用侧映射；二者可短期不同但必须有兼容策略。
* **Migration 与 Backfill**：migration 改结构或规则，backfill 把历史数据迁入新结构。
* **Backward Compatible 与 Permanent Compatibility**：兼容阶段是迁移桥梁，不代表旧字段永远保留。
* **Default 与 Historical Data**：设置默认值通常保护未来写入，不会自动赋值给所有已有记录。
* **Expand/Contract 与 Big-Bang Migration**：前者允许新旧版本共存与回滚，后者要求一次性切换，线上风险更高。

本章结论
--------

Schema evolution 应按 ``Expand → Coexist → Backfill → Verify → Cut Over → Contract`` 设计。数据库结构、运行代码、API、缓存和历史数据必须作为一个兼容系统共同演化；安全迁移的核心不是 SQL 能否执行，而是新旧世界能否在发布窗口内同时正确运行并可回滚。
