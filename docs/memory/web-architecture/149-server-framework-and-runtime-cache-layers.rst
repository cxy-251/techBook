第149章：Server Framework and Runtime Cache Layers
==================================================

核心知识点
----------

* Server cache 用于跨请求复用昂贵后端结果，例如数据库查询、远程 API、配置、feature flag、权限快照和聚合数据；其风险是把上下文相关结果错误扩大为全局结果。
* Framework cache 需要按“缓存了什么对象”理解：data result、function result、RSC payload、component output、route output、static generation artifact 的生命周期和失效入口不同。
* 同一次 server request 内的 memoization 与跨 request 持久 cache 是不同层级。前者只去重当前 render/request，后者改变多个用户请求的读取路径。
* Runtime cache key 必须表达 request context。Tenant、user/role/permission version、locale、range、feature flag、region 等会改变结果时，应进入 key 或禁止共享。
* 大页面不一定适合整体缓存。团队统计、导航用户信息、权限能力和实验区块可以拥有不同粒度的 key 与 TTL，降低错误共享和大范围 invalidation。
* Static generation、ISR 和 on-demand revalidation 把 build-time 与 runtime 混合：静态页面也会拥有运行期 freshness、regeneration 与失败恢复状态。
* Mutation 后必须沿真实依赖关系触发 cache tag、resource key、path 或 dependency invalidation；只更新数据库不会自动刷新 framework output。
* Cache tag/dependency graph 的价值是精确失效。粒度过粗会造成 cache stampede 和源站压力，粒度过细则增加依赖维护复杂度。
* Server cache failure 常是静默的：数据库已新、API 单测正确，但特定用户、region 或 route 仍持续看到旧结果，因此必须能观察 hit、key、tag、age 与 regeneration。
* Framework API 名称会变，稳定判断不变：代码在哪个 runtime、结果保存在哪里、谁共享、何时失效、mutation 后谁负责刷新。

关键路径
--------

服务端缓存读取：

::

   request
   → read tenant/user/locale/runtime context
   → derive cache identity
   → server/framework cache lookup
   → hit: reuse scoped result
   → miss: database/API computation
   → store with lifetime/tags
   → render response

Mutation 后失效：

::

   trusted mutation
   → database commit
   → derive affected resource dependencies
   → invalidate data tags / route outputs
   → next read regenerates or revalidates
   → monitor stale/regeneration failure

概念辨析
--------

* **Request Memoization 与 Persistent Cache**：前者通常只活在一次请求，后者跨请求保存结果。
* **Data Cache 与 Render Cache**：前者缓存数据读取，后者缓存渲染产物；一个新鲜不代表另一个也新鲜。
* **Static Generation 与 Immutable File**：静态生成结果可能在 runtime 被重新生成，因此不一定是真正 immutable artifact。
* **Cache Tag 与 Cache Key**：key 标识一份结果，tag 表达多个结果共享的失效依赖。
* **Framework Cache 与 Architecture**：框架只是提供 API，真正语义仍由共享范围、上下文和失效协议决定。

本章结论
--------

服务端缓存应按 ``Request Context → Cache Identity → Cached Object → Dependency → Invalidation → Regeneration`` 阅读。框架缓存不是免费优化，它会改变数据读取和页面生成时机；只有上下文、依赖和 mutation 失效都被显式建模，缓存才是可靠架构。