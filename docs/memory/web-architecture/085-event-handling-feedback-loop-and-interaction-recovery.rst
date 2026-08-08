第085章：Event Handling, Feedback Loop, and Interaction Recovery
================================================================

核心知识点
----------

* UI 交互的入口始终是浏览器事件系统；框架回调位于事件派发之后。
* Event handler 的职责是把用户意图转换成状态迁移、请求、导航、表单提交或其他系统动作。
* 一次完整交互必须形成反馈闭环：``intent → pending → success/error → recovery``。
* 即时反馈用于确认系统已经接收用户动作，远端操作是否最终成功属于另一阶段。
* 浏览器默认行为、框架接管、焦点、键盘和可访问性语义必须协同，不能为了框架抽象破坏原生行为。
* Recovery 要处理请求失败、权限拒绝、重复点击、乱序响应、乐观更新失败和路由中断。
* Event propagation 决定局部组件、父容器和全局监听器的责任边界。

关键路径
--------

一次保存操作应追踪：

``Browser Event → Handler → Validate Intent → Pending State → Mutation Request → Server Result → Cache Update/Invalidation → UI Commit → Success/Error Feedback``

失败恢复路径：

``Mutation Failure → Preserve User Draft → Restore Interactive State → Explain Error → Retry / Re-auth / Alternative Path``

对于可能并发的异步动作，应给每次意图建立 request id、version 或 abort signal，防止旧响应覆盖新状态。

原生表单的接管顺序应是：

``HTML Semantics → Default Submit Behavior → Framework Interception → Pending UI → Remote Result → Focus/Error Recovery``

``preventDefault`` 用于接管默认行为；``stopPropagation`` 控制事件传播，两者职责不同。

概念辨析
--------

* **Click ≠ successful mutation**：点击只表达用户意图，远端状态改变需要服务器确认。
* **Pending feedback ≠ success**：loading、disabled 只表示动作处理中。
* **preventDefault ≠ stopPropagation**：前者阻止默认动作，后者阻止事件继续传播。
* **Optimistic UI ≠ authoritative state**：乐观更新是暂时预测，失败时必须能回滚或重新同步。
* **Error message ≠ recovery**：恢复还要保留草稿、恢复可操作状态并给出下一步路径。

本章结论
--------

交互设计必须覆盖完整闭环，而不是只写事件回调。固定追踪 ``事件 → 意图 → 状态 → 请求 → 反馈 → 恢复``，并保留浏览器默认语义与焦点路径，才能让异步 UI 在成功和失败两种情况下都保持可预测。