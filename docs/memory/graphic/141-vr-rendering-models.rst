第141章：VR 渲染模型
====================

核心知识点
----------

VR 帧围绕 Runtime 与 Predicted Display Time 组织
   普通实时渲染围绕单相机与 back buffer；VR 每帧要等待 runtime 给出目标显示时刻，再基于同一时间标签查询 head/eye pose、构造左右眼 view/projection、渲染 swapchain image 并提交 composition layer。

空间闭环要求左右眼数据来自同一预测时刻
   Left/right eye pose、FOV、view matrix、projection matrix、viewport 和 target layer 必须属于同一 frame。任一眼沿用旧矩阵或错误 layer，近距离几何会立即表现为重影、尺度异常或深度反转。

Stereo Rendering 的差异来自真实双眼基线
   IPD 决定两眼观察点间距；近物产生更大视差，远物视差更小。应用不应自行伪造左右眼偏移，而应使用 runtime 返回的 eye pose 与 per-eye FOV。

Per-Eye Render Target 可以采用多种布局
   独立 texture、texture array layer 或单大纹理分区都可行。真正需要保持一致的是 eye→viewport→depth→array layer→submit sub-image 的映射。

Single-Pass Stereo 主要减少重复提交
   一份 geometry/material state 可以为多个 view 执行，shader 通过 view index 读取不同矩阵并写入对应 layer。它能减少 CPU command 与部分 vertex work，但左右眼 fragment、depth 与 screen-space 结果仍然不同。

VR 基础循环有固定生命周期
   Runtime events → wait frame → begin frame → locate views → acquire/wait swapchain image → render views → release image → submit layer → end frame。黑屏、拉伸、单眼错误都应沿这条生命周期检查。

Swapchain Image 有 Runtime 所有权约束
   XR image 不能按普通自有 RT 使用。必须遵守 acquire、wait、render、release、submit 顺序，并把底层 Vulkan/D3D/Metal/OpenGL 状态同步封装进 XR backend。

畸变与 Late-Stage Reprojection 通常由 Runtime 负责
   应用提交线性渲染结果、pose/FOV 与 sub-image，runtime 根据设备镜片与最新追踪数据完成 distortion、reprojection 与最终 compositor 合成。应用不应把重投影视为长期超预算的替代品。

Motion-to-Photon 是 VR 延迟的真实观察对象
   Sensor/pose age、CPU queue、GPU pass、runtime compositor、display scanout 都会进入最终延迟。GPU frame time 达标并不保证头动反馈及时。

Frame Deadline 比平均 FPS 更重要
   90Hz 单刷新槽约 11.11ms，120Hz 约 8.33ms。偶发长帧会触发 dropped frame、旧帧复用或 reprojection，即使平均 FPS 看起来正常，仍会明显破坏舒适性。

Deferred Rendering 在 VR 中会放大带宽成本
   双眼高分辨率意味着 G-buffer、MSAA、resolve、透明合成和 screen-space pass 的读写量成倍增加。移动头显通常更偏向 forward/forward+ 或混合路径，以降低 MRT 与带宽压力。

透明对象与 UI 需要独立处理
   Glass、particle、volume、spatial UI 往往不适合直接塞进 deferred G-buffer。它们应在 per-eye depth 约束下走 forward/composition layer，并避免单眼 screen-space 假设。

Dynamic Quality 应服务帧稳定
   Dynamic resolution、LOD、MSAA、shadow、post-process、particle 与 foveation 应由同一质量控制器管理。目标是稳定命中 frame deadline，同时避免左右眼质量不一致和清晰度剧烈跳变。

Thermal 与 Battery 是独立头显的重要约束
   短时间 GPU 达标不代表持续体验稳定。移动 XR 需要同时观察 GPU/CPU time、thermal level、电池和 refresh mode，并使用带迟滞的质量档位避免频繁震荡。

VR 调试先查时序，再查画面
   头动漂移优先检查 predicted display time、pose query 与 queue depth；深度异常查 eye pose/projection/IPD；单眼问题查 layer/viewport；dropped frame 再拆 GPU pass 与 bandwidth。

关键路径
--------

一帧 VR：

::

   runtime wait frame
   → predicted display time
   → locate left/right views
   → build per-eye view/projection
   → acquire swapchain image
   → render stereo views
   → release image
   → submit projection layer
   → runtime distortion/reprojection/composition
   → display

双眼问题排查：

::

   stereo artifact
   → verify same frame time
   → verify eye pose/FOV
   → verify view/projection matrices
   → verify viewport/depth/array layer
   → verify submitted sub-image and pose

性能稳定：

::

   missed frame or judder
   → record CPU/GPU/compositor timing
   → inspect pose age and queue depth
   → split expensive passes
   → reduce G-buffer/MSAA/post cost
   → apply dynamic resolution/LOD/foveation
   → verify dropped frame and reprojection rate

概念辨析
--------

* **GPU Frame Time 与 Motion-to-Photon**：前者只是应用 GPU 阶段，后者包含追踪、队列、compositor 与显示。
* **Stereo Rendering 与 Duplicate Image**：双眼不是复制同一图像，而是不同 eye pose 与 projection 的同一世界状态。
* **Single-Pass Stereo 与 Single View**：single-pass 只减少重复提交，仍然存在多个独立 view 输出。
* **Reprojection 与 New Rendering**：reprojection 修正已有图像的姿态关系，无法生成未渲染的新遮挡内容。
* **Deferred VR 与 Ordinary Deferred**：算法相同，但双眼分辨率、MSAA、frame deadline 与 compositor 让资源成本更严格。
* **Average FPS 与 Frame Stability**：平均值不能描述 missed slot、长尾帧和长期 reprojection。

本章结论
--------

VR 渲染应按“Runtime Timing—Predicted Pose—Stereo Views—Swapchain—Per-Eye Rendering—Composition—Deadline—Comfort”理解。稳定体验的核心是让左右眼使用同一目标显示时间下的空间状态，严格遵守 runtime 图像生命周期，并让应用 CPU/GPU 工作持续低于帧预算，为 compositor 和最终重投影保留余量。