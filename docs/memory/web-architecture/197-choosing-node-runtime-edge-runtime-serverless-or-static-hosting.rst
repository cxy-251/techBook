第197章：Choosing Node Runtime, Edge Runtime, Serverless, or Static Hosting
============================================================================

核心知识点
----------

* Runtime 选择首先看请求需要什么能力：secret、database、filesystem、streaming、WebSocket、后台任务、执行时长、region、日志和回滚。
* Static hosting 适合预构建的公开 artifact：HTML、CSS、JS、image、font、SSG 页面和 SPA shell；可信动态逻辑必须交给其他 runtime。
* Node runtime 适合完整 server capability、稳定连接池、复杂 middleware、流式处理、长连接、队列 worker 和较长生命周期任务。
* Serverless 适合 request-scoped、事件驱动和突发流量；优势是低运维和按需扩缩，代价是 cold start、timeout、包体、连接和无状态约束。
* Edge runtime 适合靠近用户的轻量决策：地区路由、redirect、header 改写、A/B、cache policy、轻量鉴权；通常不适合长事务和重依赖。
* 数据位置可能推翻计算位置。Compute 放在 edge，如果 primary database 远在中心 region，端到端延迟可能反而更高。
* Runtime capability 不能从框架文档推断，必须以目标平台实际支持的 API、timeout、body、streaming、WebSocket、Node compatibility 为准。
* Node 进程内状态只适合临时优化。进程重启、扩缩容和滚动发布会清空内存，持久事实仍需 database/cache/queue 等外部系统。
* Serverless execution environment 可能复用，但应用不能依赖它永久存在；连接池和全局对象只能视为 opportunistic reuse。
* Static、edge、serverless、Node 常在同一系统组合使用。架构问题不是选四选一，而是每段路径应落在哪个 runtime。
* 每多一个 runtime，就增加日志、超时、权限、缓存、发布和回滚边界，需要相应 observability。
* Runtime 决策必须同时计算成本和失败模型，包括平台锁定、区域限制、并发、冷启动、进程故障和调试复杂度。

关键路径
--------

Runtime 选择：

::

   request/workload
   → list required capabilities
   → locate authoritative data
   → estimate lifetime/connection/stream needs
   → compare static/edge/serverless/Node
   → verify target platform behavior
   → define logs/timeouts/retry/rollback

典型组合：

::

   static assets → CDN/static hosting
   early routing/cache decision → edge
   burst request API → serverless
   transaction/long-lived/worker workload → Node service
   durable state → database/queue/object storage

概念辨析
--------

* **Runtime 与 Hosting Product**：runtime 是代码执行边界，hosting product 可能同时提供多个 runtime。
* **Edge 与 Serverless**：都可能短生命周期和托管扩缩，但 edge 更强调地理分布与受限 Web API，serverless 不一定靠近用户。
* **Static Hosting 与 SPA Backend**：SPA 前端可静态托管，API 和可信逻辑仍需要动态 runtime。
* **Warm Reuse 与 Persistent Process**：serverless 实例可能复用，但不能按长期进程假设设计持久状态。
* **Compute Proximity 与 End-to-End Latency**：计算靠近用户不代表数据也靠近用户；必须测完整请求路径。

本章结论
--------

Runtime 应按 ``Required Capability → Data Location → Lifecycle → Platform Limits → Cost/Failure`` 选择。现代 Web 往往组合 static、edge、serverless 与 Node；正确性来自把每段工作放到能力匹配且数据路径合理的执行边界。