第104章：Apple Touch Event, RunLoop, Responder Chain, Gesture Recognizer
=======================================================================

核心知识点
----------

* Apple 公开可解释的输入链路是 ``System Event Boundary → UIApplication → UIWindow → Hit Test → UIGestureRecognizer / UIView / UIControl → Responder Chain``。
* Apple 更底层的触摸 driver、系统事件 daemon 和窗口服务包含私有实现；稳定分析应以 UIKit / Foundation 的公开对象和可观察行为为边界。
* ``UIEvent`` 组织输入事件，``UITouch`` 表示一个持续触点，常见 phase 为 began、moved、stationary、ended、cancelled。
* ``UITouch.timestamp`` 表示触摸事实发生的时间；回调执行时间还包含主线程排队成本，两者不能混用。
* UIKit 输入最终在主线程 RunLoop 上处理；主线程若执行同步 I/O、复杂布局或长任务，事件即使已经到达 App，也会延迟进入业务回调。
* Hit Testing 从 ``UIWindow`` 沿 View 层级选择初始目标；透明视图、``userInteractionEnabled``、hidden、alpha、坐标转换都会影响命中结果。
* ``UIGestureRecognizer`` 观察触摸序列并通过状态机解释语义；多个 recognizer 可通过 failure dependency、delegate 与 simultaneous recognition 协调竞争。
* Responder Chain 负责把当前对象未处理的事件或 action 继续向上交给 UIView、UIViewController、UIWindow、UIApplication 等 responder。
* ``UIControl`` 的 control event、UIView 原始 touch 回调、UIGestureRecognizer 和 Responder Chain 属于不同层级，排查时必须区分。

关键路径
--------

::

   Touch
      → system event boundary
      → UIApplication / main RunLoop
      → UIWindow
      → hitTest
      → target UIView
      → attached UIGestureRecognizer(s)
      → UIControl / UIView handling
      → Responder Chain if needed
      → business callback
      → layout / Core Animation commit
      → visible feedback

点击按钮无响应时：

::

   事件是否进入 App
      → Main Thread 是否阻塞
      → UIWindow / Hit Test 是否命中目标
      → Gesture 是否取消或延迟触摸
      → UIControl / View 是否处理
      → Responder / Controller 逻辑是否执行

概念辨析
--------

* **UITouch vs UIGestureRecognizer**：UITouch 是触点事实；Recognizer 是对一段触摸序列的语义解释器。
* **Hit Test vs Responder Chain**：Hit Test 决定初始目标；Responder Chain 决定未处理事件或 action 如何继续传播。
* **RunLoop Mode vs Thread**：Mode 是同一线程 RunLoop 当前监听的一组 source/timer；并不是另一条线程。
* **View Touch Handling vs UIControl Event**：UIView 可直接处理 touches；UIControl 在其上封装 pressed/highlighted/action 等控件语义。
* **Model State vs Visible Feedback**：业务状态已经修改，并不代表屏幕已经显示；还需要布局、Core Animation transaction 与后续 frame pipeline。

本章结论
--------

Apple 输入问题应从主线程边界向内收缩：先确认事件是否进入 App 和 RunLoop，再检查 Hit Test，再看 Gesture Recognizer 竞争，最后检查 UIControl、UIView 和 Responder Chain。私有系统实现无需猜测，公开对象已经足以定位绝大多数 App 侧输入问题。