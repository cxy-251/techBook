Promise, Timer, Event Callback, and Asynchronous Continuation
==============================================================

核心知识点
----------

* 异步 JavaScript 的核心不是“并行执行代码”，而是 continuation scheduling：把后续逻辑保存起来，在未来由 Promise、timer、event 或 host callback 重新进入 JavaScript。
* event callback 由浏览器事件系统持有；timer callback 由 timer 记录持有；Promise reaction 由 Promise 状态变化触发；网络、storage、worker 等能力由 host 推进实际工作。
* Promise continuation 进入 microtask；timer callback 通常进入未来 task。``await`` 本质上把 async function 后半段注册为 Promise continuation。
* Timer 是 delay request，不是精确执行时刻。``setTimeout(fn, 200)`` 表示满足最小时间条件后可以调度，真实执行仍受主线程、后台节流和浏览器策略影响。
* 搜索、路由和请求型异步最容易出现 stale continuation：旧请求、旧 timer 或旧 Promise 结果在新用户意图之后返回，覆盖最新状态。
* ``AbortController`` 可以把“当前结果已经不需要”传递给支持 AbortSignal 的 host API；取消浏览器端等待不等于服务器一定停止了业务执行。
* 即使某个 Promise 已无法取消，仍可用 request/version id、signal 状态、route identity 或 component lifecycle 阻止过期 continuation 写入当前状态。
* 所有异步资源都需要生命周期出口：listener 要移除、timer 要 clear、subscription 要 unsubscribe、request 要 abort 或失效、重复轮询要有停止条件。

关键路径
--------

搜索输入防乱序：

``input event → update current intent → clear old timer → abort old request → schedule debounce timer → start fetch → Promise reaction → verify request/version id → commit latest result``

``await`` 路径：

``async function → synchronous prefix → await promise → return control to host → promise settles → microtask → resume async function``

Timer 路径：

``setTimeout → host owns timer → delay threshold reached → task queued/runnable → main thread available → callback runs``

稳定异步更新的检查顺序：

``continuation 由谁创建 → 进入 task 还是 microtask → 捕获了什么状态 → 未来写入谁 → 旧 continuation 如何取消/失效 → 错误如何恢复``

概念辨析
--------

* **Async vs Parallel**：异步表示当前调用栈让出控制并在未来继续；是否真正并行取决于 host、Worker、网络、GPU 等执行位置。
* **Promise vs Timer**：Promise reaction 是 microtask continuation；timer 是 host 的延迟 task 请求，语义与调度位置不同。
* **``await`` vs 阻塞线程**：``await`` 暂停当前 async function continuation，不阻塞浏览器等待网络；主线程可以继续处理其它工作。
* **Abort vs Rollback**：abort 尝试停止或忽略进行中的 host 工作；已经发生的服务器副作用需要幂等、事务或补偿机制处理。
* **Debounce vs Cancel**：debounce 减少启动频率；cancel/invalidating stale result 解决已经启动的旧工作。
* **Resolved Promise vs 已绘制 UI**：Promise continuation 已运行只代表状态/DOM 可能已更新，屏幕仍需后续 rendering opportunity。

本章结论
--------

稳定异步代码应按 ``Create Continuation → Host/Queue Ownership → Reentry → State Validity Check → Cleanup`` 设计。Promise、timer、事件和网络只是不同 continuation 来源；真正决定正确性的，是未来回调是否仍代表当前用户意图，以及旧工作是否有明确取消、失效和错误恢复路径。
