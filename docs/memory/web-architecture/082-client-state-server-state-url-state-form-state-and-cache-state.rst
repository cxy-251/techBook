第082章：Client State, Server State, URL State, Form State, and Cache State
==========================================================================

核心知识点
----------

* UI 中的“状态”并不属于同一层：client state、server state、URL state、form state 和 cache state 的所有者、生命周期与恢复责任不同。
* Client state 表示当前界面的局部交互记忆，如展开、tab、modal、hover、拖拽等。
* Server state 的权威来源在服务器或数据库，浏览器中的数据只是带新鲜度和失败语义的本地副本。
* URL state 适合可分享、可刷新恢复、可后退前进、可被服务器和缓存识别的页面状态。
* Form state 表示用户正在编辑、尚未提交或等待校验的意图，应独立于已保存的服务器事实。
* Cache state 是派生副本，必须有 key、新鲜度、失效和刷新规则；cache 不是最终真相。

关键路径
--------

状态分类先问四个问题：

#. 权威值在哪里产生；
#. 刷新、分享链接、后退后是否应保留；
#. 多个副本冲突时谁负责收敛；
#. 失败后由谁恢复。

商品列表的典型路径：

``URL Query → Route Input → Server Query → Database Truth → Query Cache Copy → UI``

同时存在：

``Filter Panel Open → Client State``

``Address Draft → Form State → Validation → Submit → Server State``

``Mutation Success → Invalidate Cache → Refetch → Updated UI``

如果排序条件改变，应优先更新 URL，再让路由和 query key 驱动数据刷新；如果库存改变，应由远端事实和缓存失效更新界面，而不是长期保存在普通全局 store 中。

概念辨析
--------

* **Client state ≠ all browser memory**：浏览器内存中的值也可能只是 server state 或 cache state 的副本。
* **Server state ≠ global store**：远程数据需要 stale、retry、dedupe、invalidation 等语义，普通全局状态并不会自动提供这些能力。
* **URL state ≠ implementation detail**：它是浏览器、用户、服务器、CDN 和路由共享的公共状态边界。
* **Form state ≠ saved data**：用户正在输入的草稿是 pending intent，不能在每个按键时就当作远端事实。
* **Cache state ≠ truth**：缓存可以过期、被驱逐、命中旧版本或与权威源暂时不一致。

本章结论
--------

状态设计的第一原则是先确定所有者，再决定存放位置。把 URL、表单、远端事实和缓存副本都压进同一种状态容器，会直接制造刷新丢失、旧数据、重复提交和恢复困难。