第046章：Async Runtime Architecture
===================================

核心知识点
----------

* ``asyncio`` 的并发模型是协作式调度：event loop 只在 coroutine 主动到达可挂起的 ``await`` 边界时获得机会推进其它工作。
* ``async def`` 调用先创建 coroutine object；coroutine 只是可暂停执行体，Task 才表示“这段 coroutine 已交给 event loop 调度”。
* Future 表达一个稍后完成的结果、异常或取消状态。Task 本身具有 Future-like 完成态，但它的完成来自 coroutine 的执行结果。
* event loop 维护 ready callback、timer、I/O 事件以及 Task/Future 的唤醒关系；它不在任意 Python 指令处抢占当前 coroutine。
* Task 每次只推进到下一个 suspension point、return 或 exception。等待对象未完成时，Task 登记为 waiter；等待对象完成后，Task 被重新安排到 ready 路径。
* ``await`` 是状态边界。执行在 ``await`` 前观察到的共享状态，在恢复后可能已经被其它 Task 修改，因此跨 ``await`` 的条件通常要重新确认。
* 长时间 CPU 循环若没有 ``await``，会占住 event-loop 线程，阻塞其它 Task、timer、I/O callback 和 cancellation。
* ``asyncio.sleep(0)`` 可以显式让出执行权，但它只解决调度机会，不减少 CPU 工作总量；重 CPU 任务通常应移交线程池、进程池或 native code。
* ``asyncio.Queue(maxsize=N)`` 不只是容器，它还是背压机制。队列满时 ``await put()`` 暂停 producer，直到 consumer 释放容量。
* Lock、Semaphore、Queue、Event 等 asyncio 原语都是“条件未满足时挂起 Task，条件变化时安排恢复”的运行时对象。
* ``task.cancel()`` 是取消请求，不是强制终止。``CancelledError`` 会在 Task 下一次可注入执行点进入 coroutine；清理应放在 ``finally`` 中，并通常继续传播取消。
* ``TaskGroup`` 把一组子 Task 的生命周期、等待、异常传播和协调取消绑定到明确作用域，是 structured concurrency 的核心接口。
* 后台 Task 需要明确所有权。创建后完全丢弃引用，会让异常收集、取消和生命周期变得不可控。
* ``queue.get()`` 成功后，应确保最终调用 ``queue.task_done()``；否则 ``queue.join()`` 的 unfinished counter 无法归零。

关键路径
--------

Task 调度主链：

::

   asyncio.run(main())
       ↓
   create top-level Task
       ↓
   event loop selects ready Task step
       ↓
   drive coroutine frame
       ↓
   coroutine reaches await X
       ↓
   X already done → send result/exception immediately
       or
   X pending → register current Task as waiter
       ↓
   current Task suspended
       ↓
   event loop runs other ready callbacks / Tasks / I/O
       ↓
   X becomes done
       ↓
   completion callback schedules waiting Task
       ↓
   Task returns to ready queue
       ↓
   resume coroutine at same await expression
       ↓
   return / raise / await next object

取消与清理链：

::

   task.cancel()
       ↓
   mark cancellation request
       ↓
   Task gets next execution opportunity
       ↓
   inject CancelledError at suspension boundary
       ↓
   coroutine finally blocks run
       ↓
   release resource / task_done / unlock
       ↓
   cancellation propagates outward
       ↓
   TaskGroup / caller observes cancelled state

背压链：

::

   producer await queue.put(item)
       ↓
   queue full
       ↓
   producer Task suspended
       ↓
   consumer await queue.get()
       ↓
   item removed, capacity available
       ↓
   producer scheduled ready
       ↓
   put completes and producer continues

概念辨析
--------

* **coroutine object 与 Task**：coroutine 保存可恢复执行状态；Task 增加调度、完成态、取消和等待者管理。
* **Task 与 Future**：Task 主动驱动 coroutine；Future 通常只是被外部事件完成的结果容器。
* **``await`` 与并发**：``await`` 提供潜在挂起点；多个独立 Task 同时存在时，event loop 才能在它们之间推进。
* **协作式调度与抢占式调度**：asyncio 依赖代码主动让出执行权；OS 线程调度器可以在更低层抢占线程。
* **Queue 容量与锁**：``maxsize`` 控制生产速率和内存积压；Lock/Semaphore 控制共享临界区或并发度，二者解决不同问题。
* **取消与失败**：取消是一种结构化控制流；普通异常表示任务失败。TaskGroup 会对二者采用不同的传播与协调规则。
* **async 与 CPU 并行**：asyncio 主要隐藏 I/O 等待；单 event-loop 线程中的纯 Python CPU 循环不会因为 ``async def`` 自动并行。
* **后台 Task 与结构化并发**：fire-and-forget 需要显式保存和清理；TaskGroup 让子任务的所有权和生命周期天然闭合。

本章结论
--------

Async runtime 可以压缩为“event loop 维护就绪条件，Task 驱动 coroutine，Future/Queue/Lock/Timer 等对象在条件完成时重新唤醒 Task”。排查异步程序时，先找当前 Task 在 ``await`` 什么，再找谁负责完成这个等待对象、Task 何时回到 ready queue，以及取消和清理是否能闭合。只要沿这条状态链追踪，卡住、背压、取消失效、CPU 阻塞和后台任务泄漏都能落到具体运行时对象上。