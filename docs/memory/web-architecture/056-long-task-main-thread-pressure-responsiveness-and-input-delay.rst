Long Task, Main Thread Pressure, Responsiveness, and Input Delay
===============================================================

核心知识点
----------

* Main thread 是页面最关键的共享资源之一，承担 JavaScript、事件回调、DOM 操作、style/layout、部分渲染协调、GC、框架更新和生命周期回调。
* 用户输入已经发生，不代表回调能立即执行。若主线程正在运行其它 task，输入只能排队；这段等待就是 input delay 的核心来源。
* Long Task 是主线程连续占用的重要观测信号。50ms 是常用工程阈值，用于暴露会明显压缩输入和绘制机会的任务，但它不是“49ms 安全、51ms 必坏”的绝对边界。
* 一次交互延迟可以拆成 ``input delay → processing duration → presentation delay``：等待回调开始、执行回调、等待下一次绘制分别属于不同责任段。
* 造成主线程压力的不只有“业务 JS”：模块启动、JSON 解析、大列表 diff、DOM 批量更新、强制同步 layout、GC、microtask 链、第三方脚本都可能占据同一条用户可见路径。
* 把大工作切成连续 microtask 不等于真正让出主线程；microtask checkpoint 仍需清空。需要让浏览器处理输入/渲染时，应切到后续 task、scheduler、Worker 或其它能真正交还控制权的边界。
* Worker 适合纯计算、解析、搜索索引、压缩等可序列化工作；DOM、layout 和多数 UI commit 仍需要主线程。
* 响应性优化应以用户关键反馈为优先：先让 pending/pressed/typing 等状态及时可见，再安排低优先级计算、analytics 和非关键更新。

关键路径
--------

一次交互到下一帧：

``User input → event queued → wait for main thread → callback starts → JS/state/DOM work → microtasks → style/layout/paint → next frame``

延迟拆分：

``Input Delay = input happened → handler starts``

``Processing Duration = handler starts → event callbacks finish``

``Presentation Delay = callbacks finish → next visual frame``

典型长任务：

``input callback → filter/sort 50k rows → build DOM → sync layout read → framework effects → analytics → task returns``

优化顺序：

``找到受影响交互 → Performance trace 定位阻塞 task → 拆出脚本/layout/GC/third-party → 缩短单次任务 → 减少 DOM 范围 → 移出非关键工作 → Worker/缓存/虚拟化 → 验证真实 INP/帧表现``

概念辨析
--------

* **Long Task vs INP**：Long Task 是主线程占用证据；INP 是用户交互到下一次绘制的整体响应性指标。二者相关但不等价。
* **Input delay vs Handler slow**：input delay 发生在回调开始之前；handler slow 属于 processing duration。
* **DOM update done vs Paint done**：框架或脚本已提交 DOM 后，presentation delay 仍可能来自 style/layout/paint。
* **Microtask splitting vs Yielding**：连续 ``queueMicrotask`` 仍可能饿死渲染；真正 yielding 要让 event loop 获得处理其它 task/渲染的机会。
* **Main thread vs Network**：请求很快返回，UI 仍可能因主线程忙碌而迟迟不更新；网络 timing 和主线程 timing 要分开。
* **Worker vs Main thread**：Worker 可以搬走纯计算，不能直接替代 DOM mutation、layout 和页面交互提交。

本章结论
--------

响应性问题应沿 ``Input → Queue → Main Thread → State/DOM → Rendering → Frame`` 定位。先区分 input delay、处理时长和 presentation delay，再找占用主线程的真实工作。稳定优化原则是缩短单次同步任务、避免 microtask 饥饿、控制 DOM/layout 范围、把可迁移计算移出主线程，并让关键视觉反馈优先于低价值工作。
