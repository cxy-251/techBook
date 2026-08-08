第165章：Android Deep Path Frame Rendering
==========================================

核心知识点
----------

* Android View 一帧主链是 ``State Change → invalidate/requestLayout → Choreographer#doFrame → Main Thread Traversal → RenderNode/Display List → RenderThread → Skia/GPU → Surface/BufferQueue → SurfaceFlinger → HWC → Display Controller → Panel``。
* ``invalidate`` 主要请求重绘，``requestLayout`` 会触发 measure/layout，影响范围和成本通常更大。
* Main Thread 在同一个 Looper 上竞争输入、生命周期、业务消息、动画、measure/layout/draw；任何长任务都会压缩一帧的时间预算。
* ``Choreographer`` 用 VSync 节奏协调 input、animation、traversal 等帧工作。刷新率越高，单帧预算越小：60Hz 约 16.67ms，120Hz 约 8.33ms。
* View 层把 UI 状态记录为 Display List / RenderNode 等渲染描述；``RenderThread`` 负责消费这些状态并驱动 Skia 图形后端。
* Skia 可通过 OpenGL ES/Vulkan 等后端生成 GPU command。CPU 提交完成不等于 GPU 已完成，后续阶段依赖 fence 判断 buffer 是否可消费。
* ``Surface`` 是 producer 端接口；``BufferQueue`` 管 producer/consumer 间的 GraphicBuffer 生命周期；fence 用于同步 ownership 和 GPU/consumer 时序。
* SurfaceFlinger 持有全局 Layer/Transaction 状态，latch 各 producer 的 buffer，并决定每层的 composition 方式。
* Hardware Composer 结合 overlay plane、格式、缩放、旋转、HDR、带宽等能力决定 device/client composition，随后把结果交给 display controller。
* 一帧掉帧必须先定位“最早迟到边界”：App main thread、RenderThread、GPU completion、BufferQueue、SurfaceFlinger composition、HWC/display 都可能产生相同的可见 jank。
* ``FrameTimeline`` 在现代 Android 中把 expected/actual frame、App 与 SurfaceFlinger 的时间线放在一起，是定位 missed frame 的核心证据。
* 主线程正常并不代表 GPU 正常；GPU 正常也不代表 SurfaceFlinger/display 一定按时 present。帧分析必须覆盖整条 producer→consumer→present 链。

关键路径
--------

::

   App state changes
   → invalidate / requestLayout
   → VSync / Choreographer#doFrame
   → input + animation + measure + layout + draw
   → RenderNode / display list sync
   → RenderThread
   → Skia → GPU commands
   → dequeue / render / queue GraphicBuffer
   → BufferQueue + fence
   → SurfaceFlinger latch Layer
   → composition decision
   → Hardware Composer
   → display controller
   → panel scanout

掉帧定位：

::

   expected frame deadline
   → App finished on time?
   → RenderThread/GPU finished on time?
   → buffer queued/latch on time?
   → SurfaceFlinger composed on time?
   → HWC/present on time?
   → first late boundary = primary suspect

概念辨析
--------

* **invalidate 与 requestLayout**：前者偏内容重绘，后者要求重新计算 View 尺寸/位置。
* **Main Thread 与 RenderThread**：主线程负责 UI 状态和 traversal，RenderThread 负责大量渲染执行；二者仍需同步。
* **Surface 与 BufferQueue**：Surface 是 producer API，BufferQueue 是跨生产者/消费者管理 buffer 的队列机制。
* **App Rendering 与 System Composition**：App 生成自身窗口 buffer，SurfaceFlinger 合成全局所有可见 layer。
* **Jank 与 GPU 慢**：GPU 慢只是 jank 的一种来源，main/render/queue/compositor/display 任一阶段迟到都可掉帧。

本章结论
--------

Android 帧渲染必须按 ``App → Render → GPU → Buffer → Compose → Present`` 阅读。诊断时不要从最终 late present 反推原因，而要沿 FrameTimeline 找到第一个超过 deadline 的责任边界。