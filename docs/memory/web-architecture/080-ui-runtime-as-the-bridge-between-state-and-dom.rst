第080章：UI Runtime as the Bridge Between State and DOM
======================================================

核心知识点
----------

* UI runtime 位于应用状态与真实 DOM 之间，把状态变化转换成界面描述、变化定位和 DOM mutation。
* 声明式 UI 的核心是描述“当前状态下界面应该是什么”，而不是逐条编写 DOM 修改命令。
* UI runtime 中的 render 与浏览器 rendering 不是一回事：前者是状态到界面描述的转换，后者是 style、layout、paint、composite。
* React、Vue、Svelte、Solid 等实现策略不同，但都必须解决 ``state change → affected UI → DOM mutation``。
* DOM mutation 是框架抽象最终落地的位置；任何框架优化最终都要接受浏览器 DOM、样式和布局成本。
* UI runtime 可以表达 pending、error、success、optimistic 等界面状态，但不拥有服务器、数据库、缓存和权限真相。

关键路径
--------

一次典型交互应按以下路径分析：

``User Event → Event Handler → State Change → UI Runtime Scheduling → UI Description → Change Localization → DOM Mutation → Style/Layout/Paint → User Feedback``

排查更新失败时按顺序检查：

#. 事件是否真正进入处理器；
#. 状态是否产生预期变化；
#. 组件或模板是否把状态映射到正确输出；
#. runtime 是否定位到正确节点、属性或文本；
#. DOM 是否实际提交变化；
#. 浏览器是否因长任务、布局或样式问题推迟可见反馈。

对于 ``count: 0 → 1``，runtime 可能只需更新文本节点；对于 ``pending: false → true``，可能需要同时修改 ``disabled``、``aria-busy`` 和 loading 文案。状态变化本身不是 DOM 更新计划，runtime 必须把它收敛为具体平台操作。

概念辨析
--------

* **UI render ≠ browser render**：组件重新执行或模板求值发生在 JavaScript/runtime 层；layout、paint、composite 属于浏览器渲染管线。
* **Declarative UI ≠ no DOM cost**：声明式语法减少应用层命令式代码，真实 DOM mutation 与浏览器成本仍然存在。
* **State owner ≠ UI runtime**：runtime 管理更新流程，不自动成为订单、库存、权限、服务器数据的权威来源。
* **Re-render ≠ DOM replacement**：组件可以重新计算整段输出，commit 阶段仍可能只修改少量真实节点。
* **Framework abstraction ≠ system boundary removal**：网络、缓存、数据库、浏览器安全和部署边界不会因为组件框架而消失。

本章结论
--------

分析 UI runtime 时固定使用 ``状态来源 → 更新触发 → 界面描述 → 变化定位 → DOM mutation → 浏览器渲染``。框架的核心价值是把状态变化稳定地转换成有限 DOM 更新；用户最终看到的结果仍由浏览器平台完成。