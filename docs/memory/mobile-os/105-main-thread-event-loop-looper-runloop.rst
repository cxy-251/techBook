第105章：Main Thread, Event Loop, Looper, RunLoop
================================================

核心知识点
----------

* Main Thread 是移动 UI 的主要串行执行线，输入回调、生命周期、状态更新、布局、绘制提交和动画推进都在这里竞争时间。
* Event Loop 的基本模型是 ``wait → wakeup → select callback → execute → sleep``；它把异步系统事件转换成应用线程上的同步函数调用。
* Android 主线程使用 Looper、MessageQueue、Handler、native Looper callback 和 Choreographer；Apple 使用 RunLoop、Source、Timer、Observer、Mode。
* Android 输入事件通过 InputChannel 唤醒主线程 Looper，再由 WindowInputEventReceiver / ViewRootImpl 处理；它并不等于普通 ``Handler.post`` 消息。
* Choreographer 将 input、animation、traversal、commit 等 frame work 对齐到显示 timing pulse，使主线程状态更新与下一帧保持节奏一致。
* Android MessageQueue 的 sync barrier 可让与帧相关的 asynchronous message 越过普通同步消息，目标是保护 frame deadline。
* Apple RunLoop 的 Mode 决定当前处理哪些 Source、Timer 和 Observer；滚动期间进入 tracking mode 时，仅注册在 default mode 的 timer 可能延迟。
* Main Thread Blocking 会同时放大输入延迟和显示延迟：输入回调排队、动画无法推进、layout/draw 不能按时执行、下一帧反馈错过 deadline。
* 线程调度和 event-loop 排队属于两个层级：内核决定线程何时得到 CPU，event loop 决定该线程得到 CPU 后先执行哪个应用任务。

关键路径
--------

通用主线程路径：

::

   System Event / Timer / Frame Pulse / Posted Task
      → Event Loop Wakeup
      → Queue Selection
      → Main Thread Callback
      → UI State Change
      → Layout / Draw Request
      → Frame Commit
      → Visible Feedback

Android：

::

   InputChannel
      → Looper callback
      → ViewRootImpl input handling
      → App callback
      → invalidate / requestLayout
      → Choreographer doFrame
      → traversal / commit

Apple：

::

   UIKit Event Source
      → Main RunLoop
      → current RunLoop Mode
      → touch / gesture / control callback
      → layout / Core Animation transaction
      → frame feedback

概念辨析
--------

* **Thread Scheduler vs Event Loop**：Scheduler 分配 CPU；Event Loop 排列线程内部任务。
* **Looper vs Handler**：Looper 运行消息循环；Handler 只是向某个 Looper 的队列投递和处理消息的接口。
* **MessageQueue vs Choreographer**：MessageQueue 管通用主线程任务；Choreographer 专门组织与 frame timing 相关的输入、动画、遍历和提交。
* **RunLoop Source vs Timer**：Source 响应异步事件；Timer 在到期后变为可运行任务，但仍要等待线程获得执行机会。
* **RunLoop Mode vs Priority**：Mode 是监听集合，不是任务优先级本身。
* **Callback 完成 vs Frame 完成**：业务回调结束只是状态更新完成，后续仍需 layout、render、compose、present 才能形成用户可见反馈。

本章结论
--------

Main Thread 的本质是 UI 状态的唯一提交线，Event Loop 则决定这条线上的任务顺序。点击无反馈、滚动卡顿和动画延迟经常来自同一原因：输入、业务任务和 frame work 在主线程上争用时间。排查时应把“事件是否到达”“队列等了多久”“回调执行多久”“是否赶上下一帧”分开测量。