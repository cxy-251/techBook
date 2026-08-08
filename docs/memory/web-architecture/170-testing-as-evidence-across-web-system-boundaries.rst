第170章：Testing as Evidence Across Web System Boundaries
=========================================================

核心知识点
----------

* 测试的目标不是增加数量，而是为系统行为提供证据：给定输入经过哪些 runtime、状态、网络、缓存和持久化边界后，最终产生什么可观察结果。
* Code coverage 只能证明代码被执行过，不能证明用户路径成立；真正的发布证据必须绑定输入、边界、状态和观察点。
* Unit、component、integration、API/contract、E2E、visual/a11y、performance test 的差异，本质是观察边界不同。
* 测试越接近真实用户路径，证据越接近生产结果，同时数据准备、环境控制、运行时间和失败定位成本也越高。
* Web 测试必须保留 browser reality：DOM、CSS、navigation、focus、storage、network、hydration、accessibility tree 和 rendering timing 都可能制造用户可见故障。
* Test scope 应匹配 failure impact。纯函数规则适合 unit，组件交互适合 component，跨模块协作适合 integration，接口兼容适合 contract，用户关键路径适合 E2E。
* Test data 是系统模型的一部分。用户、tenant、role、资源归属、缓存状态、数据库状态和版本组合都应能被 fixture 表达。
* Deterministic boundary 是稳定测试的前提。时间、随机数、网络、动画、第三方服务、并发、缓存和环境变量都需要显式控制。
* Mock/fake 的价值是缩小当前测试边界，不是伪造“整个系统已经正确”；被替换的边界仍需在更高层测试中获得真实证据。
* Flaky test 往往说明某个边界未受控，例如固定等待、共享数据库状态、异步竞态、缓存残留、浏览器动画或第三方依赖。
* 测试策略应直接映射架构边界，让失败报告可以快速回答“哪一段路径失去证据”。

关键路径
--------

从需求到测试证据：

::

   user-visible behavior
   → reconstruct runtime/state boundaries
   → identify smallest failure scope
   → choose test layer
   → prepare deterministic data/environment
   → execute path
   → observe DOM / HTTP / DB / cache / trace / metric
   → record what this test actually proves

跨边界关键路径：

::

   browser action
   → UI state
   → API/server policy
   → database mutation/read
   → cache invalidation/revalidation
   → response
   → browser-visible result

概念辨析
--------

* **Coverage 与 Evidence**：coverage 证明代码被执行，evidence 证明某条系统行为在特定条件下成立。
* **Mock 与 Boundary Proof**：mock 让当前测试隔离外部边界，不代表外部边界本身已经被证明正确。
* **Unit 与 E2E**：前者保护局部决策，后者保护真实用户跨边界路径；两者成本和证据范围不同。
* **Deterministic 与 Realistic**：稳定测试需要控制变量，真实路径测试需要保留关键 runtime；目标是控制无关不确定性，而不是删除真实风险。
* **Test Failure 与 Product Failure**：测试失败首先说明某条证据链失效，需要再定位是产品回归、环境漂移还是测试边界不稳定。

本章结论
--------

Web 测试应按 ``Behavior → Boundary → Evidence → Scope → Determinism`` 设计。高质量测试不是“尽量覆盖更多代码”，而是用最低合理成本证明关键用户路径和系统 contract，并让每个失败都能映射回真实架构边界。