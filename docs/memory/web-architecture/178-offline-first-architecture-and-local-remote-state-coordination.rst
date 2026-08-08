第178章：Offline-First Architecture and Local-Remote State Coordination
=======================================================================

核心知识点
----------

* Offline-first 的前提是把网络当作可失败依赖，而不是永远在线的默认条件；读取、写入、恢复与同步都必须拥有明确本地路径。
* 离线时，本地状态可以临时驱动 UI，但远端 server/database 仍负责最终权限、业务规则和持久事实。
* 本地状态应拆成不同责任：app shell、业务快照、本地草稿、待同步 operation log，不能混成一个模糊缓存对象。
* Cache Storage 更适合按 Request/Response 保存 shell 与离线资源；IndexedDB 更适合结构化业务实体、版本、草稿和操作队列。
* Offline read path 必须同时表达数据和可信度：最近快照、stale 快照、只读副本、无缓存空态需要不同 UI。
* Offline write path 记录的是用户意图，不是“稍后再发一次表单”。操作应带 operation id、base version、idempotency key、retry state 与错误信息。
* 网络恢复后的同步必须处理重复、乱序、资源删除、权限变化和其他用户并发修改；同步不是简单 replay。
* Idempotency 负责防止同一意图被重复持久化；version/baseVersion 负责判断本地意图基于哪一版远端事实。
* Conflict strategy 属于产品语义。自动 merge、server wins、client wins、字段级合并或人工解决，必须根据数据风险选择。
* 大文件离线上传应把二进制、元数据和操作状态分开，支持待上传、重试、取消和 orphan cleanup。
* Local schema 也需要版本迁移。长期离线设备可能同时持有旧 Service Worker、旧 IndexedDB schema 与新 server contract。
* Offline UX 必须让用户知道当前状态是 synced、cached、draft、pending、failed 还是 conflict；否则离线能力会破坏用户信任。

关键路径
--------

离线读取：

::

   user opens page
   → service worker/network attempt
   → network unavailable
   → load app shell from Cache Storage
   → read structured snapshot from IndexedDB
   → evaluate snapshot freshness/permission confidence
   → render cached/read-only/offline state

离线写入与恢复：

::

   user mutation
   → persist local operation + idempotency key
   → optimistic local UI
   → network reconnect
   → send pending operations
   → server auth + version/conflict check
   → durable commit or reject
   → reconcile local snapshot/queue/UI

概念辨析
--------

* **Offline-First 与 Cache-First**：offline-first 是完整状态与恢复架构，cache-first 只是某类请求读取策略。
* **Local Source of Truth 与 Durable Source of Truth**：离线时本地副本临时决定 UI，远端可信系统最终决定跨用户业务事实。
* **Draft 与 Pending Mutation**：draft 尚未承诺提交，pending mutation 已表达用户意图并等待远端确认。
* **Retry 与 Replay**：retry 必须带幂等和冲突判断；机械 replay 可能重复写入或覆盖新数据。
* **Stale 与 Conflict**：stale 表示副本旧，conflict 表示两个有效修改无法按当前规则直接合并。

本章结论
--------

Offline-first 应按 ``Local Availability → Local State Ownership → Operation Log → Sync → Conflict → Reconciliation`` 设计。核心不是“断网还能打开页面”，而是在本地可用性与远端一致性之间建立可追踪、可重试、可冲突恢复的状态协议。