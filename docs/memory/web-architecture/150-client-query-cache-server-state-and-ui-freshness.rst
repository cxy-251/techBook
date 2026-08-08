第150章：Client Query Cache, Server State, and UI Freshness
===========================================================

核心知识点
----------

* Client query cache 保存的是 server state 的本地快照；订单、库存、评论、用户资料和权限事实仍由 server/database 拥有。
* Query cache 与 component state 责任不同。前者管理远端读取结果、stale/fetching/error/mutation 状态，后者管理输入、modal、selection、scroll 等本地交互状态。
* Stale data 可以维持 UI 连续性，但必须让产品语义承认“正在确认”。关键业务操作不能把旧副本当作最终事实。
* Query key 是客户端缓存身份。任何会改变 query result 的 tenant、resource id、filter、page、sort、locale、permission/auth scope 都需要进入 key 或被服务端稳定默认。
* Key 过粗会串数据，尤其多租户和权限场景；key 过碎会造成重复请求和低命中率。Secret/token 不应直接进入可见 cache key。
* Background refetch 把 responsiveness 与 freshness 分离：先显示已有数据，再异步更新；失败时可保留旧数据并明确标记“更新失败”。
* Window focus、network reconnect、route remount、polling、manual invalidation 与 subscription 都可以成为重新获取触发器，频率应匹配业务 freshness 目标。
* Optimistic update 暂时让客户端预测写入结果，但 authority 没有真正转移。最终必须通过 server echo、refetch、rollback 或 version reconciliation 回到服务端事实。
* Mutation 完成后要更新所有受影响读模型：详情、列表、统计、搜索、分页和相关 route cache；只改一个 query 会制造 split-brain UI。
* UI freshness 是产品决策。聊天、库存、权限、金融数据比文章详情、静态资料需要更窄 stale 窗口；刷新频率不应全局统一。
* Route context、query key 与 mutation scope 必须协同。URL 参数、tenant 切换或登录身份变化时，旧 query cache 不能继续被当成当前上下文数据。

关键路径
--------

Client query 读取：

::

   route/context
   → derive query key
   → read cached snapshot
   → render cached/loading/stale state
   → background fetch server
   → server reads authoritative data
   → update cache snapshot
   → UI reconciles

Optimistic mutation：

::

   user action
   → cancel/isolate conflicting reads
   → optimistic cache patch
   → send mutation
   → server commit or reject
   → reconcile server result
   → invalidate/refetch affected queries
   → rollback only this mutation if needed

概念辨析
--------

* **Server State 与 Client State**：server state 由远端系统拥有，client state 由当前页面交互拥有。
* **Cached 与 Fresh**：cached 只表示有副本，fresh 表示副本仍在允许的新鲜窗口内。
* **Stale 与 Wrong**：stale 可以在明确语义下继续展示；wrong 是把已失去可信度的数据当最终事实。
* **Optimistic Update 与 Durable Write**：前者是 UI 预测，后者是服务端确认的持久事实。
* **Query Key 与 Route Key**：query key 标识远端数据副本，route state 标识页面导航上下文；二者通常需要共享同一资源/tenant 维度。

本章结论
--------

客户端数据层应按 ``Server Authority → Query Identity → Cached Snapshot → Freshness → Refetch/Mutation → Reconciliation`` 设计。Query cache 的价值是让页面快速且连续地工作，同时必须始终能够回到服务端事实，并在上下文变化和写入完成后精确收敛。