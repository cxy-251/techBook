第153章：Stale Data, Split Brain UI, and Cache Consistency Failure
==================================================================

核心知识点
----------

* Stale data 是缓存副本落后于权威事实。它本身不一定是 bug；当 UI 把旧副本当最终事实并允许用户据此操作时，才成为一致性缺陷。
* 同一业务对象常同时存在于详情、列表、侧边栏计数、搜索索引、通知、另一个 tab、CDN/server/query cache 中，因此一次 mutation 会影响多个 read model。
* Split-brain UI 指不同区域展示同一资源的不同真相。根因通常不是一个页面“没刷新”，而是资源副本的 owner、key、失效和刷新协议不统一。
* 排查旧数据应先确认 durable state，再沿真实读路径逐层检查 browser/query cache、Service Worker、CDN region、server/framework cache 和 search/index 副本。
* Mutation result 只更新某个局部 cache，不代表列表、聚合、搜索和 route output 已经更新。失效范围必须按资源依赖图扩展。
* Cache race 常发生在旧 refetch、optimistic update、mutation result、route navigation 和自动刷新交错时；较早语义时间的响应可能更晚到达并覆盖新状态。
* 处理竞态需要 cancel/isolate in-flight read、resource version/updatedAt/ETag 判断、server-confirmed reconciliation 和有限 rollback，而不是按“最后到达响应”盲目覆盖。
* Permission change 会把 stale 从体验问题升级为安全问题。用户被移出 tenant、角色降低、session 失效后，旧缓存不能继续充当授权事实或暴露私有数据。
* Auth/permission 变化应触发 user/tenant-scoped query cache、server cache、route cache、realtime channel 与必要浏览器状态清理；UI 隐藏按钮不足以恢复安全边界。
* Deployment version skew 也会制造 split brain：旧 HTML、新 JS chunk、旧 RSC/API shape、Service Worker shell 和不同 CDN region 可能同时存在。
* 内容 hash、兼容 API、旧静态资源保留、release/version header 与受控 cache purge 是减少发布版本错配的关键。
* 缓存正确性只有在 failure mode 被设计后才成立：刷新失败是否继续显示旧值、旧值是否有标记、权限变化如何硬失效、版本漂移如何诊断都必须提前定义。

关键路径
--------

旧数据诊断：

::

   confirm database/source-of-truth version
   → identify stale UI location
   → map it to resource/read model
   → inspect client query/local state
   → inspect browser/service-worker cache
   → inspect CDN region/cache status
   → inspect server/framework cache
   → compare release/resource version
   → repair invalidation/revalidation path

Mutation 竞态恢复：

::

   mutation starts
   → cancel/isolate conflicting old reads
   → optimistic patch with version marker
   → server commits and returns version
   → reject responses older than current version
   → invalidate all dependent read models
   → refetch/reconcile

概念辨析
--------

* **Stale Data 与 Corrupt Data**：stale 是旧副本，corrupt 是事实本身错误；诊断入口不同。
* **Split-Brain UI 与 Multi-Model UI**：多个 read model 可以合法存在，问题在于它们对同一事实缺少一致的新鲜度协议。
* **Race Condition 与 Slow Request**：慢请求本身不是问题；旧语义响应覆盖新状态才构成竞态。
* **Permission Cache 与 Authorization**：缓存可以保存权限派生结果，但执行敏感操作时仍需可信边界重新授权。
* **Deployment Skew 与 Cache Stale**：前者是不同 release artifact/contract 共存，后者是同一语义版本的副本过期；两者可能叠加。

本章结论
--------

缓存一致性故障应按 ``Authoritative Version → Read Model → Cached Copy → Race/Invalidation → Permission/Release Boundary → Recovery`` 排查。稳定系统不要求所有副本同毫秒一致，而要求每个副本都能解释自己的版本、允许的 stale 窗口、失效责任和失败恢复。