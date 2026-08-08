第175章：Logs, Metrics, Traces, Error Tracking, and Distributed Request Evidence
===============================================================================

核心知识点
----------

* Logs、metrics、traces、error tracking 观察的是不同维度：log 记录离散事件，metric 描述聚合趋势，trace 连接跨边界因果路径，error tracking 绑定运行时异常与 release/context。
* 单一信号很难解释全栈故障。稳定排查通常先用 metrics 固定影响范围，再用 trace 还原请求路径，再用 logs/error events 补充细节。
* Structured log 应携带稳定字段：event、request id、trace id、route、status、release、region、tenant/user scope、dependency、duration、retryability 和 cache state。
* Log field 应归属于真实 runtime：browser 记录用户环境和前端异常，edge 记录 region/cache/routing，server 记录 handler/auth/business state，database 记录 query/transaction 事实。
* Metrics 适合观察 latency、error rate、throughput、cache hit、queue depth、CPU/memory、DB pool 和 Core Web Vitals；延迟应关注分位数和分布，而不是只看平均值。
* Metric label 必须控制基数。route、status class、region、release 等适合聚合；user id、session id、订单号、完整 URL query 不适合作为高基数标签。
* Trace 用 trace id / span id / parent relation 把 browser、CDN/edge、server、database、cache、third party 和 background job 连成同一因果图。
* Correlation ID 是跨系统拼接证据的关键。Request id、trace id、session hash、release id 让不同日志和平台事件可以被归并到同一次用户动作。
* Error tracking 应记录 stack、source map、release、route、browser/device、region、breadcrumb 和用户上下文，同时避免收集 secret 与敏感表单内容。
* Observability 必须尊重 privacy/security boundary：token、cookie、支付数据、密码、个人敏感字段和 secret 应脱敏、过滤或禁止采集。
* 采样策略决定 trace/error evidence 的可见范围；高流量系统需要在成本、正常请求覆盖和异常保留之间权衡。
* 可观测性的目标不是“收集更多数据”，而是让每次事故都能回答：发生了什么、影响多大、哪条路径、哪个版本、哪个边界最先异常。

关键路径
--------

事故证据链：

::

   user-visible symptom
   → metrics: impact/time window
   → trace: cross-boundary path
   → logs: local event details
   → error tracking: stack/release/context
   → correlation ids join signals
   → root cause + recovery

Trace 传播：

::

   browser/edge request
   → trace context
   → server span
   → database/cache/external spans
   → background work
   → shared trace/release identity

概念辨析
--------

* **Log 与 Metric**：log 解释单个事件，metric 解释群体规模和趋势。
* **Metric 与 Trace**：metric 指出“哪里整体变差”，trace 解释“某次请求经过哪里变慢”。
* **Request ID 与 Trace ID**：request id 常标识单次入口请求，trace id 可跨多个服务/span 延续更长因果路径。
* **Error Tracking 与 Logging**：error tracking 专注异常聚合、stack 和 release 关联；日志覆盖更广泛业务事件。
* **Observability 与 Data Collection**：有价值的可观测性要求上下文可关联且受隐私控制，不等于无限收集原始数据。

本章结论
--------

分布式排障应按 ``Metrics Scope → Trace Path → Log Detail → Error/Release Context → Correlation`` 建立证据。Logs、metrics 和 traces 不是互相替代的工具，而是从规模、路径和事件三个角度共同还原一次真实用户故障。