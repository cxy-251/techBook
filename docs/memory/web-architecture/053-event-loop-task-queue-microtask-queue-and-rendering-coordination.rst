Event Loop, Task Queue, Microtask Queue, and Rendering Coordination
===================================================================

核心知识点
----------

* Event loop 是浏览器 host runtime 协调 JavaScript、用户事件、timer、网络 continuation、microtask checkpoint 与渲染机会的核心调度模型。
* Task 承担较大的异步工作单元，例如用户事件、timer callback、部分网络/消息回调；一个 task 开始后，当前 JavaScript 调用栈会运行到返回。
* Microtask 用于更紧邻当前 task 的 continuation，例如 Promise reaction、``queueMicrotask``、MutationObserver 和部分框架 flush。浏览器在 microtask checkpoint 中持续执行，直到队列清空。
* DOM 状态改变不等于像素已经显示。JavaScript 写入 DOM 后，浏览器还要获得 rendering opportunity，执行 style、layout、paint、composite 才能让用户看到结果。
* ``requestAnimationFrame`` 绑定下一次适合更新动画的渲染机会；它和普通 task、microtask 处在不同调度位置。
* 长 task 会阻塞下一次输入、timer 与渲染；长 microtask 链也会阻塞，因为 checkpoint 必须持续处理到队列为空。
* 不同 task source 之间不应假定全局严格 FIFO；应用应依赖具体 API 的顺序语义，而不是“所有异步回调按注册顺序执行”。
* UI framework 的 batch、nextTick、scheduler 最终仍受浏览器 event loop 约束；框架只能包装 host scheduling，不能绕开主线程和渲染机会。

关键路径
--------

一次点击到屏幕更新：

``User input → browser queues task → event callback → synchronous JS / DOM writes → task returns → microtask checkpoint → requestAnimationFrame callbacks → style/layout/paint/composite → frame``

Promise continuation：

``async result ready → Promise reaction queued as microtask → current task ends → microtask checkpoint → continuation runs → DOM/state update → later render opportunity``

Timer：

``setTimeout registered → minimum delay reached → timer task becomes runnable → selected by event loop → callback executes``

排查“状态已经改了但画面没更新”：

``当前 task 是否结束 → microtask 是否持续追加 → 是否有 long task → rAF 是否执行 → 浏览器是否进入 style/layout/paint``

概念辨析
--------

* **Task vs Microtask**：task 是较大宿主工作单元；microtask 是当前 task 结束后的紧邻 continuation，通常先于后续 task 与渲染决策继续执行。
* **Microtask vs Render**：microtask 完成只说明 JS continuation 已执行，不说明浏览器已 paint。
* **``setTimeout(0)`` vs 立即执行**：它只是请求尽快安排未来 task，仍需等待当前 task、microtask 和浏览器调度。
* **Promise vs Timer 顺序**：同一 task 内已排入的 Promise reaction 通常在 timer task 前运行；这是 microtask checkpoint 与 task 的边界，不是“Promise 天生更快”。
* **Event loop vs JavaScript engine**：engine 执行语言代码；event loop 属于 host 调度模型，决定何时把回调重新交给 engine。
* **Framework flush vs Browser paint**：框架 DOM commit 完成后仍需浏览器渲染管线，不能把框架 flush 当作像素已经呈现。

本章结论
--------

现代 Web 异步顺序应统一放回 ``Task → Microtask Checkpoint → Rendering Opportunity`` 判断。用户交互是否及时可见，取决于当前 task 能否快速返回、microtask 是否及时清空，以及浏览器能否取得下一次渲染机会。看到卡顿时，先定位调度层级，再分析框架和业务代码。
