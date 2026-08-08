第111章：Request Waterfall, Parallel Loading, and Dependency Ordering
====================================================================

核心知识点
----------

* Request waterfall 不是“请求多”，而是多个读取被错误串行化，后一个读取等待前一个本不需要提供的结果。
* 分析页面读取时应先画 dependency graph，再区分真实依赖边和由组件层级、代码顺序、晚发现参数造成的伪依赖边。
* 真正依赖通常来自身份、tenant、权限、上游 ID、参数校验或 feature context；这些顺序属于正确性和 trust boundary，不应为追求并行而删除。
* 一旦共同前置条件确定，彼此独立的读取应尽早启动；总等待会从“多个耗时相加”接近“前置条件 + 最慢并行分支”。
* Nested route、nested component 和 ``useEffect`` 很容易把视觉树误写成数据依赖树，使首屏核心读取推迟到 bundle 执行、hydration 或子组件挂载之后。
* 并行不是越多越好。无条件同时发起所有潜在读取会增加连接、数据库并发、cache miss 和无效工作；首屏必要数据与低概率交互数据要分级。
* Prefetch、route loader、server promise 提前创建和 query cache 预热，本质上都在做同一件事：把已知的未来读取移到更早的时间点。
* 用户意图变化后，旧读取需要 abort、降级为仅写缓存，或在 commit 前校验 identity，避免晚返回覆盖新页面。

关键路径
--------

先画：

``User Intent → Route Match → Trusted Context(session/tenant/permission) → {Projects, Alerts, Activity, Notifications} → UI``

如果四个业务读取只共同依赖 trusted context，它们应在上下文成立后并行启动，而不是 ``Projects → Alerts → Activity → Notifications`` 串行等待。

排查 waterfall 时按顺序看 Network start time、server trace、数据库 query start time，再回到代码确认是谁引入了等待边。优化目标是删除伪依赖，不是破坏权限和数据依赖。

概念辨析
--------

* **Waterfall vs many requests**：多个同时启动的请求不是 waterfall；阶梯式启动且后续无真实依赖才是问题。
* **Parallelism vs correctness**：权限、tenant 和资源 ID 等真实前置条件必须保留顺序。
* **UI nesting vs data dependency**：组件父子关系不等于数据必须父子串行获取。
* **Prefetch vs eager everything**：prefetch 依据用户意图和成本提前工作；无差别 eager fetch 会浪费资源。
* **Abort vs ignore result**：abort 尝试停止工作；忽略旧结果只阻止 UI commit，两者可组合但责任不同。

本章结论
--------

读取性能首先是依赖建模问题。稳定优化方式是尽早识别真实前置条件，在可信上下文建立后并行启动独立读取，并让低优先级工作延后；任何优化都必须同时保留权限边界、缓存身份和旧请求的提交资格控制。