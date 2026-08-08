第001章：Modern Web Integration Surface
========================================

核心知识点
----------

* 现代 Web 不是“前端 + 后端”两层结构，而是 browser、network、server、edge、database、cache、build time 与 deployment runtime 共同组成的多运行时系统。
* 分析任何 Web 行为时，优先回答四个问题：请求或交互经过什么路径、跨越哪些边界、状态由谁拥有、失败由谁恢复。
* Browser 是客户端运行环境，负责 navigation、DOM/CSS/JS、event loop、rendering、storage、permission 与同源/CORS/CSP 等策略执行。
* Browser 中的代码位于用户可观察、可修改输入的边界，不能承担 secret、数据库凭据或最终授权判断。
* Server 是更可信的 request handling、policy enforcement 与 data access 边界，可读取 secret、验证 session、执行业务规则、访问数据库并生成 HTML、JSON、stream、redirect 或 error。
* Network 不是透明函数调用，而是 URL、HTTP method/status/header/body、cookie、cache、redirect、TLS、CORS、streaming 等协议语义组成的边界。
* Web Platform 是 HTML、CSS、DOM、ECMAScript、Fetch、Storage、Worker、Service Worker、WebRTC、WebGPU 等能力的共同表面；框架只能封装其中一部分。
* Full-stack 的本质是跨 runtime 协调：browser、server、edge、database、cache、build output 与 deployment environment 之间传递请求、状态和失败。
* React、Next.js、Astro、SvelteKit、Hono、Prisma、Vite 等工具应被还原成“它在哪运行、封装哪个边界、状态在哪里、失败在哪里暴露”。
* 同一个用户现象可能来自多个状态副本，例如旧头像可能来自 component state、HTTP cache、Service Worker、CDN、server cache 或 database；定位必须先找 state owner。

关键路径
--------

一次现代 Web 请求：

::

   user intent
   → browser runtime
   → URL / HTTP / cookie / cache policy
   → CDN / edge
   → server runtime
   → database / storage / internal service
   → HTML / JSON / stream / redirect / error
   → browser parse / execute / render
   → follow-up fetch / local state / interaction

统一分析模型：

::

   behavior
   → locate runtime
   → trace path
   → mark boundary crossings
   → identify state owner
   → identify failure and recovery owner

概念辨析
--------

* **Browser 与 Frontend Framework**：Browser 是真实运行环境，framework 只是其上的 UI/路由/状态抽象。
* **Server 与 Backend API**：Server 不只返回 JSON，还承担 HTML rendering、身份、权限、数据访问、缓存和错误恢复。
* **HTTP 与函数调用**：函数调用可共享进程内对象，HTTP 只能通过协议字段和序列化数据跨边界协作。
* **Web Platform 与 Framework**：平台定义底层能力和安全语义，framework 组合并包装这些能力，不能取消平台边界。
* **State Copy 与 Source of Truth**：浏览器、缓存和服务端可以同时持有副本，最终事实必须明确由哪个边界拥有。

本章结论
--------

现代 Web 的最小心智模型是 ``Path → Boundary → State → Failure``。遇到任何框架、缓存、登录、渲染或部署问题，先问“代码在哪里运行、状态由谁拥有、跨了什么边界、谁负责恢复”，再进入具体技术名词。