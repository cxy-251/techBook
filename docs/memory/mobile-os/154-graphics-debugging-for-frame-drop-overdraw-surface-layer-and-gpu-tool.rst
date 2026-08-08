第154章：Graphics Debugging for Frame Drop Overdraw Surface Layer and GPU Tool
===============================================================================

核心知识点
----------

* 图形调试的核心不是“页面复杂不复杂”，而是先锁定某一帧，再判断延迟发生在 ``Input / Main Thread → Render Thread → GPU → Compositor → Display`` 的哪一段。
* Frame drop 表示画面未在目标刷新周期内完成。60Hz 的直觉预算约 16.67ms，120Hz 约 8.33ms，但真实判断应以 expected present、actual present、frame deadline 与 jank reason 为准。
* 一次掉帧可能来自主线程 layout / draw record、RenderThread、GPU workload、buffer queue、fence wait、系统合成或 display present；不能看到 GPU 活跃就直接归因 GPU。
* ``Layout cost`` 是 CPU/UI framework 负载，``Overdraw`` 是像素重复覆盖，``GPU cost`` 是 shader、texture、blend、fill rate、bandwidth、offscreen pass 等 GPU 负载，三者属于不同责任层。
* Android 图形诊断应优先组合 Perfetto FrameTimeline、App Main/RenderThread、SurfaceFlinger layer/fence 和 Android GPU Inspector。
* FrameTimeline 用 expected / actual timeline 判断 App frame 与 SurfaceFlinger frame 是否按时完成；它负责指出“哪一帧晚了”，不直接替代根因分析。
* Surface / Layer 状态用于判断 z-order、visible region、alpha、crop、buffer、composition type 和 fence。App 已按时提交 buffer 时，late present 仍可能来自合成链。
* GPU 工具负责回答 GPU 是否饱和，以及具体 render pass、draw call、texture upload、shader、bandwidth 是否构成瓶颈。
* Apple 侧常用 Core Animation Instrument、Metal System Trace、GPU Counters 与 GPU Capture。它们分别观察 layer/commit、command buffer/GPU timeline、硬件计数器与单帧 GPU workload。
* ``VSync`` 是显示节奏基准，``Buffer Queue`` 是生产者与消费者之间的缓冲边界，``Fence`` 表示异步工作完成条件，``Present Time`` 表示帧真正进入显示的时刻。
* Buffer stuffing、queue stall、late fence、missed VSync 都可能表现为卡顿；必须沿同一帧的 producer → compositor → display 路径确认谁最先迟到。
* 高刷新率会缩短单帧预算，因此原本在 60Hz 可接受的 layout、shader 或 composition 工作，在 120Hz 下可能持续成为 jank 来源。

关键路径
--------

Android 掉帧定位：

::

   identify janky frame in FrameTimeline
   → inspect Main Thread / RenderThread
   → did App submit buffer on time?
   → inspect SurfaceFlinger layer + fence
   → inspect composition / HWC decision
   → inspect GPU workload with AGI
   → compare expected present vs actual present
   → assign App / GPU / compositor / display boundary

单帧责任链：

::

   input event
   → state / layout / draw record
   → render submission
   → GPU execution
   → queue buffer
   → compositor latch / composition
   → fence completion
   → display present at VSync

概念辨析
--------

* **Frame Drop 与 ANR**：frame drop 是帧截止时间未满足；ANR 是更长时间的应用响应失败，两者时间尺度不同。
* **Overdraw 与 Layout Cost**：overdraw 主要增加绘制/GPU 负载，layout cost 主要占用主线程 CPU 时间。
* **GPU Slow 与 Composition Slow**：GPU slow 是应用或合成 GPU 工作本身过长，composition slow 还可能来自 layer、HWC、fence 和 buffer 状态。
* **Buffer Queue 与 Fence**：queue 管理 buffer 的生产/消费关系，fence 表达某项异步 GPU/硬件工作何时完成。
* **Expected Present 与 Actual Present**：前者是系统目标显示时间，后者是帧真实显示时间；两者偏差是判断 jank 的关键证据。

本章结论
--------

图形调试的稳定方法是 ``锁定慢帧 → 判断 App 是否按时产出 → 判断 GPU 是否按时完成 → 判断合成器是否按时提交 → 判断 Display 是否按时 present``。只有沿同一帧时间线完成闭环，才能把“卡顿”准确归因到 UI、GPU、Surface/Layer、合成或显示节奏。