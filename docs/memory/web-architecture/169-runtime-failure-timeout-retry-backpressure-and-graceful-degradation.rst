第169章：Runtime Failure, Timeout, Retry, Backpressure, and Graceful Degradation
================================================================================

核心知识点
----------

* Web runtime failure 可能发生在业务 handler 之前：DNS/TLS、CDN routing、edge middleware、serverless bootstrap、依赖加载、环境变量和平台限流都可能提前失败。
* Timeout 是架构边界。Browser、CDN/proxy、edge、serverless/server、database、third party 都有各自等待预算，必须形成从外到内的整体时间预算。
* 核心能力与非核心能力要分配不同 timeout。商品主体、库存和交易确认属于核心路径，推荐、分析、图片增强等应拥有更短预算和可降级结果。
* Retry 既能恢复瞬时故障，也能放大雪崩。Browser、CDN、queue、platform、driver 和 SDK 多层重试叠加时，一个用户动作可能产生大量下游请求。
* 写操作在重试前必须建立 idempotency boundary，例如 idempotency key、唯一约束、事务状态机或去重记录；不能只靠客户端“不要重复点”。
* Retry 需要有限次数、指数退避、jitter、可重试错误分类和总预算；认证失败、业务校验失败等永久错误不应机械重试。
* Backpressure 用来保护系统免受无界工作量：当下游慢、连接池耗尽、客户端读取慢或 stream 消费滞后时，应限流、排队、暂停生产或主动降级。
* Graceful degradation 的目标是保留核心用户价值。非关键推荐、分析、头像增强、实时组件失败时，页面主体和关键操作仍应可用。
* 降级不是吞掉错误。系统需要明确哪些区域进入 fallback、哪些状态陈旧、哪些操作被禁用，并保留观测证据。
* Partial failure 是现代 Web 的常态；可靠性目标是限制故障范围、控制工作量、保持数据安全和提供可恢复用户路径。
* Observability 必须携带 runtime context：request id、route、tenant/user scope、region、release、cache state、retry attempt、timeout budget 和 degradation decision。
* 故障诊断要从“请求最早出现在哪一层日志”开始，避免把 platform/runtime failure 错判成业务代码异常。

关键路径
--------

跨 runtime 故障定位：

::

   browser/network evidence
   → CDN/cache/routing evidence
   → edge runtime evidence
   → serverless/server bootstrap + handler
   → database/upstream evidence
   → identify first failing boundary

受控恢复：

::

   assign timeout budgets
   → classify core vs optional dependency
   → retry only transient + idempotent operations
   → apply backoff/jitter
   → enforce concurrency/backpressure
   → degrade optional features
   → preserve request/release/runtime context

概念辨析
--------

* **Timeout 与 Failure**：timeout 是某层主动停止等待的策略，failure 是更广义的不可成功状态。
* **Retry 与 Recovery**：retry 是恢复手段之一；没有幂等和预算时，它可能成为故障放大器。
* **Backpressure 与 Rate Limit**：backpressure 根据下游消费能力调节生产，rate limit 通常限制入口请求速率；二者都用于保护容量。
* **Graceful Degradation 与 Silent Failure**：降级明确保留核心价值并暴露状态，静默失败让用户误以为系统仍完整正确。
* **Partial Failure 与 Total Outage**：多运行时系统中局部依赖失败更常见，架构应避免局部失败扩散成整页/整站不可用。

本章结论
--------

可靠 Web runtime 应按 ``Failure Location → Timeout Budget → Retry Safety → Backpressure → Degradation → Observability`` 设计。系统不应假设所有依赖始终成功，而应让局部失败被限制、可解释、可恢复，同时保证核心用户路径和数据一致性不被重试与过载破坏。