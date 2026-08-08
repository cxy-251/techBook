第101章：Touch Controller, Driver, Input Queue, Event Dispatch
==============================================================

核心知识点
----------

* Touch Controller 把电容、压力、接触面积等物理信号转换成 raw coordinate、timestamp、tracking id、tool type 等输入材料。
* 采样频率决定输入事实的时间密度；更高采样率只能缩短“观察手指变化”的间隔，不能单独保证界面低延迟。
* 输入触发通常采用 interrupt-driven，移动事件也可能批量上报；系统需要在响应速度、唤醒次数和功耗之间取舍。
* Kernel Driver 的核心职责是 ``去噪 → 校准 → 坐标映射 → 协议转换 → 能力声明``，把设备私有协议转换成统一 input event。
* Input Queue 保证 DOWN/MOVE/UP/CANCEL 的时间顺序，并吸收 producer 与 consumer 速度差；MOVE 可以合并，但触摸状态边界必须保留。
* Event Dispatch 的系统任务是根据 display、window stack、touchable region、focus、overlay、当前 touch state 选择目标窗口。
* 一次 DOWN 通常建立本轮触摸目标，后续 MOVE/UP 沿用既有触摸状态；窗口变化、系统手势或失效连接可能触发 CANCEL。
* 输入路径上的延迟可来自硬件采样、driver、queue、window dispatch 和 App main thread，不能把所有问题都归因于“屏幕”或“App 卡”。

关键路径
--------

::

   Touch Controller sample
      → interrupt / polling
      → Kernel Driver read
      → filtering / calibration / coordinate mapping
      → standardized input events
      → Input Queue
      → target window selection
      → event dispatch
      → App main thread
      → UI feedback

稳定排查顺序：

::

   raw data 是否连续
      → timestamp 是否稳定
      → 坐标映射是否正确
      → queue 是否积压
      → target window 是否正确
      → App 是否及时消费

概念辨析
--------

* **Interrupt vs Polling**：Interrupt 在状态变化时唤醒处理器；Polling 按周期主动读取。前者更省空闲功耗，后者节奏更固定。
* **Tracking ID vs Coordinate**：Coordinate 表示当前位置；Tracking ID 表示“这一系列采样属于同一个触点”。
* **Filtering vs Latency**：滤波越强，噪声越小，但也可能增加跟手延迟；两者是硬件输入调优中的直接取舍。
* **Queueing vs Coalescing**：Queueing 保存待处理事件；Coalescing 把连续 MOVE 样本合并交付，目标是降低回调频率而非丢失时间事实。
* **Focus Window vs Touched Window**：键盘输入通常依赖 focus；触摸 DOWN 更依赖坐标命中的 touched window。

本章结论
--------

输入系统的底层任务不是识别业务手势，而是把不稳定、设备私有的触摸事实转换成有序、可映射、可分发的系统事件。定位触摸异常时，先验证 raw data 和 driver，再检查队列与窗口选择，最后进入 App 主线程与 UI Framework。