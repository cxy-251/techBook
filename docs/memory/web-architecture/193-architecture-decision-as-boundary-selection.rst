第193章：Architecture Decision as Boundary Selection
=====================================================

核心知识点
----------

* Web 架构决策本质是边界选择：一段工作应由 browser、server、edge、build、cache、database、third-party 还是 deployment runtime 承担。
* 决策前先从真实用户路径出发，标出请求、状态和响应经过的边界，再讨论框架、渲染模式或平台。
* 每个边界都要同时评估 ``capability / cost / failure shape``。只比较性能或开发速度，会遗漏权限、缓存污染、一致性和恢复成本。
* Browser 擅长交互、局部状态和即时反馈；代价在用户设备、网络与 JavaScript，失败表现为卡顿、请求取消和状态丢失。
* Server 提供 trusted execution、secret、database、权限和第三方调用；代价在计算、连接、冷启动和运维，失败通常表现为 timeout、5xx 或状态未知。
* Edge 擅长早期路由、轻量鉴权、header 改写、实验和 cache policy；受 runtime API、依赖、区域日志与数据距离约束。
* Cache 通过复用副本换取延迟和成本收益，也引入 freshness、key、segmentation、invalidation 与跨用户泄漏风险。
* Database 拥有持久事实、约束和事务；third-party 拥有外部事实；deployment boundary 决定代码实际在哪里运行、如何发布、观测和回滚。
* 把工作从一个边界迁移到另一个边界，会同时改变输入来源、状态所有权、缓存范围、错误恢复和可观察证据，不能只看“代码能否运行”。
* 高质量决策必须显式列约束：SEO、数据新鲜度、权限、用户设备、网络、成本、团队能力、平台限制、合规、性能与可维护性。
* Framework default 也是架构决策。默认 rendering、cache、prefetch、runtime、bundle split 与 deployment behavior 都必须被审查。
* Tradeoff matrix 比技术偏好可靠。评估收益、代价、风险、可逆性、迁移成本、调试难度和团队熟悉度，并留下证据与逃生口。

关键路径
--------

架构决策：

::

   real user path
   → locate browser/server/edge/build/cache/database boundaries
   → list state owner and request context
   → list explicit constraints
   → compare capability/cost/failure shape
   → choose boundary placement
   → define metrics/observability
   → define rollback and migration escape route

工作迁移：

::

   current boundary
   → identify inputs/state/dependencies
   → move compute/storage/cache responsibility
   → redesign security + freshness + failure handling
   → verify production evidence
   → retain rollback path

概念辨析
--------

* **Architecture Decision 与 Technology Selection**：技术选型只是实现动作，架构决策先决定责任放在哪个系统边界。
* **Capability 与 Convenience**：某 runtime 能做某事不代表适合做；还要考虑成本、失败和数据距离。
* **Performance Gain 与 Boundary Shift**：把工作前移到 CDN/edge/server 会改变一致性、权限和调试责任，不是免费优化。
* **Default 与 Neutral Setting**：框架默认值并不中立，它已经替项目选择了部分架构路径。
* **Tradeoff 与 Compromise**：tradeoff 是显式交换不同目标，并留下验证条件；不是模糊地“各有优缺点”。

本章结论
--------

架构决策应按 ``User Path → Boundary → Constraint → Capability/Cost/Failure → Evidence → Escape Route`` 进行。好的方案不是把更多能力堆进某个框架，而是把责任放到最合适的边界，并让失败、观测和迁移都保持可解释。