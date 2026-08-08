第106章：Input Latency and Touch Responsiveness
===============================================

核心知识点
----------

* Input Latency 是 ``触摸发生 → 屏幕反馈`` 的端到端时间，必须拆成采样、系统分发、App 处理、渲染、合成、显示几个阶段。
* Touch Responsiveness 不只取决于平均延迟，还取决于抖动、首帧反馈、连续帧节奏和输入与视觉结果是否稳定对齐。
* 输入时间戳与回调执行时间不同：前者描述样本何时发生，后者已经包含系统分发和主线程排队成本。
* 高 Touch Sampling Rate 提供更密集的输入事实，但若 App 主线程、GPU 或显示链路延迟，高采样率不能消除跟手问题。
* MOVE 事件可能包含 historical / coalesced samples；拖动、绘图和手写场景若只消费最新点，会损失轨迹信息。
* Input Dispatch Latency 发生在窗口目标确认和事件进入 App 之前；复杂窗口、overlay、系统手势、focus 变化和目标 App 不及时消费都会增加等待。
* App Handling Latency 主要来自主线程长任务、锁等待、同步 IPC、I/O、GC/ARC 压力、复杂布局和手势竞争。
* Rendering Latency 发生在状态更新之后，包括 layout/draw、RenderThread/Core Animation、GPU、buffer/fence 与 compositor；状态已更新不等于用户已经看到。
* 显示刷新率决定反馈最早能落在哪个扫描周期。即使某段工作只晚几毫秒，也可能错过 deadline，额外增加一个完整刷新周期。
* Jank、Missed Frame 和 ANR 是同一端到端交互链上的不同严重程度表现：前两者主要破坏节奏和反馈，ANR 表示 App 长时间无法及时处理系统交互。

关键路径
--------

::

   Touch sample timestamp
      → Kernel / Input Service
      → Window Target
      → App Main Thread callback
      → UI State Update
      → Layout / Render / GPU
      → Buffer ready
      → System Compositor
      → Present / Scanout
      → User sees feedback

延迟归因顺序：

::

   先找首个可见反馈帧
      → 回溯对应 input timestamp
      → 比较 dispatch 到达时间
      → 比较 callback start / end
      → 比较 frame submit / GPU completion
      → 比较 compositor present time
      → 得到具体延迟阶段

概念辨析
--------

* **Sampling Latency vs Dispatch Latency**：前者发生在触摸被观测之前；后者发生在事件已经存在、但尚未进入目标 App 之前。
* **Handling Latency vs Rendering Latency**：Handling 是 App 把事件转换成状态；Rendering 是把状态转换成可显示帧。
* **Frame Rate vs Input Latency**：高帧率有助于降低显示等待，但主线程或输入分发慢时，输入延迟仍然可能很高。
* **Jank vs High Latency**：Jank 强调帧节奏不稳定；High Latency 强调输入到视觉结果之间等待过长，两者可以同时出现，也可以分别出现。
* **ANR vs Missed Frame**：Missed Frame 是毫秒级 deadline 失败；ANR 是秒级交互无法及时完成的系统级故障判断。
* **平均延迟 vs P99 延迟**：交互手感往往更容易被偶发长尾破坏，因此只看平均值会隐藏真实问题。

本章结论
--------

输入响应必须用端到端时间线分析。最有效的方法不是先猜“主线程慢”或“触控差”，而是确定输入事件何时发生、何时进入 App、哪一帧承载反馈、该帧何时真正显示，再把总延迟切回采样、分发、处理、渲染和显示边界。