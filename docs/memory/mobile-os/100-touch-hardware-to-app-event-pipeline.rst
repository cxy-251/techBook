第100章：Touch Hardware to App Event Pipeline
=============================================

核心知识点
----------

* 触摸输入是一条 ``Hardware → Kernel Driver → System Input Service → Window Target → UI Framework → App Callback`` 的责任链。
* Touch Controller 只负责采样接触点：坐标、时间戳、tracking id、接触面积、压力估计和工具类型；它不知道按钮、窗口或业务语义。
* Kernel input driver 把 I2C/SPI/firmware 私有数据转换成统一输入事件；Linux 多点触控常用 slot、``ABS_MT_TRACKING_ID`` 和 ``SYN_REPORT`` 表达触点生命周期与采样批次。
* System Input Service 将 raw event 转成平台事件，完成坐标归一化、显示映射、旋转、设备分类、手势区域与系统策略过滤。
* 输入事件从系统进入 App 前必须先选择目标窗口；进入 App 后再由 View/Responder/gesture system 把坐标序列升级为控件或手势语义。
* Input Queue 用于吸收硬件采样速度与 App 消费速度的差异；时间戳必须保留，否则无法区分采样延迟、排队延迟和处理延迟。
* MOVE 事件可以合并或批量交付；DOWN、UP、CANCEL 等状态边界决定触摸序列生命周期，不能简单丢弃。
* 用户真正感知的是 ``touch-to-display``，因此输入链路最终必须和下一帧渲染、合成、显示时间线连接起来。

关键路径
--------

::

   手指接触
      → Touch Controller 采样
      → Driver 读取 firmware / register / FIFO
      → Kernel input event
      → System Input Service 归一化坐标与事件语义
      → Input Queue
      → Window Target Selection
      → App Event Receiver
      → View / Responder / Gesture
      → App 状态更新
      → 下一帧显示反馈

Android 的典型公开路径是：

::

   Touch Controller
      → Linux evdev
      → EventHub
      → InputReader
      → InputDispatcher
      → InputChannel
      → ViewRootImpl
      → View Tree

概念辨析
--------

* **Raw Touch vs System Event**：Raw Touch 是触点事实；System Event 已包含坐标映射、事件阶段和系统策略。
* **Pointer ID vs Pointer Index**：ID 在同一触摸生命周期中保持身份；Index 只是当前事件对象中的数组位置。
* **采样率 vs 刷新率**：采样率决定输入事实密度；刷新率决定屏幕展示机会，两者并不相等。
* **Event Time vs Delivery Time**：前者描述输入发生时间，后者描述事件到达某层的时间；两者差值就是队列和调度成本的一部分。
* **输入成功 vs UI 有反馈**：事件成功到达 App 仍可能因主线程阻塞、渲染晚交或 missed frame 导致用户感觉“点了没反应”。

本章结论
--------

触摸事件的语义会沿系统层级逐步升级：硬件提供触点，内核提供标准事件，系统服务决定坐标和窗口归属，UI Framework 决定控件与手势，App 才产生业务意图。排查触摸问题时应按 ``采样 → 标准化 → 排队 → 窗口目标 → App 分发 → 帧反馈`` 顺序定位。