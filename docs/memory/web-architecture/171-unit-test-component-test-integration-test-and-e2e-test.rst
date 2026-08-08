第171章：Unit Test, Component Test, Integration Test, and E2E Test
===================================================================

核心知识点
----------

* Unit test 保护局部逻辑和纯决策，适合 parser、validator、formatter、policy、reducer、cache-key builder 等“输入 → 决策 → 输出”明确的责任单元。
* Component test 保护 UI responsibility boundary，验证 props、local state、event、loading、error、disabled、focus 和 accessibility state 最终如何进入 DOM。
* Integration test 保护模块协作，适合 route/action、auth guard、service、database adapter、cache layer、serializer 等一起工作的路径。
* E2E test 保护用户关键路径，从真实浏览器跨过 route、network、server、database 和 cache，验证登录、提交、支付、上传、搜索等高价值流程。
* 测试层级的核心差异不是文件位置，而是跨过多少 runtime、依赖多少真实外部状态、观察哪个最终结果。
* Unit test 应把时间、随机数、locale、feature flag 等隐含环境变成显式输入，使规则失败可快速定位。
* Component test 应优先断言用户可观察的 role、label、text、focus、disabled 和 error，而不是内部 hook、实例或私有变量。
* Integration test 要明确哪些依赖是真实实现、fake、mock 或 fixture；范围不清会导致既慢又难定位。
* E2E test 数量应少而高价值，覆盖业务关键路径、跨边界风险、历史真实事故与发布 smoke，而不是穷举所有分支。
* E2E 等待应绑定可观察状态，例如 URL 改变、按钮可操作、确认文本出现、网络响应完成，而不是固定 sleep。
* Test pyramid 更接近成本模型，而不是硬性比例。现代 Web 应根据 browser complexity、API risk、framework boundary 和用户价值重新分配层级。
* Flaky test 通常暴露未受控边界：动画、时间、网络、共享数据库、缓存、异步竞态、第三方依赖或浏览器状态。

关键路径
--------

测试层级选择：

::

   identify failure risk
   → local pure decision? → unit
   → UI responsibility? → component
   → module collaboration? → integration
   → user-critical cross-runtime path? → E2E

E2E 用户路径：

::

   browser interaction
   → DOM/router
   → request
   → server handler
   → transaction/cache
   → response/redirect
   → final user-visible state

概念辨析
--------

* **Unit 与 Component**：unit 主要证明局部逻辑，component 主要证明 UI 输入、事件和 DOM 行为。
* **Integration 与 E2E**：integration 只连接选定模块和依赖，E2E 尽量从真实用户入口验证整条关键路径。
* **Mock 与 Fake**：mock 常验证调用行为，fake 提供可工作的简化实现；二者都在缩小测试边界。
* **Test Pyramid 与 Test Strategy**：金字塔表达成本梯度，策略应按当前系统风险决定各层证据比例。
* **Flaky 与 Random Failure**：flaky 不是“偶尔运气差”，而是测试依赖的时间、状态或外部边界没有被控制。

本章结论
--------

测试分层应按 ``Local Decision → UI Boundary → Module Collaboration → User Path`` 阅读。每层只承担它能可靠证明的事实：低层提高反馈和定位速度，高层补齐真实边界组合；稳定策略来自层级协作，而不是把所有风险塞进一种测试。