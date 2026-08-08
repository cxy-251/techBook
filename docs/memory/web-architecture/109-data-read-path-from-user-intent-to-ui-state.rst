第109章：Data Read Path from User Intent to UI State
=====================================================

核心知识点
----------

* 数据读取的起点不是 ``fetch()``，而是用户意图：导航、筛选、搜索、分页、刷新、返回恢复都在回答“用户现在想看什么”。
* 一次完整读路径通常跨越 ``User Intent → URL/Route → Loader/Query → HTTP → Auth → Cache → Database/Service → Serialization → Client Cache → UI``。
* URL 适合承载需要刷新、分享、收藏和服务器直达恢复的读取条件；组件内临时草稿不应自动进入 URL。
* UI 展示的通常不是远端事实本身，而是某个时间点、某组条件、某个权限上下文下的本地表示或缓存快照。
* 读取状态至少要区分 initial loading、已有数据上的 refreshing、empty、error、stale；单一 ``isLoading`` 很容易掩盖真实路径。
* 读取结果必须带身份：用户、tenant、route params、query、locale、权限和分页条件中，凡是会改变返回结果的维度都属于数据身份。
* 取消与乱序是读路径正确性的一部分：用户意图变化后，旧请求即使成功，也不再自动拥有当前 UI 的提交资格。

关键路径
--------

``用户意图 → URL/交互状态 → 读取函数 → HTTP 请求 → 身份与权限检查 → Cache Lookup → Database/Service → 响应序列化 → Client Cache → UI Commit``

沿路径检查时，先确认当前 UI 在回答哪个用户问题，再确认读取参数是否完整；随后看请求运行在 browser、server 还是 edge，检查缓存命中与远端权威来源，最后确认响应是否仍属于当前 route 和当前用户意图。

首次进入页面时没有旧数据，页面需要结构化 fallback；筛选或后台刷新时已有旧快照，可以保留上下文并显式标记刷新；分页时应保留已加载内容，只给新增窗口表达 pending。

概念辨析
--------

* **Remote truth vs local representation**：数据库或服务拥有权威事实；HTML、JSON、query cache 和组件状态只是其本地表示。
* **URL state vs read result**：URL 描述“读什么”；响应和缓存描述“读到了什么”。
* **Loading vs empty**：loading 表示结果尚未确认；empty 表示服务器已经确认当前条件下没有结果。
* **HTTP cache vs query cache**：前者围绕请求/响应和缓存头；后者围绕业务数据 key、freshness、observer、refetch 与 invalidation。
* **Request success vs UI validity**：请求成功只说明拿到响应；还要确认权限、schema、cache key 和当前 navigation identity 都成立。

本章结论
--------

数据读取应被理解为一条从用户意图到 UI 快照的跨边界路径。稳定实现必须同时明确读取身份、可信来源、缓存归属、等待状态、取消/乱序规则和失败恢复；只有 ``fetch`` 成功，不能证明用户看到的是当前、正确且属于自己的数据。