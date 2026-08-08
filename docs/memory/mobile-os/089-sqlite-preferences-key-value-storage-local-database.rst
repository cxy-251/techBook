第089章：SQLite, Preferences, Key-Value Storage, Local Database
==============================================================

核心知识点
----------

* 本地数据层要先按语义分类：轻量配置、结构化业务对象、派生索引、大文件缓存、同步状态和密钥材料应进入不同存储通道。
* Preferences / UserDefaults / DataStore 适合少量键值配置、用户选项、feature flag 和轻量迁移标记，不适合复杂关系、排序、查询和多对象事务。
* SQLite 是移动端结构化本地数据的基础：表、索引、page、transaction、lock、journal/WAL 和 crash recovery 共同定义持久化语义。
* Room、Core Data、SwiftData 等上层框架提供对象模型、查询、迁移和生命周期封装，但底层仍受事务、I/O、锁与文件生命周期约束。
* WAL 让 reader 与 writer 更容易并发，写入先追加到 WAL，再由 checkpoint 合并回主库；移动端仍只有受控 writer，并需关注 WAL 增长和 checkpoint 成本。
* 业务事实与同步状态应尽量在同一事务提交，避免“对象更新成功但同步标记失败”这类跨层不一致。
* 敏感 token、密钥与认证材料不应只依赖数据库或偏好文件；应交给 Keychain / Keystore，并让数据库只保存引用、密文或包裹后的材料。
* 本地数据库属于 App container 的文件系统事实，备份、恢复、schema migration、云同步和隐私删除都会影响其生命周期。

关键路径
--------

::

   User action
     → App data layer
     → classify data
       → Preferences/UserDefaults for small config
       → SQLite/Room/Core Data/SwiftData for structured state
       → Files for large cache/blob
       → Keychain/Keystore for secrets
     → App container filesystem
     → backup / migration / sync policy

数据库写入：

::

   Repository
     → transaction begin
     → update business tables
     → update sync/version state
     → WAL/journal
     → fsync / commit boundary
     → transaction visible

概念辨析
--------

* **Preferences vs database**：前者适合独立小键值；后者适合结构化查询、索引、关系和事务一致性。
* **Database file vs database engine**：文件只是持久化载体；事务、锁、查询计划和 crash recovery 由数据库引擎实现。
* **Rollback journal vs WAL**：前者以回滚日志保护事务；后者把新写入追加到 WAL 并在之后 checkpoint，读写并发特性不同。
* **ORM/object store vs SQLite**：上层框架改善模型表达，不会消除底层 I/O、索引和事务成本。
* **Encryption vs key protection**：数据库加密保护文件内容；真正的密钥生命周期仍应交给平台密钥系统与用户认证边界。

本章结论
--------

移动端本地存储不是“选一个数据库”问题，而是把不同语义的数据放进匹配的生命周期和一致性机制。轻量配置用键值层，业务事实用事务数据库，大对象用文件，密钥用系统安全存储，再统一考虑备份、迁移和同步。