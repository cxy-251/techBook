第151章：Revalidation, Invalidation, Purge, and Stale-While-Revalidate
======================================================================

核心知识点
----------

* Revalidation、invalidation、purge 与 stale-while-revalidate 都处理缓存更新，但触发者、位置和用户可见结果不同，不能混用成一个“刷新”。
* Revalidation 是询问“现有副本还有效吗”。HTTP 层常通过 ``ETag/If-None-Match``、``Last-Modified/If-Modified-Since``，framework/client 层则通过 tag、version 或 refetch 完成确认。
* Invalidation 是由权威状态变化主动宣布“相关副本不再可信”。Mutation、权限变化、发布、后台任务或运维事件都可以触发失效。
* Purge 更接近 CDN/edge 的具体副本操作：删除、驱逐或标记过期某些 URL、prefix、tag/surrogate key 对应的边缘结果。
* ``stale-while-revalidate`` 允许短时间先返回旧副本，再后台刷新，以较低延迟换取受控 stale 窗口；它不适合所有资金、权限和交易确认路径。
* Mutation 后的刷新范围应来自依赖关系，而不是页面名字。一次商品更新可能影响详情、分类列表、搜索、计数、推荐、静态页和 client query。
* 失效范围过小产生旧 UI，范围过大产生 cache stampede、源站和数据库瞬时压力。需要按 resource id、tag、path 和 read model 精确建依赖。
* 软失效允许旧副本暂时继续服务并后台刷新；硬失效要求下一次读取等待新结果。选择依据是旧数据的业务风险。
* 权限、session 和安全状态变化通常要求更严格失效，因为 stale 私有数据可能从体验问题升级为越权可见。
* Purge 成功不代表所有缓存层都新鲜。浏览器 HTTP cache、Service Worker、server cache、framework cache、client query cache 仍可能持有各自副本。
* Revalidation/invalidation 必须可观察：写入是否 commit、事件是否发出、目标 tag/key 是否正确、缓存是否接受信号、下一次读取是否真正重算。

关键路径
--------

写入后的缓存一致性：

::

   trusted mutation
   → durable commit
   → derive affected resource dependencies
   → invalidate server/framework/client caches
   → purge edge/CDN copies when needed
   → next read revalidates or regenerates
   → UI reconciles new facts

HTTP revalidation：

::

   stale cached response
   → send validator
   → upstream compares representation
   → 304: reuse body + refresh metadata
   → 200: replace cached response

概念辨析
--------

* **Revalidation 与 Invalidation**：前者确认旧副本还能不能用，后者主动宣布旧副本不再可信。
* **Invalidation 与 Purge**：invalidation 是语义动作，purge 是常见的 CDN/edge 执行动作。
* **Soft Invalidation 与 Hard Invalidation**：前者允许短暂 stale，后者阻止旧结果继续服务。
* **SWR 与 Eventual Consistency**：SWR 是一种缓存刷新策略，会制造明确的短暂旧值窗口；它只是最终一致性的一种实现手段。
* **Purge Everything 与 Precise Purge**：全量清空恢复粗暴但昂贵，日常更新应优先资源/tag 级精确失效。

本章结论
--------

缓存更新协议应按 ``Authoritative Change → Dependency Mapping → Invalidate/Purge → Revalidate/Regenerate → UI Reconciliation`` 设计。真正困难的不是让缓存“刷新”，而是准确决定哪些副本已经失信、允许旧多久、谁负责恢复，以及失败时如何保持系统可解释。