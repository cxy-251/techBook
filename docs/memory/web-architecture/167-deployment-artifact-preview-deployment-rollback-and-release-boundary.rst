第167章：Deployment Artifact, Preview Deployment, Rollback, and Release Boundary
================================================================================

核心知识点
----------

* 真正上线的是 deployment artifact，而不是抽象的 commit。HTML、client bundle、server/edge output、manifest、migration、cache rule、config、feature flag 和 job worker 都可能属于一次 release。
* Release boundary 定义哪些变化必须一起生效、一起验证或保持兼容；边界过大扩大事故面，过小会拆散强依赖 contract。
* Preview deployment 把 branch/PR 变成可执行环境，能提前验证 route、asset、API、auth callback、metadata、cache header、runtime config 和 production build 行为。
* Preview 必须使用隔离 trust boundary：测试数据、sandbox third-party、preview secret 与访问控制，不能默认复用生产数据库和全权限凭据。
* 发布前应建立 artifact 清单：browser、server、edge、routing、schema、cache、config、background job、observability 都要有版本事实。
* Rollback 不只是“切回旧代码”。数据库 schema、已写入数据、CDN cache、旧/new browser session、Service Worker、queue payload 和 feature flag 可能已经前进。
* Schema 变化应优先采用 expand/contract 和向前/向后兼容策略，让旧代码与新 schema 在短暂 version skew 中都能工作。
* Version skew 是 Web 发布常态：浏览器、CDN region、serverless instance、server node、database schema 和 job worker 不可能瞬时同时切换。
* Hashed static asset 应保留旧版本一段时间，避免旧 HTML 或已打开页面在发布后请求不存在的 chunk。
* Cache rule、API contract、queue payload、config 与 schema 都是 release contract；改动时必须考虑跨版本兼容。
* Deployment pipeline 需要 verification gate：build、typecheck、test、preview smoke、migration compatibility、bundle/artifact check、安全扫描和 rollback/fallback 检查。
* Release engineering 决定新旧系统如何共存、错误如何扩散和恢复，因此本身就是 Web architecture。

关键路径
--------

发布：

::

   source commit
   → reproducible build
   → versioned artifacts + metadata
   → preview deployment
   → smoke/contract/migration checks
   → production release
   → browser/CDN/runtime/schema/jobs gradually converge
   → observe release id across layers

回滚判断：

::

   production failure
   → identify affected artifacts/state
   → check schema/data forward compatibility
   → check cached/client versions
   → switch traffic/code if safe
   → otherwise forward-fix incompatible state
   → verify jobs/config/cache converge

概念辨析
--------

* **Commit 与 Deployment Artifact**：commit 是源码输入，artifact 是运行时真正执行/加载的版本化输出。
* **Preview 与 Production**：preview 验证真实产物，但不应拥有生产级数据与权限。
* **Rollback 与 Forward Fix**：可逆状态可以回滚，已前进且不兼容的数据/schema 常需要向前修复。
* **Release Boundary 与 Service Boundary**：release boundary 描述哪些变化要协调生效，不等同于代码服务划分。
* **Version Skew 与 Failed Deploy**：短暂版本错位是正常现象；只有 contract 不兼容时才演化成故障。

本章结论
--------

发布应按 ``Artifact → Preview Evidence → Release Contract → Version Skew → Rollback/Forward Fix`` 阅读。稳定发布不依赖“所有层同时切换”，而依赖新旧版本在迁移窗口内保持兼容，并让每个 artifact、schema、cache 和 runtime 都可被精确追踪。