Optimistic UI, Pending State, Rollback, and Conflict Resolution
==============================================================

核心知识点
----------

* Pending state 表示“系统已接收用户意图，服务端结果尚未确认”；Optimistic UI 则进一步预测成功，把临时结果提前投影到界面。
* 乐观状态属于浏览器或客户端缓存，不是 durable fact；服务端确认后的 canonical result 才能结束预测阶段。
* Optimistic UI 适合失败率低、影响小、可逆、预测准确且服务端能返回最终资源版本的写入，例如点赞、收藏、低风险状态切换。
* 支付、库存扣减、权限变更等高风险动作更适合显式 pending/confirmed 模型，因为预测错误的业务成本过高。
* 乐观更新必须保存 rollback material：旧字段、反向 patch、mutation id、资源 id、影响的 query key、列表位置与派生计数。
* 回滚不是静默改回数据；UI 还要解释失败原因，并保留与该失败无关的后续用户输入。
* 并发协作下应携带 ``version``、ETag 或修订号发现过期假设；冲突需要重新读取、自动合并或让用户理解差异后重新提交。

关键路径
--------

``User Action`` → 建立 mutation identity → UI 进入 pending → 可选应用 optimistic patch → 发出写入并携带 expected version → server validation / auth / transaction → 返回 canonical resource 或 conflict/error → 成功时用 server result reconcile → 失败时按 operation 精确 rollback → 冲突时拉取当前事实并决定自动合并或人工选择 → 重新校准相关 cache。

列表中的并发 optimistic mutation 不应依赖整页旧快照覆盖恢复，否则一个失败操作可能擦掉之后已经发生的其他操作。更稳的设计是为每个 mutation 保存局部 patch 与 operation id，只撤销自己触达的投影。

概念辨析
--------

* **pending vs optimistic**：pending 只表达处理中；optimistic 已经把预测结果展示给用户。
* **optimistic state vs server state**：前者是临时本地投影，后者是可信远端事实。
* **rollback vs refetch**：rollback 恢复本次预测影响；refetch 从权威源重新校准，两者可以组合。
* **conflict vs ordinary failure**：普通失败表示操作未成立；冲突表示请求基于的旧事实已经变化，需要处理新旧版本关系。
* **whole-cache snapshot vs operation patch**：前者实现简单但并发下容易误覆盖；后者更适合多 mutation 同时进行。

本章结论
--------

Optimistic UI 的价值来自把等待移出用户主观路径，它的可靠性来自明确的临时身份、可逆 patch、服务端版本和 reconciliation。没有 rollback 与 conflict path 的乐观更新，只是在客户端提前宣告一个尚未被系统证明的事实。