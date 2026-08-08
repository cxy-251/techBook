Mutation Result, Cache Invalidation, and UI Consistency
======================================================

核心知识点
----------

* Mutation 在数据库提交后还没有结束；系统必须把 durable fact 重新传播到浏览器、route data、server/framework cache、client query cache、CDN 和其他 UI 投影。
* Mutation result 是服务端回到 UI 的状态桥梁，通常应携带 canonical resource、version、resource id、redirect、field/business error 或异步任务状态，而不是只返回 ``ok: true``。
* Server echo 用服务端最终表示校准 optimistic state，尤其适合规范化字段、临时 ID → 真实 ID、派生计数、权限变化和版本更新。
* Cache invalidation 的含义是“声明哪些副本不再可信”，不是机械清空所有缓存；不同层应采用 key、tag、entity、path、TTL 或 revalidation 等不同机制。
* 写入影响的是资源本体及其投影：修改文章标题可能同时影响详情、列表、搜索、RSS、Open Graph 与客户端缓存。
* Client query cache、framework cache、CDN cache 和 component state 属于不同 runtime，不能假设某一层失效会自动同步其他层。
* UI consistency 是最终收敛问题：局部 optimistic patch、server echo、背景 refetch 和 route revalidation 应围绕同一资源 identity 与 version 合并，而非互相覆盖。

关键路径
--------

``Mutation Request`` → server validation / transaction → database commit → 生成 canonical result → 更新或标记 server/framework cache stale → 决定 CDN/HTTP cache 是否 purge、revalidate 或等待 TTL → response 返回 resource/version/redirect/error → client 用 server echo reconcile optimistic state → 精确更新能确定的新事实 → invalidate 无法安全推导的 query / route projection → 后台重新读取 → UI 收敛到同一 durable version。

创建资源时若客户端使用临时 ID，成功结果必须完成 identity migration；不能简单把 server 返回对象再 append 一次，否则会形成 ``temp`` 与真实资源并存的 identity split。

概念辨析
--------

* **mutation success vs UI consistency**：数据库成功只证明主事实成立；各副本和页面视图仍可能保持旧状态。
* **server echo vs refetch**：server echo 直接给出本次写入的权威结果；refetch 用于重新确认受影响但无法从结果安全推导的投影。
* **cache invalidation vs cache deletion**：invalidation 只表示副本不能继续无条件信任，后续可以重新验证、替换或按策略保留 stale 数据。
* **resource vs projection**：资源是权威实体；列表摘要、计数、搜索结果和页面片段是依赖它的派生表示。
* **local patch vs canonical result**：前者服务即时反馈，后者负责最终收敛；共享计数、权限和版本尤其应以服务端结果为准。

本章结论
--------

写入架构必须同时设计“事实如何提交”和“事实如何重新进入读路径”。Mutation result、资源 identity、cache invalidation 与 revalidation 共同决定 UI 是否最终一致；只把数据库写对而不管理副本，会让用户持续看到一个已经失效的世界。