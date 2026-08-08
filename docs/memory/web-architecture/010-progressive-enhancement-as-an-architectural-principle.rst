Progressive Enhancement as an Architectural Principle
======================================================

核心知识点
----------

* Progressive Enhancement 是架构约束：先用 URL、HTML、link、form、HTTP 和服务器响应建立可工作的基础路径，再叠加 JavaScript 与客户端增强。
* 基础路径由浏览器和服务器共同拥有，负责导航、表单提交、历史记录、完整页面响应和可恢复错误。
* 增强层可以接管局部请求、客户端路由、pending 状态、动画、预取、离线缓存和乐观 UI，但应保持基础输入与结果语义。
* 增强层接管的浏览器责任越多，应用就越需要自行维护 history、focus、scroll、concurrency、error recovery 与 cache consistency。
* JavaScript 未加载、bundle 失败、hydration 延迟、网络慢、Service Worker 陈旧或 API 缺失都应被视为正常失败路径，而不是“不可能发生”的异常。
* URL、表单和语义 HTML 同时支撑可访问性、导航恢复、公开发现和无 JavaScript 基础能力，是多种系统属性共享的底座。

关键路径
--------

基础路径：

``User Intent → URL/link/form → Browser Native Behavior → HTTP Request → Server → HTML/Redirect/Error → New Document``

增强路径：

``Native Entry → JavaScript Ready → intercept navigation/submission → Fetch → partial update → history/state synchronization → UI``

增强失败后的恢复：

``enhancement failure → cancel/rollback/error UI → native navigation or form submission → server-owned result``

状态归属应保持：

``URL state → URL``
``durable business state → server/database``
``temporary interaction state → client runtime``
``cached copies → explicit cache layer``

概念辨析
--------

* **Progressive Enhancement vs No JavaScript**：它不是拒绝 JavaScript，而是要求 JavaScript 的增强责任建立在可工作的基础契约上。
* **Base Path vs Fallback Patch**：基础路径从设计时就存在；fallback patch 往往是增强路径失败后临时补救。
* **Native Form vs Client Mutation**：原生表单天然拥有 URL、编码、导航和提交语义；客户端 mutation 可以优化反馈，但要重新承担并发与恢复责任。
* **SSR HTML vs Hydrated App**：HTML 已可见不代表增强 runtime 已接管；hydration 窗口本身就是运行状态。
* **可访问性/SEO vs 独立附加项**：语义 HTML、稳定 URL、链接和表单同时服务多种系统能力，不应等到最后补齐。

本章结论
--------

渐进增强的核心不是“保守”，而是把复杂性分层。关键用户意图先由稳定 Web 契约形成闭环，客户端 runtime 再接管局部体验；当增强层不可用时，系统仍知道如何导航、提交、返回错误和恢复状态。