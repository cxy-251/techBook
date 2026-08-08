第160章：Asset CSS Font and Static Resource Pipeline
====================================================

核心知识点
----------

* 图片、SVG、字体、视频、WASM、JSON、CSS、icon 等源码资源会经过 copy、transform、compress、hash、inline、extract 或 URL rewrite，最终成为浏览器和 CDN 可加载的 runtime resources。
* Asset pipeline 的核心链条是 ``source reference → build transform → emitted file/manifest → deployed URL → CDN/browser cache → render``。
* Hashed filename 把资源内容版本写进 URL，适合 ``public, max-age`` 与 ``immutable`` 长缓存；内容变化时生成新 URL，而不是覆盖旧文件。
* HTML/manifest 是当前资源版本的选择入口，通常需要更短 freshness 或 revalidation；静态 hash asset 则可以长期保存。
* 安全部署需要保留旧 hash 资源一段时间，因为旧 HTML、BFCache、Service Worker 和尚未刷新的 CDN region 仍可能引用旧文件。
* CSS pipeline 不只是文本拼接，还处理 CSS modules、PostCSS/语法转换、minification、resource URL rewrite、source map、critical CSS、extraction 与 runtime injection。
* CSS extraction 与 injection 会改变样式到达时机。外部 CSS 可能阻塞渲染，JS 注入 CSS 会依赖脚本执行，route-level CSS split 可能造成晚到样式和视觉跳变。
* Font pipeline 影响 FOUT、FOIT 与 layout shift。字体格式、subset、preload、``font-display``、fallback metrics、跨域 header 与缓存策略需要一起设计。
* Image pipeline 应显式处理尺寸、格式、DPR、responsive ``srcset/sizes``、lazy/eager loading、placeholder、宽高声明和 CDN 变体。
* CSS/font/image 的问题常来自“引用关系错误”而不是文件内容本身：base URL、public path、manifest、CSS ``url()``、CDN origin 和部署目录必须一致。
* Static resource diagnostics 应先确认最终 URL 和状态码，再确认 content type/cache，再确认 manifest/HTML 引用，最后检查渲染时序。

关键路径
--------

静态资源：

::

   source import / CSS url / public asset
   → build transform + optimization
   → content-hash filename
   → manifest / HTML / CSS reference
   → deploy static files
   → CDN/browser request + cache
   → decode/parse/render

版本发布：

::

   emit new hashed assets
   → upload assets first
   → publish HTML/manifest referencing new hashes
   → keep old hashes during compatibility window
   → garbage-collect only after old entry points expire

概念辨析
--------

* **Asset Source 与 Runtime Resource**：前者是仓库文件，后者是带部署 URL、header 和缓存身份的产物。
* **Hash Asset 与 Mutable HTML**：hash asset 适合长期 immutable，HTML 负责切换当前资源图。
* **CSS Extraction 与 CSS Injection**：前者生成外部 stylesheet，后者依赖 JS 在运行时插入样式；渲染时序不同。
* **Font Preload 与 Font Display**：preload 改变请求调度，font-display 决定字体等待/替换策略；二者解决不同问题。
* **Image Optimization 与 Lazy Loading**：前者减少/适配传输成本，后者决定什么时候请求；可组合使用。

本章结论
--------

静态资源应按 ``Source → Transform → Hashed Artifact → Reference → Cache → Render`` 阅读。资源 pipeline 的正确性决定版本能否稳定加载、缓存是否安全以及首屏是否稳定；URL、manifest、CDN 与浏览器渲染时序必须作为一条链共同设计。