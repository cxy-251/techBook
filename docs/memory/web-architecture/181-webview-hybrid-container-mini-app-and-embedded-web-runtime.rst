第181章：WebView, Hybrid Container, Mini-App, and Embedded Web Runtime
======================================================================

核心知识点
----------

* Embedded Web 把 Web document/runtime 放进原生应用、超级 App、小程序或企业容器，页面仍使用 HTML/CSS/JavaScript，但生命周期和能力由宿主管理。
* WebView 与普通浏览器最大的差异是宿主接管了部分浏览器责任：入口、返回栈、外链、权限提示、文件选择、下载、调试、cookie 注入和崩溃恢复都可能由 App 决定。
* Embedded runtime 必须明确五个对象：host app、WebView/runtime、loaded origin、server API、native capability；每个对象拥有不同状态和信任等级。
* Hybrid app 用 bridge 把 Web UI 与原生能力连接起来。Web 页面表达业务意图，宿主负责把意图转换成支付、相机、文件、定位、推送等系统调用。
* Native bridge 是高风险 capability boundary。低权限且可远程更新的页面一旦通过 bridge 触达高权限原生层，XSS 后果会被显著放大。
* Bridge contract 至少应定义 operation、payload schema、allowed origin/frame、user gesture、permission context、request id、result/error shape 与生命周期。
* Host 必须对 bridge 请求重新做来源、参数、权限和业务状态校验，不能因为消息来自自己的 WebView 就自动信任。
* Embedded runtime 的 host capability surface 通常与完整浏览器不同：API 支持、Cookie、storage partition、WebRTC、下载、文件、media 和调试能力可能受容器版本限制。
* Mini-app/super-app 容器拥有自己的 route、lifecycle、package size、审核、权限、缓存和 API contract，同一 Web 代码需要显式适配宿主规则。
* Auth 与 navigation 假设会变化。SSO/token 可能由 native host 注入，返回键/深链/支付回调可能绕过普通 browser history。
* Bridge callback 必须绑定 WebView/document 生命周期；页面已导航或实例已销毁后到达的异步回调不能继续修改旧上下文。
* Embedded Web 的正确架构不是“Web 页面 + 一堆原生 API”，而是明确哪些职责属于 Web、host、server 与 OS，并为跨边界动作提供可观测证据。

关键路径
--------

Embedded 请求与能力调用：

::

   user enters native screen
   → host creates WebView and loads trusted origin
   → document/runtime starts
   → page reads server data
   → page emits typed bridge intent
   → host validates origin/schema/permission/business state
   → native SDK / OS capability
   → typed result callback
   → page revalidates server state and updates UI

Bridge 安全检查：

::

   message received
   → verify current main-frame origin
   → verify operation allowlist
   → validate payload schema
   → verify user gesture / native permission
   → verify trusted business state
   → invoke native capability
   → verify callback still belongs to active WebView/document

概念辨析
--------

* **WebView 与 Browser**：都执行 Web 内容，但 WebView 的入口、UI、权限和生命周期被宿主应用包裹。
* **Hybrid App 与 PWA**：hybrid app 依赖原生容器和 bridge；PWA 仍由浏览器/Web 平台托管。
* **Bridge 与 Ordinary API Request**：bridge 跨到原生高权限层，风险通常高于普通 Web HTTP 调用。
* **Web Origin 与 Host Trust**：页面 origin 是 Web 信任标识，host app 是另一层原生信任主体，二者必须显式绑定。
* **Container Capability 与 Web Platform Capability**：容器可以新增原生能力，也可能缩减或改变普通浏览器 API 行为。

本章结论
--------

Embedded Web 应按 ``Host Ownership → Web Runtime → Origin → Bridge Contract → Native Capability → Lifecycle/Recovery`` 阅读。真正需要设计的是宿主接管了哪些浏览器责任，以及每次 Web → Native 权限跃迁如何被验证、限制和恢复。