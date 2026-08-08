第058章：URL, History, Navigation, Location, and Browser State
==============================================================

核心知识点
----------

* URL 是浏览器、服务器、缓存、框架 router 与用户之间共享的公开状态边界。适合承载可分享、可收藏、可刷新恢复、会影响数据请求与页面语义的状态。
* ``URL`` / ``URLSearchParams`` 用结构化方式处理 ``origin``、``pathname``、``search``、``hash``，优先于手工字符串拼接。
* ``window.location`` 连接当前 ``Document`` 与浏览器级导航。``assign``、直接赋值、``replace``、``reload`` 都可能创建或重新加载文档，属于 document 生命周期边界。
* History API 允许在同一 Document 内更新 URL 与 session history。``pushState`` 创建新 entry，``replaceState`` 修正当前 entry，``popstate`` 处理返回/前进后的状态恢复。
* ``history.state`` 是某个 session history entry 的附加状态，不能替代 URL 的主要页面语义；刷新、复制链接和新标签页仍应能仅凭 URL 恢复主要视图。
* SPA navigation 的本质是同一 Document 内同步 URL、history entry、router state、数据请求与视图状态；Document navigation 则重新进入 HTML、网络、缓存和页面启动链。
* URL 会进入访问日志、缓存 key、分析系统、分享链路和 referrer；敏感 token、私密草稿和不应公开的用户状态不应长期放在 URL 中。

关键路径
--------

筛选状态进入 URL：

::

   User changes filter
     → URLSearchParams
     → pushState / replaceState
     → session history entry
     → router state
     → data request / cache key
     → UI

浏览器返回：

::

   Back / Forward
     → history traversal
     → active entry changes
     → popstate / router notification
     → restore URL-derived state
     → restore data / scroll / focus

跨文档导航：

::

   Current Document
     → location / link / form / redirect
     → navigation
     → response commit
     → new Document
     → new runtime state

状态放置判断：

::

   Need share / refresh / server rendering?
     → URL candidate
   Entry-local ephemeral state?
     → history.state candidate
   Current component-only transient state?
     → memory state
   Sensitive or durable identity state?
     → server/session/storage boundary

概念辨析
--------

* ``URL`` 与 ``Location``：URL 是普通结构化地址对象；Location 代表当前文档地址并带导航副作用。
* ``pushState`` 与 ``replaceState``：前者表示新的用户历史里程碑，后者用于规范化或修正当前 entry。
* ``history.state`` 与 URL：前者只属于当前浏览器 session history；后者是可分享的公共接口，应承担主要恢复语义。
* SPA navigation 与 Document navigation：前者通常复用当前 Document；后者创建新 Document 并重新经过加载链。
* ``hash`` 与 query：fragment 通常不发送给服务器，适合文档内位置或局部客户端状态；query 会参与请求、缓存和服务端路由。
* 路由状态与组件状态：路由状态决定可恢复页面身份，组件状态只服务当前运行时局部交互。

本章结论
--------

先判断状态是否应成为 URL，再判断当前动作是否创建新 Document，最后决定是否创建新的 history entry。现代路由的稳定模型是 ``URL ↔ History Entry ↔ Router State ↔ Data State ↔ UI`` 保持同一语义；任何一层脱节都会表现为刷新丢状态、返回错乱、深链接 404、缓存异常或分享链接不可恢复。