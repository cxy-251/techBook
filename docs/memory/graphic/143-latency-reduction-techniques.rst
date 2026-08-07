第143章：延迟降低技术
====================

核心知识点
----------

XR 延迟优化的目标是让显示状态贴合用户当前身体状态
   头部、手柄和 gaze 已经移动后，最终图像必须在显示时刻尽量对应新的感知状态。延迟问题因此跨越 sensor、tracking、application、GPU、runtime compositor 和 display scanout。

Motion-to-Photon 比单独 GPU Time 更能描述 XR 延迟
   总延迟包含 sensor sampling、tracking fusion、pose prediction、application update、render、submit、composition、scanout 与 panel response。GPU 8ms 并不能证明最终 motion-to-photon 足够低。

Prediction 把渲染目标对准未来显示时刻
   Runtime 根据 IMU、视觉追踪、速度历史与滤波状态预测 predicted display time 下的 pose。应用应围绕该时间点查询 view/input/spatial state，而不是使用普通 wall clock 或上一轮 update 的旧姿态。

Prediction Error 是不可避免的估计误差
   快速 yaw、追踪噪声、长预测窗口和重定位会放大预测误差。表现通常是 world-locked object 漂移、过冲或回拉。预测窗口越长，模型越难准确。

Late Latching 的核心是让姿态更晚进入 GPU
   Scene simulation、animation、visibility 与 material 可较早准备，而最终 per-eye view/projection、controller ray、gaze center 等小型动态状态应尽可能靠近 draw/submit 时更新。

Late Latching 不能破坏 Culling
   如果 visibility 使用旧 pose，而矩阵最后才更新，快速转头后边缘对象可能已经被错误剔除。常见做法是扩大 culling frustum、采用 union/guard band 或更保守的 visibility set。

Timewarp/ATW 用最新 Head Pose 重投影已有图像
   Runtime 在应用提交后，根据更新后的姿态对 eye image 做旋转或空间重投影，以缩短提交到扫描之间的 residual latency。它最擅长补偿小范围头部旋转。

ATW 无法生成缺失几何
   大幅平移、新暴露区域、近距离遮挡和动态物体运动无法仅靠旧图像恢复。应用仍需要稳定渲染、正确 depth 与足够保守的可见集。

Spacewarp/Frame Synthesis 还要处理场景运动
   当应用没有交付完整新帧时，runtime 可利用 image、depth、motion vector、camera motion 等合成中间帧。它比纯 timewarp 更依赖正确的对象运动和遮挡信息。

Depth 是 Reprojection 的关键结构证据
   Per-eye depth 能帮助 compositor 理解近远关系和重投影尺度。应用提交 depth 时必须明确 format、near/far、reverse-Z、array layer 与 runtime 约定。

Motion Vector 需要严格的 Per-Eye 时间语义
   Motion vector 应对应当前/上一帧 view-projection 与 object transform。透明物体、particle、skinned mesh、UI、passthrough 等特殊内容若 motion 错误，会在 spacewarp、TAA 和 upscaler 中产生 ghosting。

Composition Layer 可以保护高频 UI
   文字、光标、系统面板和 world-locked quad 若独立交给 compositor，通常比烘入主场景后再 timewarp 更清晰稳定。需要真实遮挡和材质效果的 UI 则更适合 scene layer。

Frame Pacing 比平均吞吐更重要
   90Hz 约 11.11ms，120Hz 约 8.33ms。应用应稳定命中 refresh slot，并给 compositor 留余量。高平均 FPS 伴随周期性 missed frame，仍会产生 judder 和高 reprojection。

Judder 是时序不均匀的视觉结果
   Missed vsync、frame pacing 波动、runtime 补帧比例变化都会让 world-locked 边缘出现不均匀运动。它不能只用“帧率低”解释。

Reprojection Rate 是重要风险指标
   偶发峰值可能是正常安全网；长期高比例表示应用路径持续依赖 runtime 补偿。需要与 GPU/CPU time、pose age、dropped frame 和视觉 artifact 一起观察。

舒适性评估必须连接主观反馈与工程指标
   Motion-to-photon 峰值、reprojection、dropped frame、tracking invalid 与用户眩晕/眼疲劳是否同步，比单纯 FPS 更能解释体验风险。

延迟优化应按层次推进
   先保证 frame budget 和 pacing，再缩短 pose age，再提供 depth/motion 支持 compositor，最后再叠加更激进 prediction、spacewarp、foveation 等补偿策略。

关键路径
--------

XR 延迟链：

::

   sensor sample
   → runtime tracking/prediction
   → predicted display pose
   → application state update
   → late pose binding
   → GPU rendering
   → layer submit
   → compositor timewarp/spacewarp
   → display scanout
   → photon reaches eye

补偿数据：

::

   old rendered frame
   + latest head pose
   + per-eye depth
   + motion vectors
   → reprojection validity
   → timewarp / frame synthesis
   → corrected display frame

风险诊断：

::

   drift / judder / ghost / discomfort
   → classify head vs object vs input latency
   → inspect pose age
   → inspect CPU/GPU frame pacing
   → inspect dropped/reprojection rate
   → inspect depth/motion validity
   → compare raw render and compensation paths

概念辨析
--------

* **Prediction 与 Late Latching**：prediction 决定使用哪个未来姿态，late latching 决定这个姿态多晚写入渲染资源。
* **Timewarp 与 Spacewarp**：timewarp 主要修正头部姿态，spacewarp 还尝试合成场景运动。
* **GPU Time 与 Motion-to-Photon**：前者是局部执行成本，后者是用户运动到显示反馈的全链路延迟。
* **Reprojection Safety Net 与 Normal Rendering**：重投影用于最后一段补偿，不应成为长期超预算的常态路径。
* **Depth Reprojection 与 Motion Vector Reprojection**：depth 解释空间层次，motion vector 解释帧间内容运动。
* **Dropped Frame 与 Judder**：掉帧是时序事件，judder 是用户看到的非均匀运动结果。

本章结论
--------

XR 延迟应按“Tracking Time—Prediction—Late Binding—GPU Work—Submit—Reprojection—Display—Comfort Evidence”理解。有效优化不是单纯让 shader 更快，而是让姿态尽可能接近最终显示时刻进入画面，让 compositor 获得可靠 depth/motion 信息，并用 pose age、frame pacing、reprojection 与用户反馈证明整个感知闭环稳定。