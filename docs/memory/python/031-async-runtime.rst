第031章：Async Runtime
======================

核心知识点
----------

* ``async def`` 定义 coroutine function；调用它时先创建 coroutine object，函数体并不会立即同步执行到底。
* coroutine object 表达“这段异步函数体的一次可恢复执行状态”；Task 表达“由 event loop 调度的 coroutine”；Future 表达“一个稍后会完成的结果、异常或取消状态”。
* native coroutine 天然是 awaitable；自定义 awaitable 通过 ``__await__()`` 返回 iterator 参与 ``await`` 协议。
* ``await`` 是显式 suspension boundary。右侧 awaitable 尚未完成时，当前 coroutine frame 被保存，执行权交回调度器；完成后从同一位置恢复。
* ``await`` 本身不等于并发。只有 coroutine 被 Task 等调度单位独立注册后，event loop 才能在多个可运行对象之间推进。
* ``asyncio.create_task(coro)`` 把 coroutine 包装为 Task 并安排到当前 event loop；Task 负责推进 coroutine、保存结果/异常、处理取消并唤醒等待者。
* Future 更像完成信号容器。高层业务通常直接使用 coroutine/Task，底层 I/O、timer、callback、线程池桥接更常用 Future 表达“结果稍后到达”。
* event loop 进行 cooperative scheduling：Python 代码不会在任意字节码处被 async 调度抢占，切换主要发生在 coroutine 主动到达未完成的 awaitable。
* 一个 native coroutine object 通常只能完整消费一次；Future/Task 完成后可以被多个等待方读取结果。
* 子 Task 的 return value 或 exception 会在父 coroutine 的 ``await`` 位置重新出现，因此 ``await`` 同时是结果回收边界和异常传播边界。
* ``task.cancel()`` 是取消请求，不是强制杀死线程。Task 在下一次可运行机会向 coroutine 的挂起点注入 ``asyncio.CancelledError``，清理代码应在 ``finally`` 中释放资源。
* ``TaskGroup`` 等 structured concurrency 工具把一组 Task 的生命周期绑定到一个明确作用域：退出时统一等待，成员失败时协调取消与异常聚合。
* 长时间 CPU 运算如果没有 suspension point，会持续占用 event-loop 线程；async 主要解决等待期间的协作调度，不自动解决 CPU 并行。

关键路径
--------

典型 async 调度链：

::

   call async function
       ↓
   coroutine object created
       ↓
   asyncio.run / create_task
       ↓
   Task registered with event loop
       ↓
   Task drives coroutine frame
       ↓
   coroutine reaches await pending awaitable
       ↓
   frame suspended
       ↓
   awaited Future / Task records waiter
       ↓
   event loop runs other ready work
       ↓
   I/O / timer / callback completes Future
       ↓
   waiting Task becomes ready
       ↓
   event loop resumes coroutine
       ↓
   await expression returns value or raises exception
       ↓
   coroutine finishes / fails / is cancelled

取消路径：

::

   task.cancel()
       ↓
   cancellation requested
       ↓
   task scheduled to resume
       ↓
   inject CancelledError at suspension point
       ↓
   coroutine finally/cleanup runs
       ↓
   cancellation propagates or is deliberately handled

概念辨析
--------

* **coroutine function 与 coroutine object**：前者是 ``async def`` 定义；后者是调用后得到的一次异步执行对象。
* **coroutine 与 Task**：coroutine 保存可恢复执行；Task 是 event loop 对 coroutine 的调度与完成状态包装。
* **Task 与 Future**：Task 的完成来自 coroutine 执行结果；Future 的完成通常由外部事件或回调写入。
* **await 与并发**：``await`` 只表达依赖和潜在挂起；``create_task``、TaskGroup 等才让多个 coroutine 同时处于可调度状态。
* **async 与线程并行**：asyncio 默认在单 event-loop 线程内协作切换；CPU-bound 并行需要线程、进程、native code 或其它执行资源。
* **取消与终止**：cancel 是异常注入协议，让 coroutine 有机会清理；它不是 OS 级强制终止。
* **coroutine object 与 Future 的重复等待**：coroutine 完整结束后不能重新执行；已完成 Future/Task 保存完成态，可被再次 await。
* **``asyncio.sleep(0)`` 与真正等待**：它可以主动让出 event loop 执行权，但不会减少 CPU 工作总量。

本章结论
--------

Async runtime 可以压缩为“coroutine 保存可恢复执行，Task 负责调度它，Future 表达等待完成，event loop 在 suspension boundary 之间推进”。排查异步代码时，应先确认创建了什么对象，再确认谁驱动它、当前 await 谁、完成信号由谁写入、取消会在哪个挂起点注入。掌握这条对象与状态链后，async/await、Task、Future、event loop 与 cancellation 可以统一到同一个执行模型中。