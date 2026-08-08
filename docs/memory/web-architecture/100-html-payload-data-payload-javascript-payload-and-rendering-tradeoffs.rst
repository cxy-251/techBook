第100章：HTML Payload, Data Payload, JavaScript Payload, and Rendering Tradeoffs
=============================================================================

核心知识点
----------

* 现代页面不是单一“HTML 响应”，而是 HTML、data payload、JavaScript、CSS、font、image、manifest 等多类 payload 的组合。
* HTML 决定浏览器多早获得结构、文本和关键资源发现机会；更多 HTML 可减少空白和提升公开可读性，但增加 server render、传输、解析与缓存复杂度。
* JavaScript 决定交互能力和客户端状态逻辑；更多 JavaScript 会增加下载、解析、编译、执行、hydration、内存和长期运行成本。
* Data payload 决定 server truth 如何进入 browser。过大 payload 增加下载、JSON/RSC 解析、对象分配与 stale state；过细 payload 增加请求数量、协调、waterfall 与失效复杂度。
* CSS 和 font 属于渲染就绪路径，可能阻塞或改变首屏视觉，造成 FOUC、FOIT 与 layout shift，不能从渲染模型分析中排除。
* 图片等关键资源是否能在初始 HTML 被早期发现，会直接影响浏览器调度和 LCP。
* Payload 大小本身不是最终目标；优化目标是减少用户从导航到“看见、理解、交互、完成任务”的总等待时间。
* SSR、CSR、SSG、RSC、islands、resumability 只是把同一组 payload 工作移动到不同 runtime 和时间点，必须用真实设备与网络指标验证。

关键路径
--------

::

   Navigation
     → HTML Document
        ├─ DOM structure / metadata
        ├─ CSS / font discovery
        ├─ image discovery
        ├─ data payload references
        └─ JavaScript references
     → Browser Parse / Style / Layout / Paint
     → Data Parse / Cache / State
     → JS Download / Compile / Execute
     → Hydration / Activation
     → User Interaction
     → Next Paint / Task Completion

* 分析页面时列出每类 payload 的：生产 runtime、传输大小、缓存层、解析/执行成本、用户任务优先级和失败模式。
* 若 HTML 已很快但按钮迟钝，重点查 client JavaScript 与 activation；若 JS 很小但首屏仍慢，继续查 TTFB、CSS、font、LCP resource 与 data waterfall。

概念辨析
--------

* **HTML 多 ≠ 页面一定快**：大 HTML、慢 server render、低缓存命中和复杂 DOM 可能抵消提前内容的收益。
* **JavaScript 少 ≠ 交互一定快**：同步业务计算、第三方任务、layout thrash 和网络 mutation 仍会造成输入延迟。
* **Data payload ≠ 数据库真相**：它只是一次序列化快照或缓存副本，仍需新鲜度和失效语义。
* **RSC payload ≠ HTML**：RSC 是框架级组件数据传输对象，浏览器仍需要 HTML/DOM 与客户端组件代码共同完成页面。
* **请求数少 ≠ 总等待少**：单个巨大 payload 可能推迟首屏；合理拆分可提高优先级与缓存粒度，但过度拆分会制造 waterfall。

本章结论
--------

渲染性能应按 payload 而非框架名分析。HTML、数据、JavaScript、样式、字体和图片分别占据不同关键路径；最合适的渲染模型应把关键内容尽早放入可发现、可缓存的 payload，把非关键交互和数据延后，同时控制浏览器执行成本，使用户完成核心任务的总等待最小。
