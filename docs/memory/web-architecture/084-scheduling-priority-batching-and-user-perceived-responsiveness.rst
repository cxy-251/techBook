第084章：Scheduling, Priority, Batching, and User-Perceived Responsiveness
==========================================================================

核心知识点
----------

* UI 响应性不仅取决于结果是否正确，还取决于用户操作后多久能看到下一次有效反馈。
* Batching 合并多个状态更新，减少重复 render、diff、DOM mutation 和 effect，但会改变状态读取与提交时机。
* Priority 用来区分紧急反馈与可延后工作；输入、焦点、按钮反馈通常高于列表过滤、图表重算和后台预取。
* Concurrent / interruptible rendering 的价值是让高优先级工作有机会打断或推迟低优先级 UI 计算。
* 框架调度最终仍受浏览器主线程、task、microtask、render opportunity、GC 和 long task 约束。
* 昂贵 UI 工作应根据依赖关系选择 split、defer、memoize、virtualize、worker offload 或 idle scheduling。

关键路径
--------

响应性分析使用：

``User Input → Browser Event → UI Update Queue → Priority/Batching → Urgent Commit → Browser Paint → Deferred Work → Later Commit``

搜索页面中应把工作拆成：

``输入框字符/光标 → urgent``

``过滤结果/统计/图表 → user-visible but deferrable``

``预取/分析/非关键计算 → background``

排查卡顿时先定位用户输入时间点，再看：

#. 输入前是否有 long task；
#. handler 内是否混入大计算；
#. microtask 是否连续占满；
#. runtime 是否把低价值更新放进紧急路径；
#. DOM/layout/paint 是否成为 presentation delay。

最终用 INP、input delay、long task、frame drop 和真实设备时间线验证调度策略。

概念辨析
--------

* **Batching ≠ immediate state visibility**：更新进入队列后，当前闭包仍可能读取旧 render 快照。
* **Priority ≠ business importance**：它描述当前交互时间上的紧急度，而不是功能长期价值。
* **Concurrent rendering ≠ parallel DOM mutation**：runtime 可以分片或中断计算，真实 DOM commit 仍需与浏览器主线程协调。
* **Microtask splitting ≠ yielding**：把大工作拆成连续 microtask 仍可能阻塞渲染机会。
* **Framework scheduler ≠ browser scheduler replacement**：框架只能在浏览器提供的执行窗口中安排自己的工作。

本章结论
--------

调度的核心目标是优先让用户看到“系统已收到意图”。先提交输入、pressed、pending、focus 等紧急反馈，再处理可延后的昂贵 UI；所有优化都必须回到浏览器主线程时间线验证。