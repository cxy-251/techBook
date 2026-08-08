第159章：Client Bundle, Server Bundle, Edge Bundle, and Output Target
====================================================================

核心知识点
----------

* Output target 定义产物面对哪个 runtime，因此也定义可用 API、模块格式、secret 可见性、文件系统、网络能力、生命周期与错误恢复方式。
* Full-stack 构建常同时生成 client bundle、server bundle、edge bundle、worker bundle、static assets、RSC/data payload 和 route/asset manifest。
* Client bundle 必须按“公开且受限环境”设计：用户可下载和检查代码，浏览器受网络、CPU、内存和兼容性约束，secret 和最终权限规则不能进入客户端产物。
* Server bundle 可以访问数据库、secret、内部服务、文件系统和可信会话，但仍受 Node/Bun/Deno、serverless、container、冷启动和资源限制影响。
* Edge bundle 以靠近用户的低延迟换取 runtime capability 收缩，常适合 redirect、locale、轻量 auth hint、header/cache policy 等早期决策。
* Edge 不应被假设等同 Node server。Node builtin、native addon、TCP driver、文件系统和长事务能力可能不可用或受平台约束。
* Worker bundle 面向独立执行上下文。Web Worker、Service Worker、Worklet 和平台 Worker 都需要专门入口、global object、通信方式和资源权限。
* Server-only 与 client-only boundary 必须在 build time 强制。只靠开发者约定容易让 ``fs``、database driver、secret env 进入 client，或让 ``window/localStorage`` 进入 server output。
* Client artifact 的版本和缓存是部署边界。旧 HTML 仍可能引用旧 chunk，因此新版本发布后应保留旧 hash 资源一段兼容窗口。
* Server output 的状态所有权要区分 request state、session state、durable state 与 cache state；可访问不代表可以把所有状态长期放在进程内存。
* Multi-output framework 的架构阅读应落到“哪个源码模块最终进入哪个产物、由谁加载、在哪个 runtime 执行”。

关键路径
--------

多目标构建：

::

   shared source graph
   → build/runtime boundary analysis
   → client output → browser
   → server output → server runtime
   → edge output → edge isolate
   → worker output → worker context
   → static assets → CDN/static hosting

边界检查：

::

   source import
   → determine target runtime
   → verify allowed globals/APIs/secrets
   → inspect emitted artifact/manifest
   → deploy to matching host

概念辨析
--------

* **Client Bundle 与 Public Code**：client bundle 会被用户获取，因此其中内容都应按公开材料处理。
* **Server Bundle 与 Trusted Runtime**：server 更可信，但仍必须执行 authorization、secret 管理和资源限制。
* **Edge 与 Serverless**：edge 强调靠近用户及受限 runtime；serverless 强调按请求/事件扩缩容，两者可以重叠但不等同。
* **Worker 与 Main Thread**：worker 是独立执行上下文，通过 message/event 与页面或平台协作，不共享普通 DOM 执行模型。
* **Source Boundary 与 Output Boundary**：源码目录命名只是意图，最终产物和加载者才证明运行位置。

本章结论
--------

多 runtime 构建应按 ``Source Module → Output Target → Runtime Capability → Trust Boundary → Deployment`` 阅读。Full-stack Web 的关键不是“一套 JavaScript 到处运行”，而是同一源码图被切成不同能力、信任和生命周期的产物。