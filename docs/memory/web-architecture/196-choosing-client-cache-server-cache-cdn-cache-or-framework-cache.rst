第196章：Choosing Client Cache, Server Cache, CDN Cache, or Framework Cache
===========================================================================

核心知识点
----------

* Cache 选择从数据真相和 freshness requirement 开始，而不是从“哪层命中率最高”开始。
* Browser HTTP cache、client query cache、server cache、CDN cache、framework cache 保存的都是副本；source of truth 仍在数据库、服务、对象存储或其他权威系统。
* Client query cache 适合用户会话内的远端状态副本，例如列表、详情、搜索、收藏、通知和 optimistic UI；权限仍由 server 决定。
* Server cache 适合昂贵 backend work，能结合 trusted context、tenant、role、locale、region、policy version 设计更安全 key。
* CDN cache 适合公开或可安全分段的 response，尤其是 versioned asset、公开 HTML 和匿名内容；credential/personalization 会迅速增加共享风险。
* Framework cache 可能缓存 data、render output、route、function result 等对象；必须先还原“实际缓存了什么”，再决定失效方式。
* Cache key 比缓存层数量更重要。任何影响响应语义的 tenant、user scope、locale、currency、region、permission、version 都必须进入身份设计或禁止共享。
* Invalidation strategy 要在大规模缓存前设计。Mutation、权限变化、发布、配置变化都需要明确触发 tag/key/path/purge/revalidation。
* SWR/stale-while-revalidate 是 UX 和 consistency 选择：允许先显示旧值，再后台刷新；是否可用取决于旧数据风险。
* 多层缓存不会自动同步。客户端、CDN、server、framework 各自有 owner、TTL 和 invalidation path。
* 缓存系统必须可观测：hit/miss/stale/revalidate/purge/key/tag/region/version 应能被检查，并保留人工恢复入口。
* 缓存失败最危险的不是“没命中”，而是错误命中：跨用户、跨 tenant、旧权限、旧价格或旧 release 被合法返回。

关键路径
--------

缓存选择：

::

   identify source of truth
   → define acceptable stale window
   → classify public/private/personalized
   → choose cache location
   → define complete cache key
   → define invalidation/revalidation
   → define observability/manual recovery

多层读取：

::

   browser/client cache
   → CDN/framework cache
   → server cache
   → authoritative data/service
   → response
   → mutation invalidates affected copies

概念辨析
--------

* **Browser Cache 与 Client Query Cache**：前者保存 HTTP response，后者保存应用层 server-state snapshot。
* **Server Cache 与 CDN Cache**：server cache 能看到可信上下文，CDN 更擅长公共共享和全球分发。
* **Framework Cache 与 Magic Cache**：framework 只是提供缓存抽象，key、scope、freshness 和 owner 仍需显式理解。
* **Fresh 与 Correct**：fresh 只说明副本未过期，correct 还要求副本身份与当前请求上下文匹配。
* **SWR 与 Strong Consistency**：SWR 明确允许旧值窗口，不适合必须立即确认的交易和权限事实。

本章结论
--------

缓存应按 ``Authority → Sharing Scope → Cache Key → Freshness → Invalidation → Recovery`` 设计。缓存层越多，副本协议越复杂；性能收益必须建立在正确身份、明确失效和可观测恢复之上。