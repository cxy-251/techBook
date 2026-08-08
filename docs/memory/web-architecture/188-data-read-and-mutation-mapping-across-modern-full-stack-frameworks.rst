第188章：Data Read and Mutation Mapping Across Modern Full-Stack Frameworks
============================================================================

核心知识点
----------

* Framework data model 的稳定问题是四个：读取由什么触发、在哪个 runtime 执行、结果以什么副本存在、写入后由谁推动副本刷新。
* Route params、server render、client query mount、prefetch 与 mutation revalidation 都可以触发数据读取；相同业务对象可能因此拥有多份读取副本。
* Loader-based model 把读取绑定 navigation，适合把 route params、redirect、error boundary 与初始数据快照统一管理。
* Loader 应保持读语义；写入进入 action。Action 完成后相关 loader revalidation 才能让 route snapshot 回到远端事实。
* Server Component model 把读取靠近服务端 UI tree，能直接访问 server-only 数据并减少 client bundle，但必须继续执行 auth、tenant、DTO 裁剪与缓存键审查。
* Server Component 的结果跨 RSC/serialization boundary 进入客户端时，只应传递必要、可序列化、可公开给当前用户的数据。
* Query-cache model 把 server state 明确建模为 browser 中的远端副本。Query key、staleTime、focus/reconnect、retry 与 invalidation 共同决定 UI freshness。
* Route snapshot 与 client query cache 可以并存，但必须明确谁负责初始读取、谁负责长期刷新、mutation 后各自如何失效。
* Action/server function 将用户提交重新送回 trusted server boundary；隐藏 endpoint 外形不意味着 validation、auth、transaction、idempotency 和 error semantics 消失。
* Framework default 会编码一致性权衡：自动 cache、默认 stale、prefetch、静态生成、revalidation 与 mutation invalidation 都是架构选择。
* Cache key 必须覆盖 tenant、user/permission scope、route params、locale、filter 等所有影响结果的上下文。
* 最终所有框架数据 API 都必须收敛到 ownership model：source of truth 在哪、缓存副本在哪、谁能写、谁失效、失败时谁恢复。

关键路径
--------

读取：

::

   URL / component / query key / prefetch
   → framework data trigger
   → server/edge/browser runtime
   → database or HTTP authority
   → route snapshot / render snapshot / query cache
   → UI

写入与刷新：

::

   user form/action
   → trusted mutation boundary
   → validation + auth
   → transaction / durable write
   → invalidate route/data/query copies
   → re-read authoritative state
   → reconcile UI

概念辨析
--------

* **Loader Data 与 Query Cache**：loader data 常属于一次 route/navigation 快照，query cache 更适合长期观察和后台刷新远端状态。
* **Server Component Read 与 Authorization**：运行在服务端只提供可信执行位置，不自动保证资源权限正确。
* **Server Function 与 Local Function**：调用语法可能像本地函数，实际仍跨 client/server、serialization、auth 和网络失败边界。
* **Prefetch 与 Fresh Data**：预取只是提前创建副本，最终使用时仍要符合 freshness 和权限条件。
* **Mutation Result 与 Source of Truth**：mutation 返回值可以帮助 UI 更新，但最终一致性仍由持久状态和后续权威读取确认。

本章结论
--------

现代框架的数据层应按 ``Trigger → Runtime → Authority → Cached Snapshot → Mutation → Invalidation/Revalidation`` 阅读。API 形态可以不同，但数据真相、缓存副本、写权限和刷新责任必须始终能够被明确指出。