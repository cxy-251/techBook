Browser Cache, Resource Lifetime, and Reload Semantics
=====================================================

核心知识点
----------

* “浏览器缓存”包含多层副本：memory cache、disk HTTP cache、preload cache、Service Worker Cache Storage、CDN cache、server cache；每层拥有不同生命周期和复用规则。
* HTTP cache 通过 freshness 与 validation 决定复用：``max-age``/``s-maxage`` 控制新鲜期，``ETag``/``Last-Modified`` 配合条件请求确认过期副本是否仍有效。
* ``no-cache`` 表示可以存储但复用前必须验证；``no-store`` 表示不应存储；``private`` 限制共享缓存复用；``public`` 允许共享缓存按规则保存。
* ``Vary`` 扩展 cache key，语言、编码、credential 等维度若设计错误会造成命中率下降或用户数据混用。
* Hashed JS/CSS 适合 ``public, max-age=31536000, immutable``；入口 HTML 通常应短 TTL 或强验证，以保证它指向当前 artifact graph。
* Reload、hard reload、history traversal、BFCache restore 与 Service Worker update 不是同一种路径；“刷新后正常”必须继续判断旧副本究竟来自哪一层。
* 部署和回滚必须与缓存生命周期对齐：新 HTML 引用的新 chunk 要存在，旧 HTML 仍可能引用旧 chunk，因此旧 hashed artifact 应保留一段安全窗口。

关键路径
--------

资源复用路径：

``Document/Resource Request → preload/memory cache → HTTP cache → Service Worker → CDN → Origin``

HTTP 验证：

``stale cached response → If-None-Match/If-Modified-Since → 304 → reuse local body``

版本发布：

``new deployment → new HTML/manifest → new hashed assets``

同时允许：

``old cached HTML → old hashed assets``

直到旧入口生命周期结束。

概念辨析
--------

* **HTTP Cache vs Service Worker Cache**：前者由 HTTP 语义自动管理；后者由应用脚本定义请求拦截和版本清理策略。
* **Browser Cache vs CDN Cache**：浏览器缓存是私有用户端副本；CDN 通常是跨用户共享副本。
* **Freshness vs Validation**：fresh 可直接复用；stale 不一定失效，可以通过 validator 确认继续使用。
* **Reload vs BFCache Restore**：reload 重新走资源加载；BFCache 可直接恢复冻结的 Document 与 JS heap。
* **Cache Busting vs Cache Invalidation**：内容 hash 通过新 URL 创建新版本；purge/invalidation 则主动使旧 key 不再可用。

本章结论
--------

缓存是资源版本与副本生命周期系统。排查旧页面、旧数据或发布错位时，必须先识别命中的缓存层，再检查 freshness、validation、Service Worker 和 CDN，最后回到 HTML 与 hashed artifact 的部署关系；只让用户“强刷”不能替代正确的缓存架构。