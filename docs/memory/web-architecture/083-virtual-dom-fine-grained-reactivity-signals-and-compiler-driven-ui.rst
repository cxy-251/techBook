第083章：Virtual DOM, Fine-Grained Reactivity, Signals, and Compiler-Driven UI
=============================================================================

核心知识点
----------

* UI runtime 的核心差异之一，是如何发现状态变化、定位依赖、生成更新计划并提交真实 DOM。
* Virtual DOM 通过重新计算界面描述，再执行 reconciliation / patch，把变化收敛成必要 DOM mutation。
* Fine-grained reactivity 以具体响应式读取为依赖边界，状态写入后只通知相关 effect、memo 或表达式。
* Signal 是显式响应式状态单元，通常以 getter/setter 与 subscriber 关系组织依赖传播。
* Compiler-driven UI 把部分变化分析提前到 build time，通过静态分析、patch flag、直接更新代码等方式减少 runtime 工作。
* 无论采用哪种模型，最终都要进入 DOM、style、layout、paint；框架无法绕过浏览器平台成本。

关键路径
--------

统一分析路径：

``User Event → State Write → Dependency/Change Detection → Update Plan → DOM Mutation → Browser Rendering``

Virtual DOM 路径：

``State Change → Re-run Component/Render → New UI Tree → Diff/Patch → DOM Commit``

细粒度响应路径：

``Signal Write → Notify Subscribers → Recompute Affected Expressions → Direct DOM Update``

编译驱动路径：

``Template/Component Source → Build-Time Analysis → Generated Update Logic → Runtime State Change → Targeted DOM Update``

性能排查应分别看：组件或表达式重新计算成本、依赖传播或 diff 成本、真实 DOM mutation 数量，以及 mutation 后的浏览器布局与绘制成本。

概念辨析
--------

* **Virtual DOM ≠ DOM copy**：它是 UI 描述和更新规划结构，不是浏览器 DOM 的完整镜像。
* **Re-render ≠ repaint**：组件重新执行属于 runtime 计算；浏览器 repaint 属于渲染管线。
* **Fine-grained ≠ zero overhead**：依赖图本身也需要建立、维护和清理。
* **Signals ≠ framework-independent magic**：signal 只是响应式状态单元，实际调度、effect 和 DOM 提交仍由 runtime 决定。
* **Compiler-driven ≠ no runtime**：编译器可以减少运行时判断，浏览器执行、状态传播和平台 mutation 仍然存在。

本章结论
--------

比较 UI 框架时应比较“变化传播模型”，而不是只比较语法。固定追踪 ``状态写入 → 依赖定位 → 更新计划 → DOM 提交``，就能把 Virtual DOM、signals、细粒度响应式和编译优化放到同一张系统图中。