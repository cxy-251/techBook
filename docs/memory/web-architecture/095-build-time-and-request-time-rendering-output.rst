第095章：Build-Time and Request-Time Rendering Output
=====================================================

核心知识点
----------

* 渲染输出不只包含 HTML，还包括 JSON/RSC payload、CSS、JavaScript chunk、route metadata、preload hint、cache header 与 redirect 结果。
* ``build-time output`` 是用户请求前已经固定的快照；它只能使用构建阶段可见的数据、配置和环境变量。
* ``request-time output`` 在请求到达后生成，可读取 URL、headers、cookie、authorization、locale、session、tenant、实验分组和实时数据。
* 静态输出把成本从请求路径迁移到构建、发布、产物存储、CDN 与缓存失效；动态输出则把计算、依赖和尾延迟放回用户请求路径。
* 同一页面可以拆成多种生成时间：稳定 layout 和公开内容在 build time，会员状态与权限在 request time，低优先级区域在 client time。
* 输出生成时间决定缓存能力：越依赖用户上下文，越难进入 shared cache；越稳定公开，越适合 CDN 复用。
* build-time secret、server runtime secret 与 client-exposed variable 必须分开；任何进入浏览器 bundle 的值都不能再视为秘密。
* 判断输出是否陈旧，应追踪 ``source version → generated artifact → CDN/cache copy → browser copy``，而非只看数据库当前值。

关键路径
--------

::

   Source Code / CMS / Public Data
     → Build Time
     → HTML / JSON / Manifest / Bundles
     → Deployment Artifact
     → CDN / Static Hosting

   User Request + Cookie + Locale + Auth
     → Edge / Server Runtime
     → Live Data / Permission / Session
     → Request-Time Output
     → Response + Cache Policy
     → Browser
     → Optional Client Fetch / Activation

* 内容更新后页面仍旧，依次检查：源数据是否更新、artifact 是否重新生成、部署版本是否切换、CDN 是否 purge/revalidate、浏览器是否仍命中旧副本。
* 请求时渲染慢，依次拆分 session、数据库、内部 API、模板执行、冷启动与网络传输，不要把所有时间归为“SSR 慢”。

概念辨析
--------

* **build time ≠ static hosting**：构建阶段也可能生成 server bundle、route manifest 和 edge output；它们仍将在运行时执行。
* **request time ≠ 不缓存**：请求时结果仍可使用 server cache、HTTP cache、CDN cache，只是缓存键必须覆盖影响响应的上下文。
* **环境变量 ≠ runtime secret**：构建时内联进客户端 bundle 的变量已经公开；只有留在可信 server runtime 的值才能作为 secret。
* **动态输出 ≠ 最新真相**：请求时渲染也可能读取缓存、副本或延迟数据，新鲜度仍由数据层和缓存策略决定。
* **静态输出 ≠ 零成本**：成本只是转移到了 build queue、artifact、发布、失效和版本管理。

本章结论
--------

页面输出的生成时间决定它能看到什么上下文、能缓存多久、会把成本放在哪一段路径上。稳定公开事实优先前移到 build/CDN；用户、权限与强实时上下文留在 request-time trusted boundary；不同片段采用不同时间点生成，通常比把整页强制绑定到单一静态或动态模式更可靠。
