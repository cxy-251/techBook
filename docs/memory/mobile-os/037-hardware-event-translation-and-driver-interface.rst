第037章：Hardware Event Translation and Driver Interface
=========================================================

核心知识点
----------

* Hardware event 先以电气信号、IRQ、FIFO 水位或 DMA completion 的形式进入系统；driver 再把它转换成带设备身份、时间戳、状态和错误语义的 kernel event。
* 移动硬件事件通常沿 ``Hardware → IRQ → Driver → Kernel Event → HAL / Daemon → System Service → Framework → App`` 上行。
* Interrupt handler 应尽量短，只确认来源、ack/mask、保存最小状态并安排 deferred work；复杂解析、总线访问、buffer 处理和上层通知应移到 threaded IRQ、workqueue 或其它可调度上下文。
* Event reachability 受 device state 与 power state 约束。设备处于 runtime suspend、system suspend 或低功耗模式时，只有被配置成 wake source 的事件才能拉起完整处理路径。
* Runtime PM 通过 usage counter、autosuspend、runtime suspend/resume 和 wakeup capability 在响应速度与待机功耗之间取舍。
* Driver interface 应区分控制面和数据面。控制面负责 capability query、configure、start/stop、route、rate、power、flush；数据面负责 frame、sample、event、timestamp、buffer、fence 和 completion。
* Touch、camera、audio、sensor 的数据量不同，但都遵循“硬件状态 → driver 统一表达 → system service 加入平台语义 → App callback”的转换模型。
* Driver 到 system service 的常见交接形式包括 device node、read/poll/ioctl、shared buffer、event queue、HAL callback、Binder/XPC 或 daemon event。
* 稳定 driver interface 必须明确 version、capability、buffer ownership、ordering、timestamp、error semantics 和 lifecycle，否则 framework 很难跨设备长期兼容。
* App 没收到事件不等于硬件没工作；问题可能停在 IRQ、driver 解析、power resume、event queue、HAL callback、service 分发或 App 主线程消费任一层。

关键路径
--------

触摸事件：

::

   touch controller samples contact
   → IRQ line
   → kernel IRQ dispatch
   → driver threaded handler
   → parse coordinates and timestamp
   → kernel input event queue
   → input service
   → target window
   → App callback

Runtime PM：

::

   active
   → idle
   → autosuspend
   → runtime suspended
   → wake IRQ or client request
   → runtime resume
   → restore registers / clocks
   → event path active

接口分层：

::

   control path: capability → configure → start / stop / flush
   data path: hardware data → buffer / event → timestamp → callback

概念辨析
--------

* **Hardware signal 与 kernel event**：前者只表示设备状态变化，后者已经被 driver 结构化为系统可消费语义。
* **Top half 与 deferred work**：前者强调快速确认事件，后者承担可阻塞、可排队的完整处理。
* **Device active 与 wake-capable**：设备运行时能产生事件，不代表 system suspend 时也有资格唤醒整机。
* **Control plane 与 data plane**：控制面决定设备怎么工作；数据面承载设备已经产生的结果。
* **Event delivered 与 App handled**：system service 已分发事件后，App 主线程仍可能因阻塞或调度延迟而晚处理。

本章结论
--------

Driver interface 的核心任务是把硬件时序转换成系统时序。分析事件链时，应同时追踪 IRQ/deferred work、device power state、control/data contract 和上层分发；只有把事件线、状态线和接口线放在一起，才能判断“硬件已经发生”为什么最终没有变成 App 可见行为。