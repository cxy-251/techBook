第173章：Apple Deep Path Touch Event
====================================

核心知识点
----------

* Apple Touch Path 可压缩为 ``Touch Controller → Driver / System Input → App Main RunLoop → UIKit UIEvent / UITouch → Hit-Testing → Gesture / Responder → App Callback → Frame Feedback``。
* App 能稳定依赖的是 ``UIEvent``、``UITouch``、``UIView``、``UIControl``、``UIGestureRecognizer`` 和 responder chain；触摸控制器、私有 driver 与系统输入服务属于封闭边界。
* ``UITouch.timestamp`` 保留输入时间基，可用于估算触摸到 App 回调的可见延迟；coalesced touches 保存历史采样，predicted touches 是短期预测值。
* Hit-testing 决定初始目标 view；Responder Chain 决定事件无法由当前 responder 处理时如何向上转交，两者不是同一个过程。
* ``UIGestureRecognizer`` 是对 touch sequence 的状态机解释，存在 failure dependency、simultaneous recognition、cancellation 等竞争关系。
* ``UIControl`` 的 target-action 是控件语义，``UIView`` touch 方法是原始 UIKit touch handling，gesture callback 又是另一层语义封装。
* 主线程 RunLoop 同时承担输入、timer、layout、animation 和 transaction commit；主线程长任务会推迟输入处理和下一帧反馈。
* 用户感觉“触摸慢”时，需要把输入投递延迟与显示反馈延迟分开；事件已经到达 App 后仍可能因主线程或图形管线错过帧。

关键路径
--------

* 单次点击路径：``finger down → hardware sample → system input event → main RunLoop → UIWindow hitTest → target UIView/UIControl → gesture/responder → callback``。
* 手势路径：touch sequence 同时被 view 与 gesture recognizer 观察；recognizer 根据移动、时间和依赖关系进入 began/changed/ended/failed/cancelled。
* UIControl 的 ``touchUpInside`` 只有在 down/up 序列满足控件规则时产生，不等于每个 ``UITouch`` 都会触发 control action。
* 延迟诊断先比较 ``touch.timestamp`` 与 callback time；若到 App 前已积累明显延迟，再怀疑系统输入/调度；若 callback 及时但画面慢，继续看主线程和 frame pipeline。
* 滚动期间 RunLoop mode 可能改变 timer/source 的执行条件；同时主线程上的同步 I/O、锁、长计算会直接挤占触摸和绘制预算。
* 系统全局断触、漂移、多指异常优先指向 hardware/driver/system input；单页面或单控件异常优先检查 hit-test、gesture 和 App code。

概念辨析
--------

* ``Hit-Testing`` 负责找初始 view target；``Responder Chain`` 负责 responder 之间的后续传递，不能混为一谈。
* ``UITouch`` 是 UIKit 暴露的触摸对象；``Gesture`` 是 framework 从一串 touch 中派生的语义状态。
* ``Coalesced touch`` 是真实历史采样；``Predicted touch`` 是系统预测结果，只适合低延迟视觉优化。
* ``Touch callback latency`` 与 ``touch-to-display latency`` 不同，后者还包括布局、Core Animation、GPU 和 display present。
* ``touchesCancelled`` 是合法的状态转移，可能来自 gesture 接管、系统策略或目标失效，不应简单视为“事件丢了”。

本章结论
--------

Apple 输入系统的稳定阅读顺序是先确认 touch sequence，再确认 hit-test 目标，再看 gesture/responder 竞争，随后检查主线程处理，最后验证下一帧反馈。把触摸路径和渲染路径分开再串联，才能准确解释“点击没反应”“手势抢占”“滑动卡顿”和“输入到了但反馈晚”等现象。