第110章：Loader, Fetch, Server Component Data Access, and Query Function
======================================================================

核心知识点
----------

* ``loader``、``fetch()``、Server Component data access 和 query function 都服务于读路径，但它们处在不同责任层。
* Loader 把数据读取绑定到 route/navigation，适合由 URL、route params、权限和页面进入条件决定的数据，并能自然接入 redirect、route error 与 revalidation。
* ``fetch()`` 是请求原语，只负责构造请求、接收响应、处理 body/stream、credentials、cache、abort 等；它不自动提供业务 cache key、retry、stale、invalidation 或 UI ownership。
* Server Component data access 把读取放到可信 runtime，可直接访问数据库、secret、内部服务和完整权限规则，同时只把可序列化、已裁剪的数据暴露给浏览器。
* Query function 把远端读取封装成 client query cache 可管理的单元，通常围绕稳定 query key、Promise 结果、错误、重试、新鲜度和失效工作。
* 选择读取入口时先问四件事：代码在哪里执行、数据由谁拥有、缓存由谁维护、失败由谁恢复。
* 同一页面可以组合多种入口：route 主数据由 loader/server 读取，低优先级交互数据由 query function 读取，底层 HTTP 仍可能由 ``fetch()`` 完成。

关键路径
--------

``URL/Navigation → Route Loader 或 Server Read → Auth/Data Source → Serialized Result → Route UI``

或：

``UI Intent → Query Key → Query Function → fetch() → HTTP/API → Server → Client Query Cache → UI``

Loader 适合把“进入这个地址就必须知道”的数据前移；Server Component 适合把 secret、数据库和数据裁剪留在 server；query cache 适合让浏览器长期观察远端快照。无论封装如何，最终都必须追踪 request、auth、cache、serialization 和 recovery。

概念辨析
--------

* **Loader vs component fetch**：前者属于导航边界，后者通常晚到组件运行阶段；两者的 loading、error 与 abort 粒度不同。
* **Fetch vs query function**：``fetch`` 是网络原语；query function 是远端状态读取契约，常被 cache/retry/refetch 系统调用。
* **Server Component read vs browser API call**：前者可接触可信资源并减少客户端暴露；后者必须通过公开服务器接口访问远端事实。
* **Server cache vs client query cache**：server cache 复用服务端计算/响应；client query cache 保存浏览器观察到的远端快照。
* **Framework abstraction vs runtime boundary**：框架名称不能替代执行位置判断；必须确认代码究竟在 browser、server、edge 还是 build time 运行。

本章结论
--------

不同读取抽象的本质是重新分配 route、network、server、cache 与 UI 的责任。正确选择不是寻找“最现代”的 API，而是让读取发生在最合适的 runtime，并让数据身份、权限、缓存、取消、错误和恢复都落在清晰边界上。