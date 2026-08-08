第183章：Realtime Collaboration, Presence, CRDT, OT, and Conflict Resolution
=============================================================================

核心知识点
----------

* Realtime collaboration 的本质是多个副本在并发编辑、网络延迟和离线条件下共同维护同一份共享状态。
* 协作状态至少分成 durable document data、collaboration metadata、ephemeral presence、sync/control state；它们生命周期和存储要求不同。
* Presence 如 cursor、selection、typing、online status 只属于当前会话，适合内存/Redis/房间 TTL；文档正文、评论、版本与权限需要可靠持久化。
* 本地编辑通常先乐观应用，再产生 operation/update、进入 pending queue、发送到协作后端；低延迟体验依赖 local-first application。
* 服务器或协议层需要处理权限、排序、去重、ACK、版本/因果上下文、广播与持久化，不能只做 WebSocket 转发器。
* OT 通过根据并发操作转换当前操作来保持收敛和意图；CRDT 通过可合并的数据/更新规则让副本在不同到达顺序下最终收敛。
* OT 与 CRDT 都不是“自动解决所有冲突”。富文本、树、白板、表格、移动/删除、属性修改仍需要产品定义语义。
* CRDT 常更适合离线和多副本同步，但会增加稳定 ID、tombstone/version vector、压缩和历史维护成本。
* OT 常围绕中心排序和 operation context 设计，成熟于在线文档协作，但转换函数、版本上下文和撤销语义需要严格维护。
* Sync protocol 必须处理乱序、重复、丢失、重连、离线 gap、snapshot、history compaction 与权限变化。
* Undo/redo 是协作语义的一部分。用户希望撤销自己的意图，而不是机械恢复某个全局旧快照。
* Conflict resolution 最终是产品体验：系统要能解释谁改了什么、哪些内容被合并、哪些需要人工决策、如何恢复历史版本。

关键路径
--------

实时编辑：

::

   user edit
   → apply locally to editor model
   → create operation/update + local sequence
   → pending queue
   → realtime transport
   → server auth/order/merge
   → persist operation/snapshot
   → ACK local client
   → broadcast remote update
   → other replicas merge and render

离线重连：

::

   local edits while disconnected
   → retain operation/update history
   → reconnect with known version/vector
   → exchange missing updates
   → deduplicate + order/merge
   → resolve semantic conflicts
   → persist converged state
   → rebuild presence separately

概念辨析
--------

* **Presence 与 Document Data**：presence 是会话临时信号，document data 是需要刷新/重登录后仍存在的用户资产。
* **OT 与 CRDT**：OT 重点在操作转换与上下文，CRDT 重点在复制数据/更新的可合并收敛规则。
* **Convergence 与 Correct Semantics**：副本最终相同不代表结果符合用户业务意图，语义冲突仍需产品规则。
* **Realtime 与 Durable**：实时广播说明变化快速传播，不代表变化已经安全持久化。
* **Local-First 与 Client-Authoritative**：本地先应用是延迟策略，权限和跨用户最终事实仍需可信同步/持久化边界承认。

本章结论
--------

实时协作应按 ``Local Intent → Operation/Update → Transport → Order/Merge → Durable History → Replica Convergence → User Recovery`` 设计。OT、CRDT 和 WebSocket 都只是路径中的机制，真正的架构目标是让并发修改在低延迟体验下仍可追踪、可合并、可解释和可恢复。