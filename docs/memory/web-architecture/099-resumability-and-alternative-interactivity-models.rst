第099章：Resumability and Alternative Interactivity Models
==========================================================

核心知识点
----------

* Resumability 关注“服务器已经输出 HTML 后，浏览器是否必须重新执行大量组件逻辑才能恢复交互”。
* 传统 hydration 往往在启动阶段下载组件代码、重建组件树、恢复状态并绑定事件；resumability 尝试把部分执行上下文、事件入口和状态关系提前编码进服务器输出。
* 这类模型的核心收益是减少 browser startup main-thread work，把一部分工作推迟到用户真实交互、组件可见或其它触发条件。
* 难点在 serialization：系统需要表达事件处理器位置、组件边界、状态引用、依赖关系和代码加载点，同时禁止 secret、连接对象和不可序列化运行时对象跨到浏览器。
* Lazy activation 把代码加载和事件恢复推向 user intent；适合离散、低频交互，不适合关键按钮首次点击后才开始长时间下载。
* Islands、partial hydration、resumability、lazy activation 都是在重新分配“什么时候下载代码、什么时候执行、什么时候绑定事件、什么时候恢复状态”。
* Alternative model 用更复杂的 compiler、build output、serialization、chunk graph 和调试路径换取启动性能；团队维护成本必须计入选择。
* 无论采用何种模型，最终仍受 network、JavaScript engine、event loop、DOM、cache、memory 与浏览器安全边界限制。

关键路径
--------

::

   Server / Build
     → Render HTML
     → Encode State / Event / Component Boundaries
     → Browser Parse / Paint
     → Lightweight Runtime Entry
     → Wait for Visibility / Idle / User Event
     → Resolve Handler / Component Chunk
     → Load Code
     → Restore Needed State
     → Execute Interaction
     → Server Mutation / Data Refresh

* 对每个延迟激活组件标记：事件入口、代码位置、状态所有者、数据版本、安全边界和失败恢复。
* 核心任务组件应提前预热或立即激活；低优先级推荐、评论工具、聊天等更适合 visibility/idle/intent 驱动。

概念辨析
--------

* **Resumability ≠ 零 JavaScript**：它减少或推迟初始执行，真实交互仍需要浏览器代码。
* **Resumability ≠ hydration 的同义词**：前者强调从序列化执行状态继续，后者通常强调重新建立客户端组件运行关系。
* **Lazy activation ≠ 一定更快**：它可能把启动等待移动到首次交互；只有等待位置符合用户路径才有收益。
* **Islands ≠ resumability**：islands 主要局部化客户端区域；resumability 主要改变运行状态恢复方式，两者可组合但不是同一概念。
* **更复杂模型 ≠ 更先进架构**：内容与交互简单时，原生 HTML + 少量 JavaScript 可能比复杂 runtime 协议更可靠。

本章结论
--------

替代交互模型的本质是重新安排客户端工作时机。Resumability 通过序列化和延迟恢复减少启动执行，islands 与 partial hydration 缩小激活范围，lazy activation 把工作靠近用户意图。选择它们时必须同时计算启动收益、首次交互等待、序列化限制、调试复杂度和失败恢复，而不能只比较“是否 hydration”。
