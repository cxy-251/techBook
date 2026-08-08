SPA Navigation vs Document Navigation
=====================================

核心知识点
----------

* Document navigation 由浏览器主导，目标响应 commit 后创建或恢复新的 ``Document``；HTML、DOM、JS global、事件监听和页面启动路径以新 document 为边界重新建立。
* SPA navigation 复用当前 ``Document``，应用拦截默认导航，通过 History API 改 URL/history，再自行加载数据和更新组件树。
* Document navigation 天然拥有刷新、深链接、服务器 status/redirect、浏览器 scroll/focus/history 和生命周期语义；SPA 必须主动维护这些责任。
* SPA 的收益来自复用已加载 runtime、共享布局、内存 cache、连接和组件状态；风险来自状态泄漏、监听器/订阅未清理、旧请求覆盖新 route、cache stale、滚动和焦点恢复错误。
* ``pushState`` 不会立即请求目标 URL；目标 URL 在刷新、新标签页或恢复时仍必须由 server/CDN/static hosting 独立解释。
* SPA route 不是新的安全边界。权限和可信数据必须由服务器再次校验，不能因为客户端 router 隐藏某页面就认为资源不可访问。
* 现代框架通常在 document navigation 与 SPA transition 之间混合选择，本质是重新分配 browser/server/client 的 ownership。

关键路径
--------

Document navigation：

``Link/User Intent → Browser Navigation → HTTP/Cache/Server → Response Commit → New Document → Parse/Load/Initialize → Interactive Page``

SPA navigation：

``Click → preventDefault → pushState → abort old route work → load route data/chunks → update component/DOM → title/scroll/focus/error handling``

返回路径：

``Back → history traversal → document restore/reload OR popstate/client router restore → data freshness check → UI recovery``

概念辨析
--------

* **SPA vs Single Page URL**：SPA 指复用 document 的导航执行模型，不代表整个应用只能有一个 URL。
* **Route Boundary vs Document Boundary**：route 可以在同一 document 内变化；document boundary 则意味着新的或恢复的页面执行世界。
* **Client Routing vs Server Routing**：前者决定当前 document 如何表现某 URL；后者决定直接请求该 URL 时返回什么。
* **复用状态 vs 权威状态**：SPA 可以复用内存 cache 和 UI state，但服务器/数据库仍拥有业务事实。
* **更少页面刷新 vs 一定更快**：SPA 减少 document 重建，不保证数据 waterfall、JavaScript 执行、内存、缓存一致性或首屏一定更优。

本章结论
--------

Document navigation 用新的页面执行世界换取清晰生命周期和平台恢复语义；SPA navigation 用复用执行世界换取连续交互，同时把更多状态、错误、滚动、焦点、缓存和清理责任交给应用。架构判断应先确认 URL 变化是否跨过 ``Document`` 边界，再评估哪一侧真正拥有恢复责任。