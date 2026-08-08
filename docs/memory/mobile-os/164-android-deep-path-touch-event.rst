第164章：Android Deep Path Touch Event
======================================

核心知识点
----------

* Android 触摸主链是 ``Touch Controller → Kernel Input Driver / evdev → EventHub → InputReader → InputDispatcher → Window Target → InputChannel → ViewRootImpl → View Tree → Handler → Next Frame``。
* 触控硬件负责采样接触位置、面积、压力近似值、多点关系和时间；固件还可能做去噪、边缘抑制、手掌识别、湿手/手套模式等过滤。
* Kernel input driver 把设备私有信号转换成 Linux input protocol，并通过 ``/dev/input/event*`` 暴露给用户空间。普通 App 不直接读取这些节点。
* 多点触控常使用 slot/tracking-id 模型；``ABS_MT_POSITION_X/Y``、``ABS_MT_TRACKING_ID`` 和 ``SYN_REPORT`` 等描述接触状态，而不是 Android 的“点击”语义。
* ``EventHub`` 发现和读取 evdev 设备；``InputReader`` 负责设备配置、坐标归一化、display 映射和 Android input event 语义化。
* ``InputDispatcher`` 持有窗口、display、touchable region、focus、InputChannel 和 pending event 状态，并决定事件投递给哪个窗口。
* Touch target 与 keyboard focus 不是同一概念。一次手势的 ``ACTION_DOWN`` 通常确定后续事件目标，除非窗口消失、策略取消或通道断开。
* ``InputChannel`` 是系统到 App 的跨进程投递边界。App 进程由 ``WindowInputEventReceiver / ViewRootImpl`` 接收事件，再进入 DecorView、ViewGroup 和目标 View。
* ``ViewGroup`` 可以在 ``dispatchTouchEvent`` / ``onInterceptTouchEvent`` 中改变子 View 的事件归属；GestureDetector、RecyclerView、Compose 等会在 App 内继续构建更高层手势状态机。
* 主线程是输入消费的关键执行线。事件已经到达 App 后，主线程被同步 I/O、锁、Binder 或长任务阻塞，用户仍会感觉“点了没反应”。
* 输入完成不等于视觉反馈完成。业务回调后还要经历 Choreographer、layout/draw、RenderThread、GPU、SurfaceFlinger 和 display 才能看到响应。
* ANR 输入超时是系统观察到目标窗口长期未完成事件处理的结果；根因可能是 App 主线程，也可能是它同步等待下游服务或资源。

关键路径
--------

::

   Finger contact
   → touch controller / firmware
   → kernel input driver
   → /dev/input/event*
   → EventHub
   → InputReader
   → InputDispatcher
   → touched/focused window policy
   → InputChannel
   → ViewRootImpl
   → DecorView / ViewGroup / View
   → onTouch / gesture / onClick
   → invalidate / state update
   → next rendered frame

概念辨析
--------

* **Raw Touch 与 MotionEvent**：raw touch 是硬件/内核接触事实，MotionEvent 是 Android 输入栈归一化后的应用语义对象。
* **InputReader 与 InputDispatcher**：前者读取、转换和归一化事件；后者选择目标窗口并负责投递、队列和超时。
* **Focus Window 与 Touch Target**：键盘焦点窗口不必等于当前触摸手势的目标窗口。
* **Input Latency 与 Frame Latency**：事件到 App 的时间属于输入延迟；App 处理后到像素显示还要加渲染和显示延迟。
* **ANR 与丢触**：ANR 常是目标已明确但 App 响应超时；硬件/驱动真正丢事件时，上层可能根本没有收到完整手势。

本章结论
--------

触摸问题应按 ``采样事实 → 内核事件 → 系统目标选择 → App 投递 → 主线程消费 → 视觉反馈`` 分层。先确定事件最远到达哪一层，再检查该层之后的第一个异常时间段。