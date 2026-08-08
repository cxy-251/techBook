第097章：Hydration, Partial Hydration, Islands, and Client Activation
=====================================================================

核心知识点
----------

* Hydration 发生在浏览器已经拥有服务器/构建阶段生成的 HTML 之后：客户端 JavaScript 再把状态、事件处理器和框架 runtime 连接到现有 DOM。
* “内容可见”和“区域可交互”是两个不同阶段；SSR/SSG 可以先完成前者，hydration/activation 才完成后者。
* Hydration 成本包括 JavaScript 下载、解析、编译、执行、组件树恢复、状态反序列化、事件绑定和首轮 effect。
* Full hydration 把大范围组件树纳入客户端 runtime，心智模型统一，但会扩大 bundle、主线程执行、mismatch 和长期内存成本。
* Partial hydration 只激活确实需要交互的区域，让纯展示内容继续停留在 HTML 层。
* Islands architecture 把交互看成页面中的局部“岛”：静态主体由 server/build 交付，每个 island 独立拥有客户端代码与激活时机。
* Hydration mismatch 表明 server snapshot 与 client first render 漂移，常见来源包括时间、随机数、locale、用户状态、数据版本和浏览器专属条件。
* Client activation 应按用户任务调度：首屏关键按钮优先，低优先级轮播、评论、客服等可按 visibility、idle 或明确用户意图延后。

关键路径
--------

::

   Server / Build
     → HTML + CSS + Initial Data + Script Hints
     → Browser Parse / Paint
     → Content Visible
     → Download Client Chunks
     → Execute Runtime
     → Reconcile Existing DOM
     → Restore State / Bind Events
     → Region Interactive

   Partial / Islands:
     Static HTML
       ├─ Critical Island → activate early
       ├─ Visible Island → activate on viewport
       └─ Low-Priority Island → idle / user intent

* 排查“按钮看得见但点不动”时，依次确认 chunk 是否到达、主线程是否被 long task 占用、目标 island 是否已激活、handler 是否绑定、初始化状态是否成功恢复。
* 对关键交互保留原生 link/form、明确 disabled/pending 或其它降级路径，可降低激活窗口造成的不可用感。

概念辨析
--------

* **Hydration ≠ HTML rendering**：HTML 已经存在；hydration 的目标是让客户端 runtime 接管并持续更新它。
* **Hydration ≠ 只绑定事件**：还包含组件关系、状态恢复、运行时调度、effect 和首轮输出一致性。
* **Partial hydration ≠ code splitting**：code splitting 只拆文件；partial hydration 进一步决定哪些区域根本不进入客户端运行时。
* **Islands ≠ 多个 iframe**：island 仍处于同一 document 中，只是客户端执行责任被局部化。
* **Visible ≠ interactive**：页面可以已经 FCP/LCP，却仍未完成关键区域 activation。

本章结论
--------

Hydration 架构决定服务器 HTML 何时、以多大范围被浏览器 runtime 接管。交互密度低的页面应尽量缩小客户端边界，把 JavaScript 和激活时机与真实用户意图对齐；无论 full、partial 还是 islands，都必须保证 server/client 初始状态一致，并为未激活、激活失败和低端设备提供可解释的恢复路径。
