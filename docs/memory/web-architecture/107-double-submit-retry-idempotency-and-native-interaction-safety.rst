Double Submit, Retry, Idempotency, and Native Interaction Safety
================================================================

核心知识点
----------

* Double submit 不是单纯“用户点了两次”，而是同一业务意图可能通过重复点击、回车、刷新、后退重提、网络超时后的重试、代理重试或并发 action 多次进入服务器。
* Pending state 只能减少当前 document 内的 accidental re-entry。禁用提交按钮、显示处理中、锁定关键交互能改善体验，但不能证明服务器只执行一次。
* 高风险 mutation 需要服务器幂等。idempotency key 用稳定标识把多次 HTTP 请求折叠为同一业务意图；服务器应校验 key、用户和输入摘要，并返回既有结果或处理中状态。
* 幂等检查必须和业务写入处在原子边界内，通常需要事务、唯一索引或等价 compare-and-set；“先查再插”如果没有数据库约束仍会在并发下重复执行。
* Retry 必须区分安全重试和危险 replay。客户端超时只说明响应未知，不代表服务器没有完成写入；非幂等 POST 在未知状态下不能盲目自动重试。
* Redirect-After-Post 把成功后的刷新、返回和分享转到 GET 结果页；浏览器 UI、server action、数据库约束、幂等记录和缓存刷新需要共同闭合写入安全路径。

关键路径
--------

``User submits intent → pending UI blocks local re-entry → POST with idempotency key → Server authenticates + validates key/input → Atomic lookup/create → Transactional mutation → Persist key→result mapping → 303 stable result URL → Duplicate/retry returns same result``

遇到“超时后不知道是否下单成功”时，正确恢复是用 idempotency key 或业务 attempt id 查询已知结果，而不是生成新意图直接再 POST 一次。

概念辨析
--------

* **Pending lock vs idempotency**：前者是浏览器交互保护，后者是服务器业务安全保证。
* **HTTP idempotent method vs business idempotency**：POST 默认不是幂等；应用可以通过 key 和唯一约束让特定 POST 意图具备幂等结果。
* **Retry vs replay**：retry 是在已定义安全条件下再次尝试；replay 可能重复执行已经成功但响应丢失的 mutation。
* **Request id vs idempotency key**：request id 用于追踪一次网络处理；idempotency key 表示可跨多次请求保持不变的业务意图。
* **Client cancel vs server cancel**：浏览器 abort 可能只停止等待，服务器写入仍可能继续并最终提交。

本章结论
--------

写入安全必须以“同一用户意图可能产生多次请求”为默认前提。UI pending 降低误操作，idempotency key 与数据库原子约束防止重复业务结果，redirect-after-post 和可查询结果状态负责把不确定网络恢复成可解释用户状态。