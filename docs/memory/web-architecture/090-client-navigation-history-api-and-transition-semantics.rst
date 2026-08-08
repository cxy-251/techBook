第090章：Client Navigation, History API, and Transition Semantics
================================================================

核心知识点
----------

* Client navigation 在当前 document 中完成“换页”，因此旧 JavaScript runtime、内存缓存、共享 layout 和未完成请求可能继续存在，应用必须主动管理失效与恢复。
* History API 只负责 session history：``pushState`` 创建 entry，``replaceState`` 修改当前 entry，``popstate`` 表示 Back/Forward 导致 entry 切换；它不会自动完成数据加载和 UI 更新。
* 一次完整 navigation transition 应至少包含 ``start → pending → commit → recovery`` 四阶段。
* URL、history entry、route match、数据版本、pending UI、scroll、focus 和 error boundary 必须属于同一导航语义。
* 连续点击、快速返回和慢请求会产生 race；新导航启动后，旧请求应取消或失去 UI commit 资格。
* 客户端导航仍必须保留浏览器用户预期：链接可复制、刷新可恢复、返回/前进正确、错误有反馈、滚动和焦点合理。

关键路径
--------

``User Intent → Client Router → History Entry → Route Match → Data Request → Pending UI → Commit → Scroll/Focus Recovery``

* 用户从列表 ``/products?page=3`` 点击 ``/products/42``，router 决定是否接管同源导航。
* start 阶段固定目标 URL、navigation id 与 route match；pending 阶段发数据请求并显示等待反馈。
* 若目标数据成功且 navigation id 仍是最新，commit 阶段同步当前 route、缓存、UI、标题和 history 语义。
* 用户在 pending 中再次导航时，旧 ``AbortController`` 可取消请求；即使无法真正取消 server work，旧结果也必须被标记为过期。
* ``popstate`` 到来时，以目标 history entry 的 URL 重新匹配 route，并恢复与该 entry 对应的数据、scroll 与 focus。
* recovery 处理网络失败、权限变化、错误边界、重试和返回旧状态，不能把失败留在“URL 已变、UI 未变”的半提交状态。

概念辨析
--------

* **Client navigation vs document navigation**：前者复用当前 document；后者由浏览器创建新的 document 和脚本环境。
* **History API vs router**：History 管 entry；router 解释 entry 并协调 route、data、UI 和恢复。
* **pushState vs replaceState**：前者创建用户可返回的新位置；后者修正当前导航位置。
* **请求成功 vs navigation commit**：数据返回只证明请求成功，还要确认结果属于当前最新 navigation。
* **Abort vs stale-result rejection**：abort 减少资源浪费；结果资格检查保证旧结果即使返回也不能覆盖当前页面。

本章结论
--------

客户端导航不是“改 URL 再换组件”，而是一笔跨 history、route、data、UI 与恢复状态的事务。稳定实现必须显式管理 transition 阶段、请求取消、race、Back/Forward、scroll/focus 和 error recovery，并保证任何时刻用户看到的 URL 与当前 route/data/UI 处在同一版本。
