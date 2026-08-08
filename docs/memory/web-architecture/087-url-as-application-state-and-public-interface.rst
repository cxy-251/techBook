第087章：URL as Application State and Public Interface
======================================================

核心知识点
----------

* URL 是 Web 应用最稳定的公共状态接口，同时被用户、浏览器、服务器、CDN、日志、搜索引擎与路由系统观察。
* 进入 URL 的状态天然获得刷新恢复、分享、收藏、服务端直达、历史导航、缓存分片与问题复现能力，也会暴露给日志、代理、Referer 与外部系统。
* ``path`` 适合表达资源身份和层级，``query`` 适合表达搜索、筛选、分页、排序等可组合视图状态，``fragment`` 主要用于当前文档内定位，通常不会发送给服务器。
* URL state 应描述“这个地址代表什么页面”。登录凭证、未提交草稿、敏感临时状态应留在 cookie、session、form state 或 client memory。
* URL 设计会影响 route match、缓存键、canonical、SEO、权限检查、分析统计和长期兼容性，因此属于公共 API 设计。
* History API 可以让 SPA 在当前 document 中维护 URL 与 history entry，但公共页面语义仍应能够仅从 URL 重新推导。

关键路径
--------

``用户意图 → URL → Browser History → CDN/Proxy → Server Route → Data Read → UI State``

* 用户进入 ``/products?category=shoes&sort=price-asc&page=2#reviews``。
* ``/products`` 决定资源/路由层级；query 决定可分享列表状态；``#reviews`` 只负责文档内部定位。
* 浏览器刷新或他人直接打开链接时，服务器应仅凭 path、query、headers、cookies 等请求上下文恢复页面，而不能依赖旧组件内存。
* 客户端修改筛选时，应同步更新 URL；若用户会把变化理解为新的导航位置，使用新的 history entry，否则更新当前 entry。
* 服务端、CDN 与缓存层必须明确哪些 query 进入缓存键，避免不同页面状态错误复用同一响应。
* URL 参数进入业务层前应统一解析、规范化、限制默认值与非法输入，防止路由、缓存和数据读取各自解释同一参数。

概念辨析
--------

* **URL state vs client state**：URL state 可刷新、分享、回退；client state 服务当前运行时的局部交互记忆。
* **path vs query**：path 更接近资源身份和层级；query 更接近同一资源上的可组合视图参数。
* **query vs fragment**：query 会随 HTTP 请求到达服务器；fragment 主要留在浏览器/document 层。
* **URL vs History state**：URL 是公共接口；``history.state`` 适合保存当前浏览器会话中的轻量恢复辅助信息，不能替代公共页面身份。
* **可访问 URL vs 可授权资源**：能匹配 URL 只证明路由存在，资源存在性、用户身份和权限仍须由服务器独立验证。

本章结论
--------

URL 应被当作应用最外层、最稳定的状态契约。凡是需要刷新恢复、分享、深链、服务端直达、历史导航或缓存区分的页面状态，应优先评估是否进入 URL；凡是敏感、临时、未确认或仅属于当前交互的状态，应留在更合适的 owner 中。设计 URL 时同时检查 route、cache、security、SEO、history 与长期兼容，才能避免“页面能运行但地址无法可靠表达页面”的架构缺陷。
