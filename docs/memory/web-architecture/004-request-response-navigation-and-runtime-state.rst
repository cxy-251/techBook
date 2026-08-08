第004章：Request, Response, Navigation, and Runtime State
==========================================================

核心知识点
----------

* Request 是跨边界的“意图 + 上下文”对象，包含 URL、method、headers、cookies、body、credentials、cache mode、redirect mode 与发起者语义。
* 同一个 URL 因 request 类型不同而含义不同。地址栏进入通常是 navigation request，``fetch()`` 通常是 data request，Service Worker 拦截又会进入缓存与网络策略判断。
* Response 不只是返回数据，还携带 status、content type、cache-control、cookie、安全策略、redirect、stream 与 validation 结果，并会改变浏览器后续行为。
* HTML response 通常进入 document 构建；JSON response 进入当前 JavaScript runtime；redirect 改变后续 request path；stream 改变内容到达时间；asset response 进入资源加载与缓存。
* Navigation request 的核心结果是创建、替换或恢复 document；data request 的核心结果是在已有 document 内更新局部状态。
* Navigation 会改变 URL、history、document、scroll/focus、resource lifetime 与 JavaScript runtime；data request 通常保留当前 runtime，只改变 component/query/store 等局部状态。
* Runtime state 可以同时存在于 URL、DOM、component state、browser storage、cookie、server session、database、HTTP/CDN cache 与 query cache。
* 状态设计必须明确 owner。Owner 决定谁更新、谁失效、谁同步、谁恢复，以及出现冲突时哪个副本具有最终解释权。
* URL 适合可分享、可恢复的导航状态；component state 适合当前 document 的临时交互；cookie/session 适合身份上下文；database 适合权威持久状态；cache 只是可失效副本。
* 重复状态副本会产生 stale UI、重复提交、登录丢失、hydration mismatch、回退异常与跨标签页不一致。问题本质通常是 owner 和同步路径不清晰。
* Mutation 需要把 UI pending state、server validation、database transaction、response、cache invalidation 与最终 UI reconciliation 看成一条完整路径。

关键路径
--------

Navigation：

::

   user opens URL / follows link
   → navigation request
   → redirect/cache/server processing
   → HTML response
   → commit document
   → create/restore history + runtime
   → load resources
   → render and interact

Data mutation：

::

   user action
   → client pending state
   → data/mutation request
   → server auth + validation
   → database write
   → response
   → invalidate/refetch cache
   → reconcile URL / component / query state

概念辨析
--------

* **Navigation Request 与 Data Request**：前者主要改变 document 与运行环境，后者主要在当前 document 内更新数据。
* **Response Body 与 Response Semantics**：body 只是响应的一部分；status、header、redirect、cache 与 cookie 同样会改变系统状态。
* **URL State 与 Component State**：URL 适合可分享和 history 恢复的状态，component state 适合短生命周期交互状态。
* **Server Session 与 Database State**：session 保存请求身份/会话上下文，database 保存业务持久事实，生命周期和一致性责任不同。
* **Optimistic State 与 Source of Truth**：乐观 UI 是暂时预测，server/database 失败时必须回滚或重新同步。

本章结论
--------

一次 Web 交互应按 ``Intent → Request → Response → Navigation/Local Update → State Reconciliation`` 阅读。稳定架构的关键不是减少状态，而是明确每个状态副本的 owner、生命周期和同步路径，并在跨边界失败时能恢复到权威事实。