第002章：Web Architecture Boundary Expansion
==============================================

核心知识点
----------

* 早期 Web 可以粗略看成 ``browser request → server response``；现代 Web 在这条主干上扩展出 client runtime、SSR、edge、CDN、database、browser storage、query cache、build output 与多种 deployment runtime。
* Client-side application 扩大了 browser boundary：DOM、Fetch、History、Storage、Worker、Service Worker 让浏览器承担交互、局部数据更新、本地状态和离线能力。
* SSR 把首屏 UI generation、request context、session、data loading 与部分 cache policy 放回 server；hydration 再把交互责任交回 browser。
* Full-stack framework 会把 route、loader/action、server component、mutation、cache、redirect、error boundary 包装成统一开发模型，但真实执行仍分布在不同 runtime。
* Edge runtime 与 CDN 位于 browser 和 origin server 之间，可做 redirect、rewrite、header、A/B routing、地区判断、缓存与早期拒绝，但通常受 API、CPU、memory、package 与 connection 限制。
* Database、object storage、server cache、CDN cache、browser cache 与 query cache 都会改变用户看到的数据版本，因此它们属于用户可见系统的一部分。
* Build time 是真实架构边界：它决定哪些页面预生成、哪些模块进入 client/server/edge bundle、哪些环境变量被捕获、哪些资源带版本 hash。
* Deployment runtime 会改变同一段代码的能力。Browser、Node.js、serverless、edge、static hosting、build time 的文件系统、TCP、secret、持久进程、region 与 cold start 能力并不相同。
* 多边界系统的关键风险是责任错位：把 server 状态当 client state、把 edge 当完整 server、把 cache 副本当 source of truth、把 build-time 值误认为 runtime 值。
* 实际分析的第一问应是“哪个 runtime 拥有这项责任”，然后再看状态、缓存、失败和恢复。

关键路径
--------

现代页面访问：

::

   browser navigation
   → CDN cache
   → edge runtime
   → origin server
   → database / storage
   → response
   → browser document
   → hydration / client runtime
   → follow-up data requests

边界扩展过程：

::

   browser ↔ server
   → rich client state
   → SSR / full-stack server rendering
   → CDN / edge execution
   → distributed cache + durable data
   → build-time output
   → deployment-specific runtime

概念辨析
--------

* **CSR 与 Browser Boundary**：CSR 让更多 UI 和状态逻辑在浏览器执行，但可信数据和最终权限仍不能只由 client 决定。
* **SSR 与 Server-Only**：SSR 只把首屏生成等责任移到 server，页面仍需 browser 解析、渲染并常常 hydration。
* **Edge 与 Origin Server**：Edge 更靠近用户，适合轻量早期决策；origin 通常拥有更完整 runtime、数据库和内部服务能力。
* **CDN Cache 与 Edge Compute**：CDN cache 主要复用已有响应，edge compute 会运行逻辑；二者可以同处边缘网络但职责不同。
* **Build Time 与 Runtime**：构建阶段生成 artifact，运行阶段处理真实请求；构建时可用的变量和文件不能自动代表线上运行时能力。

本章结论
--------

现代 Web 架构应按 ``Browser → CDN/Edge → Server → Data`` 的请求路径，加上 ``Build Time → Runtime Artifacts`` 的提前转换路径理解。复杂度来自责任在多个 runtime 间移动，因此任何框架功能都必须还原成“运行位置、状态所有权、缓存位置和失败恢复”。