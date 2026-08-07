第142章：Foveated Rendering
===========================

核心知识点
----------

Foveated Rendering 本质上是按视觉敏感度分配像素预算
   用户注视点附近保持完整分辨率与 shading rate，周边区域降低着色频率、采样密度或 render resolution。它的目标不是简单降分辨率，而是在用户最敏感区域保留清晰度，同时压缩高刷新率 XR 的片元与带宽成本。

中心视觉与周边视觉承担不同风险
   中心区最敏感于文字、细线、UI、材质高频和几何边缘；周边区虽然对细节分辨率较低，却仍然敏感于闪烁、亮度跳变、运动和深度错位。因此周边可以降细节，不能破坏时间稳定与运动线索。

Gaze 数据必须同时对齐空间与时间
   Eye tracker 输出 gaze ray、confidence 与 sample time；渲染器真正需要的是 predicted display time 下的 per-eye gaze point。旧 gaze 会让清晰区落在用户已经离开的区域。

左右眼应独立生成 Gaze Point
   Head/eye space gaze ray 要分别投影到左右眼 view/projection 和 eye buffer 坐标中。IPD、非对称 frustum、lens distortion 与 viewport 都会影响最终 rate map 位置。

低置信度与快速扫视应采取保守策略
   眼动不稳定时，应扩大 foveal radius 与 transition region，而不是继续使用激进周边降采样。牺牲部分收益比把低清晰区域放到用户当前注视点更安全。

常见实现分为 VRS 与 Multi-Resolution Rendering
   VRS/shading-rate image 让 tile 使用不同着色频率；多分辨率方案分别渲染中心、过渡和周边区域，再重建到 eye buffer。前者依赖硬件/API 能力，后者更通用但增加合成与采样坐标复杂度。

Rate Map 应是独立可观察资源
   每个 tile 的 shading rate、中心半径、过渡半径、gaze point 与 confidence 都应能以 debug overlay 显示。没有可视化 rate map 时，gaze 错位很容易被误判为 TAA、mip 或 upscaler 问题。

并非所有 Pass 都适合相同 Foveation
   Main material/lighting pass 通常收益最大；depth、关键 UI、hand outline、text、某些 transparency 和 compositor layer 可能必须保持全分辨率。统一给所有 pass 套同一 rate map 会制造可见错误。

Temporal Smoothing 用于控制清晰区迁移
   相邻帧 rate map 若直接跳变，会出现清晰度边界闪烁。可以平滑 gaze、radius 与过渡区，并在大幅 saccade 时短暂扩大高质量区域。

过度平滑会增加 Gaze Lag
   平滑越强，边界越稳定，但快速扫视越容易先看到一帧模糊再变清晰。需要在 gaze prediction、smoothing 和中心区大小之间共同调节。

后处理必须理解非均匀质量分布
   TAA、motion blur、bloom、DoF、upscaler 和 history reprojection 若假设全屏同分辨率，会在 foveation 边界产生 halo、ghosting 或锐度断层。

性能收益取决于真实瓶颈
   如果场景受 fragment shading、texture sampling、lighting 或 post-process 限制，foveation 通常有效；如果瓶颈在 CPU submit、geometry、sync 或 compositor，rate map 再激进也不会显著降低 frame time。

评价必须同时记录性能与视觉质量
   GPU pass time、fragment workload、bandwidth、center clarity、peripheral stability、gaze latency、saccade blur 和用户敏感度必须一起观察。只比较平均 FPS 无法判断策略是否可用。

关键内容应单独保护
   文字、报警灯、瞄准线、交互目标、透明 UI 与高对比轮廓可用 full-rate mask 或 compositor layer 保持清晰，把性能收益集中到背景材质、远景、低对比区域和高成本体渲染中。

远程 XR 会把 Gaze 延迟放大
   Gaze→network→server render→encode→network→decode→display 的链路更长，因此中心区通常需要更宽，并配合 prediction。低延迟 UI 可留在客户端独立渲染。

关键路径
--------

动态注视渲染：

::

   eye gaze sample + confidence
   → predicted display time
   → combine with head/eye pose
   → per-eye gaze point
   → temporal prediction/smoothing
   → generate shading-rate map
   → render selected passes with variable quality
   → composite full-resolution protected layers
   → submit XR frame

画质故障排查：

::

   blur / flicker / rate boundary artifact
   → show gaze/rate debug overlay
   → verify per-eye coordinates
   → inspect gaze age/confidence/velocity
   → inspect center/transition radii
   → inspect post-process history
   → inspect protected UI/transparent masks

收益验证：

::

   fixed XR scene
   → capture foveation off
   → capture conservative level
   → capture aggressive level
   → compare pass GPU time/bandwidth
   → compare center clarity/peripheral motion
   → keep only quality levels with proven tradeoff

概念辨析
--------

* **Foveated Rendering 与 Dynamic Resolution**：前者在同一 frame 内按区域分配质量，后者通常调整整个主渲染分辨率。
* **Fixed Foveation 与 Eye-Tracked Foveation**：前者高质量区固定，后者随 gaze 动态移动并引入眼动时序问题。
* **VRS 与 Multi-Resolution Rendering**：VRS 改变 tile shading rate，多分辨率通过不同尺寸 RT/区域再合成。
* **Gaze Sample 与 Display-Time Gaze**：传感器当前样本不等于最终显示时刻用户真正看的位置。
* **Peripheral Low Detail 与 Peripheral Instability**：周边可以减少细节，仍必须保持运动、亮度和深度稳定。
* **Performance Gain 与 Quality Win**：GPU 时间下降只是收益的一半，清晰区错位或闪烁意味着策略仍然失败。

本章结论
--------

Foveated Rendering 应按“Gaze Timing—Per-Eye Mapping—Rate Map—Pass Coverage—Temporal Stability—Quality/Performance Evidence”理解。稳定系统会把眼动不确定性转成更保守的高质量区域，保护文字与交互目标，并用实际 GPU workload 与用户可见伪影共同决定 foveation 等级，而不是单纯追求更激进的周边降采样。