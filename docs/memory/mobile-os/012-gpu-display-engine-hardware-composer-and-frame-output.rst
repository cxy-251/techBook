第012章：GPU, Display Engine, Hardware Composer, and Frame Output
=================================================================

核心知识点
----------

* 一帧画面从 App 到屏幕要经过 App 渲染、buffer 生产、系统 compositor、Hardware Composer/显示控制器、VSync 和 panel scanout；“App 已经画完”不等于“用户已经看到”。
* GPU 负责执行 shader、纹理处理、几何、离屏 pass 和必要的 client composition，输出可被后续合成或扫描的图像 buffer。
* Display Engine/DPU 是固定功能显示硬件，负责 overlay plane、缩放、颜色转换、HDR、简单混合和最终 scanout。它比 GPU 更适合低功耗持续输出。
* 系统 compositor 收集来自多个 App 和 System UI 的 layer，结合 z-order、alpha、transform、dataspace 和 buffer readiness 决定当前帧如何合成。
* Android 的 HWC 角色负责在 SurfaceFlinger 与显示硬件之间决定哪些 layer 可直接由硬件 plane 处理，哪些必须先由 GPU 合成。Apple 虽公开命名不同，也需要解决相同的 layer composition 与 presentation 问题。
* Buffer 保存像素；Surface/drawable 是生产显示内容的接口；Layer 保存合成属性；BufferQueue/swapchain 管理多 buffer 轮换；framebuffer/client target 是某阶段合成后的目标。必须区分这些对象。
* Fence 用来表达 buffer 的异步完成与可用性。Producer 没写完，consumer 就不能读取；consumer 没释放，producer 就不能安全复用。
* VSync 是显示节拍。App、compositor 和 display 必须围绕固定 deadline 协作；错过当前周期通常意味着旧帧继续显示或新帧延迟到下一周期。
* Hardware overlay 能减少 GPU 合成和 DRAM 带宽，但受 plane 数量、格式、缩放、透明度、HDR、protected content 等硬件能力限制。
* 掉帧不应直接归因于 GPU。App 主线程迟交、GPU fence 晚、compositor 排队、HWC fallback、display mode 切换或 thermal throttling 都能造成同样的用户现象。

关键路径
--------

一帧输出：

::

   app updates UI
   → render commands
   → GPU writes buffer
   → buffer queued to system compositor
   → compositor latches ready layers
   → HWC / display engine selects composition
   → present fence
   → panel scanout on VSync

Buffer 生命周期：

::

   producer dequeue
   → render / write
   → queue with acquire fence
   → consumer acquire
   → compose / scanout
   → release fence
   → buffer reusable

掉帧定位：

::

   missed frame
   → app submitted on time?
   → GPU fence signaled on time?
   → compositor latched on time?
   → HWC used overlay or GPU fallback?
   → present / VSync / panel state normal?

概念辨析
--------

* **GPU rendering 与 display scanout**：GPU 生成像素或合成结果，display engine 按面板时序持续输出，两者职责不同。
* **Surface 与 Layer**：Surface 更接近内容生产目标，Layer 更接近系统合成时的内容与属性记录。
* **Hardware composition 与 GPU composition**：前者利用固定功能 plane，后者通过 shader 把多个 layer 合成到 client target。
* **VSync 与 FPS**：VSync 定义显示时序，App 实际 FPS 取决于是否能持续在每个 deadline 前提交新帧。
* **BufferQueue 与复制**：队列管理的是 buffer 所有权和轮转，不等于每帧都发生 CPU 像素复制。

本章结论
--------

手机显示是一条严格受 deadline 驱动的 buffer pipeline。理解掉帧、黑屏、延迟和功耗问题时，应沿 App render、GPU、buffer/fence、system compositor、HWC/display engine、VSync 和 panel 逐段检查，而不是把所有画面问题都归到 GPU。