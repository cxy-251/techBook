第145章：Serverless Database, Edge Data, and Connection Lifecycle Constraints
=============================================================================

核心知识点
----------

* 现代数据访问必须按 runtime topology 分析：browser、CDN/edge、serverless function、connection proxy、primary database、replica、KV/cache 与 queue 的空间位置和生命周期共同决定真实路径。
* Serverless 改变传统“少量长驻 server + 长生命周期 connection pool”的假设。突发流量会扩出大量实例，若每个实例都建立大 pool，会形成 connection storm。
* 连接预算应从 database 上限反推。核心关系是 ``并发实例数 × 每实例连接上限``，再预留后台任务、管理连接和故障空间。
* 进程内 pool 只能在同一热实例中复用，不能自动合并不同 serverless instance 的连接。高并发场景常需要 database proxy、external pool、HTTP data API 或 serverless driver。
* Edge runtime 靠近用户不代表数据也靠近用户。总延迟取决于 ``browser → edge → data region → edge → browser``；远端主库可能抵消 edge 的网络优势。
* 读路径和写路径应分开设计。可接受稍旧数据的读取可以使用 replica、regional cache、global KV；需要事务顺序的写入必须回到 primary/write owner 或等价一致性边界。
* Edge-compatible data access 往往使用 HTTP database、global KV、distributed cache、regional replica、queue 或 region-aware routing，而不是假设所有 edge runtime 都适合直接维护传统 TCP database session。
* Connection proxy/pool 可能改变 session semantics。Transaction pooling 等模式可能限制 session-level state、temporary table、LISTEN/NOTIFY、advisory lock 等能力，不能视为透明层。
* Replication lag 会产生 stale read 与 read-after-write inconsistency。刚写入成功后立即从 replica 读取，可能看到旧值，因此关键流程需主库读、session stickiness、version check 或明确 UX。
* Data location 是 deployment 与 compliance boundary。Region、cross-border replication、edge cache、backup 与 log retention 会同时影响 latency、privacy、合规和 disaster recovery。
* Background job 与批处理也需要独立 pool、concurrency limit 和短 transaction，避免和用户请求争抢连接。
* “Serverless database”不是自动架构答案；真正需要设计的是 execution lifecycle、connection ownership、data distance、consistency、failure 和 compliance。

关键路径
--------

全球读取与写入：

::

   browser
   → CDN / edge entry
   → lightweight routing / auth context
   → serverless API
   → database proxy / pool
   → read path: replica/cache when freshness allows
   → write path: primary / authoritative writer
   → commit
   → replicate / invalidate / enqueue
   → response + version/freshness semantics

连接预算：

::

   platform max concurrency
   × connections per instance
   + workers / admin reserve
   → compare with database connection capacity
   → place proxy/pool and concurrency limits

概念辨析
--------

* **Edge Compute 与 Edge Data**：代码靠近用户不代表权威数据也在边缘；两者距离必须分别计算。
* **Primary 与 Replica**：primary 拥有写入顺序，replica 提供派生读取能力并可能存在复制延迟。
* **Process Pool 与 External Proxy**：进程池只复用本实例连接，外部代理可跨多个实例复用数据库连接资源。
* **Low Latency 与 Strong Consistency**：更近的副本降低读延迟，但可能牺牲新鲜度；关键写后读需明确一致性路径。
* **Serverless Runtime 与 Stateless Business Logic**：函数实例可短生命周期，不代表数据库状态、session、transaction 和 connection lifecycle 不需要显式设计。

本章结论
--------

现代数据部署应按 ``Runtime Lifecycle → Connection Ownership → Data Location → Read Freshness → Write Authority → Replication/Cache → Compliance`` 设计。Serverless 与 edge 的价值只有在连接池、数据距离和一致性一起匹配时才能成立；否则只是把延迟与资源瓶颈从 server 移到了数据库网络边界。
