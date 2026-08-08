第113章：Query Cache, Server State, and Client-Side Data Ownership
=================================================================

核心知识点
----------

* Server state 的权威来源在服务器、数据库或远端服务；浏览器中的 query cache 只是某个时间点、某组条件下的本地快照。
* Query cache 的核心职责是让远端快照可复用、可观察、可刷新、可失效，并把 ``fresh / stale / fetching / error`` 等生命周期显式交给 UI。
* Cache key 定义数据身份。tenant、viewer、filter、sort、page、locale、权限版本等凡是会改变返回结果的维度，都应进入 key 或上游 route identity。
* Freshness 不是缓存命中与否的二元值。已有快照可以继续展示，同时后台 revalidate；UI 应区分“有旧数据正在刷新”和“完全没有数据正在首次加载”。
* Query cache 不拥有业务事实。窗口重新聚焦、网络恢复、多设备写入、后台任务或 mutation 都可能让本地快照变旧。
* Mutation 后必须明确同步策略：直接更新确定快照、invalidate 相关 query、重新获取，或乐观更新后用服务器结果校正。
* Client state 与 server state 的所有权不同：modal、draft、hover 等由浏览器决定；任务状态、库存、权限、支付结果等必须以远端确认结果为准。
* 缓存可见范围要和安全上下文一致；tenant 或 viewer 切换时，旧 query 不得短暂冒充新上下文的数据。

关键路径
--------

``URL/Filter → Query Key → Query Function → HTTP → Server/Auth → Database → Serialized Snapshot → Query Cache → UI``

随后进入生命周期：

``Fresh → Stale → Background Refetch → New Snapshot / Refresh Error → UI Reconcile``

设计 query key 时先列出会改变远端结果的所有输入；设计 freshness 时评估数据变化频率、旧数据误导风险、刷新成本和降级价值；mutation 完成后再沿资源关系确定失效范围。

概念辨析
--------

* **Server state vs client state**：前者远端拥有、客户端观察；后者浏览器可直接决定。
* **Fresh vs cached**：cached 只说明本地有副本；fresh 才说明该副本在当前策略内无需立即重新验证。
* **Stale vs wrong**：stale 表示可能需要验证，不一定错误；wrong 表示身份、权限或语义已经不匹配。
* **Query key vs request URL**：URL 只是数据身份的一部分；身份、tenant、locale 和权限也可能改变响应。
* **Invalidation vs deletion**：invalidation 表示快照需要重新验证；删除缓存只是其中一种更激进策略。

本章结论
--------

Query cache 是浏览器观察 server state 的协调层，不是新的权威数据库。稳定实现必须让 cache key 精确表达数据身份，让 freshness 与业务风险匹配，并在 navigation、身份变化和 mutation 后明确重新验证或失效规则，避免旧快照被当作当前事实。