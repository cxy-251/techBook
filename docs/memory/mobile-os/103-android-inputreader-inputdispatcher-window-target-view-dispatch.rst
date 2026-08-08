第103章：Android InputReader, InputDispatcher, Window Target, View Dispatch
==========================================================================

核心知识点
----------

* Android 输入主路径是 ``Touch Controller → Linux evdev → EventHub → InputReader → InputDispatcher → InputChannel → ViewRootImpl → View Tree``。
* EventHub 负责打开和读取 ``/dev/input/event*``，维护输入设备增删，向上提供统一 raw event 流。
* InputReader 负责设备识别、坐标归一化、display mapping、方向校准、pointer/tool 分类，并把 evdev 记录组装成 Android input event。
* InputDispatcher 负责窗口目标选择和事件队列管理；DOWN 建立 touched window，MOVE/UP 通常沿用当前 touch state。
* InputDispatcher 需要结合 focus、touchable region、window flags、display id、overlay 和现有连接状态决定事件去向。
* InputChannel 是 system input service 与 App 进程之间的传输边界；App 侧 WindowInputEventReceiver 在主线程 Looper 上接收事件。
* ViewRootImpl 把系统事件送入 DecorView / ViewGroup / View；``dispatchTouchEvent``、``onInterceptTouchEvent``、``onTouchEvent`` 决定 View 层最终消费关系。
* 系统发送事件后需要等待 App 完成信号；主线程长时间不处理会导致 wait queue 堆积，最终进入 input dispatch timeout / ANR。
* 输入 ANR 的根因通常不是 InputDispatcher 自身“慢”，而是目标窗口、App 主线程或同步等待导致事件无法及时完成。

关键路径
--------

::

   /dev/input/event*
      → EventHub.read
      → InputReader normalize / map display
      → InputDispatcher choose target window
      → InputChannel
      → WindowInputEventReceiver
      → ViewRootImpl
      → DecorView.dispatchTouchEvent
      → ViewGroup interception
      → View.onTouchEvent
      → finishInputEvent

定位点击无响应时：

::

   getevent 是否有事件
      → InputReader 坐标是否正确
      → InputDispatcher 选中哪个窗口
      → InputChannel 是否正常
      → Main Thread 是否及时运行
      → View 是否拦截 / 消费

概念辨析
--------

* **EventHub vs InputReader**：EventHub 负责“读 raw event”；InputReader 负责“理解设备并转换事件”。
* **InputReader vs InputDispatcher**：Reader 解决事件是什么；Dispatcher 解决事件发给谁。
* **Focused Window vs Touched Window**：按键通常依赖 focus；触摸目标由 DOWN 坐标与窗口可触区域决定。
* **InputChannel vs Binder**：InputChannel 是高频输入传输通道；Binder 更常承担控制面和系统服务调用，两者职责不同。
* **View Interception vs Window Dispatch**：Window Dispatch 发生在系统进程；View interception 发生在目标 App 内部。
* **Input Delay vs ANR**：短延迟只表现为跟手差；长时间不能完成输入处理会升级为系统超时和 ANR。

本章结论
--------

Android 输入链路最重要的两个边界是 ``InputReader → InputDispatcher`` 与 ``InputDispatcher → InputChannel → ViewRootImpl``。前者把硬件事件变成系统事件，后者把系统窗口决策交给 App。排查输入问题时必须先确定事件在哪一层消失或等待，再进入 View 业务逻辑。