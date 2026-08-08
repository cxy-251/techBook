第186章：UI Runtime Mapping React, Vue, Svelte, Solid, and Compiler-Driven UI
=============================================================================

核心知识点
----------

* UI runtime 的稳定比较对象是 ``input event → state write → dependency propagation → derived computation → DOM update → effect lifecycle → teardown``。
* React 主要通过 state snapshot、component render、reconciliation、commit 和 scheduler 把状态变化映射到 DOM；render 应保持纯计算，外部订阅进入 effect。
* Vue 通过 reactive dependency、computed/watch、component render effect 和 compiler-informed patch 更新 DOM；template compiler 提供静态分析和 patch 提示。
* Svelte 把更多变化传播分析移到 compile time。源码中的 state、derived、effect 与 DOM binding 会被 compiler 转换为更直接的更新路径。
* Solid 以 fine-grained reactivity 为核心，signal 写入只触发实际依赖该 signal 的 computation 或 DOM binding，而不是默认重跑整个组件函数。
* Virtual DOM、signals、compiler output 是不同 change-propagation model，真正差异是依赖如何记录、更新如何调度、DOM 如何被定位和修改。
* 派生状态优先从已有 state 计算，不应无必要复制成第二份独立状态；重复状态会制造同步问题。
* Side effect 与可见 UI 计算必须分离。订阅、timer、network、imperative DOM 和外部资源都需要 cleanup 和 race handling。
* Async callback 可能携带旧 snapshot 或旧 dependency；需要识别 stale closure、过期请求、重复订阅和晚到响应。
* Hydration 把 server-rendered HTML、client initial state 与 UI runtime 连接起来。初始输入不同会产生 mismatch、状态重置或可见闪动。
* UI framework 只覆盖界面运行时。Routing、server data、mutation、identity、cache、database 与 deployment 仍是其他系统边界。
* 性能比较不能只看框架标签；应观察真实 render/patch 范围、effect 数量、DOM 成本、bundle、memory 和 interaction latency。

关键路径
--------

统一 UI runtime 路径：

::

   browser event
   → state update
   → runtime/compiler dependency propagation
   → derived values recompute
   → DOM patch/commit
   → browser style/layout/paint
   → user sees result

Effect 生命周期：

::

   component/runtime mounts
   → create subscription/effect
   → dependency changes
   → cleanup old resource
   → create new resource
   → component teardown
   → final cleanup

概念辨析
--------

* **React Re-render 与 DOM Rewrite**：组件重新计算不等于整棵 DOM 重写，实际 DOM 修改发生在 commit 差异阶段。
* **Vue Reactivity 与 Template**：reactivity 记录依赖，template/compiler 描述渲染结构和动态位置，两者协同工作。
* **Svelte Compiler 与 No Runtime**：更多工作被前移到编译期，不代表浏览器完全没有运行时状态和调度逻辑。
* **Solid Fine-Grained Reactivity 与 Component Re-render**：signal 变化更直接触发具体依赖，而不是默认重新执行整个组件树。
* **UI State 与 Server State**：UI state 属于当前交互，server state 是远端事实的本地观察副本，生命周期和刷新责任不同。

本章结论
--------

比较 React、Vue、Svelte、Solid 时，应按 ``State Model → Dependency Tracking → Update Scheduling → DOM Mutation → Effect Cleanup`` 阅读。语法只是表面，真正决定行为的是状态变化如何穿过 runtime/compiler 并最终落到浏览器 DOM。