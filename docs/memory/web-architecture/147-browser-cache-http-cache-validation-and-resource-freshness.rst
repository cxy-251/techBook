第147章：Browser Cache, HTTP Cache, Validation, and Resource Freshness
=======================================================================

核心知识点
----------

* Browser cache 主要保存同一用户代理已经获得的 HTTP response 副本；每个 HTML、JS、CSS、font、image 等资源都独立计算缓存命中和 freshness。
* HTTP cache 行为由 ``Cache-Control``、``ETag``、``Last-Modified``、``Vary``、``Expires``、``Age``、status code 与 request method 等共同决定。
* ``no-cache`` 允许存储，但复用前必须 revalidate；``no-store`` 才表示不应保存；``private`` 限制共享缓存；``public`` 明确允许共享缓存。
* Fresh response 可以直接复用，不需要网络往返。对带 content hash 的静态资源，长 ``max-age`` + ``immutable`` 是稳定策略。
* 长缓存成立的前提是“同一 URL 在生命周期内代表同一内容”。发布新版本应生成新 hash URL，而不是覆盖旧 URL 的内容。
* Stale response 需要重新验证或进入明确 stale policy。``ETag + If-None-Match``、``Last-Modified + If-Modified-Since`` 可让服务器用 ``304`` 确认副本未变化。
* ``304 Not Modified`` 不携带完整新 body，而是更新已存 response 的元数据并继续复用原副本，因此仍然有一次网络往返。
* HTML 通常承担当前资源图入口，适合短 TTL 或 ``no-cache``；带 hash 的 JS/CSS/font/image 可长期缓存并保留旧版本以服务旧 HTML。
* Reload、hard reload、history navigation、BFCache、Service Worker 与普通 HTTP cache 是不同路径；“刷新后仍旧”必须确认实际走了哪种机制。
* Browser cache bug 常被误判为部署失败：旧 HTML 引用旧 chunk、Service Worker 保存旧 shell、旧 CSS/字体持续命中，都可能造成白屏、样式错乱或功能不一致。

关键路径
--------

浏览器 HTTP cache：

::

   browser creates request
   → find matching stored response
   → if fresh: reuse directly
   → if stale + validator: conditional request
   → 304: reuse body + refresh metadata
   → 200: replace stored response
   → parse/render/request subresources

版本化静态资源：

::

   build content
   → generate content-hash URL
   → publish asset first
   → HTML references new URL
   → old URL remains immutable
   → old/new HTML can both load valid assets

概念辨析
--------

* **no-cache 与 no-store**：前者允许存储但要求验证；后者要求不保存。
* **Fresh Hit 与 304**：fresh hit 不发网络请求；304 仍需要条件请求和网络往返。
* **HTTP Cache 与 BFCache**：HTTP cache 保存 response，BFCache 保存整个 page snapshot。
* **HTTP Cache 与 Service Worker Cache**：前者由 HTTP 缓存语义管理，后者可由应用代码通过 Cache API 主动读写。
* **Stable URL 与 Immutable Content**：URL 若长期缓存，就必须稳定代表同一内容；内容变化应换 URL。

本章结论
--------

浏览器缓存应按 ``Request Identity → Stored Response → Freshness → Validation → Resource Version`` 阅读。稳定部署的关键是让 HTML 负责切换资源版本，让 hash 资源长期不可变，并在排查时区分 HTTP cache、BFCache 与 Service Worker 等不同恢复路径。