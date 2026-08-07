第145章：VR 与 AR 平台图形
========================

核心知识点
----------

XR 平台图形首先要分清三层责任
   Application renderer 负责生成 scene/color/depth；XR runtime 负责 tracking、frame timing、swapchain、composition 与 display；device capability 决定 refresh、resolution、sensor、power 与 interaction。跨平台设计必须把这三层拆开。

OpenXR 提供稳定的跨 Runtime 主线
   Instance、system、session、space、swapchain、view、composition layer 与 action 构成最小 XR 后端。厂商扩展和平台特性应挂在 capability/profile 上，而不是侵入 renderer 主干。

平台差异应按能力而不是品牌硬编码
   PC VR、Quest、visionOS、ARKit/ARCore 的真正差异在 view configuration、passthrough、hand/gaze、anchor、refresh、thermal、compositor 与权限。应用应查询能力后选择路径。

Runtime Frame Timing 是所有空间数据的时间基准
   Predicted display time 应同时驱动 view pose、input pose、anchor/spatial 查询。不同时间点的 pose 混用会造成虚拟内容相对真实世界或头部视角漂移。

ViewConfiguration 不应写死“双眼”
   后端应返回 viewCount、每个 view 的 FOV、recommended size、viewport、projection 与 depth 范围。HMD 多为双眼，handheld AR 可能单视图，未来多视图设备可能更多。

SwapchainSet 要明确资源所有权
   Runtime 提供的 color/depth image 在规定窗口 acquire/wait/write/release；renderer 自建资源自己管理；passthrough 或系统 layer 可能只暴露句柄/能力而不允许直接访问原始 camera image。

Composition Layer 是 XR Present 的真正接口
   Projection、quad、cylinder、equirect、passthrough 等 layer 最终由 compositor 组合。空间 UI 是否画入 scene 还是独立 quad layer，应依据遮挡需求、材质需求、文字清晰度和平台能力决定。

Passthrough 应抽象为 Real-World Layer
   Quest MR、visionOS、ARKit/ARCore 对 camera access 与系统合成权限差异很大。Renderer 不应假设能读取或后处理所有原始 camera frame，而应只消费平台明确提供的 color/depth/mesh/occlusion 能力。

Spatial Anchor 的核心是生命周期与可定位状态
   Anchor 需要 create、locate、persist、permission、lost/relocalize 状态。每帧渲染前必须判断是否 locatable；暂时丢失时应进入 fade/reposition 等明确状态，不能长期沿用旧 transform。

Hand/Controller/Gaze 应被转换成语义输入
   平台后端把具体设备映射成 primary ray、select/pinch、grip pose、menu、joint availability 等统一对象。应用交互逻辑消费语义动作，而不是依赖某个控制器品牌按钮。

跨平台 Backend 应输出统一 Frame Context
   Frame context 至少包含 predictedDisplayTime、views、color/depth targets、input、spatial state 与 performance hints。Renderer 的 scene/material/UI/pass 都只依赖这一稳定数据合同。

同一视觉目标不等于同一底层路径
   同一个“桌面上的虚拟控制台”，Quest 可由 passthrough+projection layer 实现，SteamVR 是纯 VR，ARCore 是 camera background+单视图，visionOS 可能由系统空间 UI 与自定义 Metal layer 组合。抽象层保持语义一致即可。

跨平台 Fallback 是正式能力
   Eye tracking、passthrough、environment depth、anchor persistence、hand tracking、refresh control 都可能不存在。Capability query 必须对应 fallback，例如 gaze→head direction、hand→controller/touch、depth occlusion→保守视觉提示。

XR 性能优化先看帧预算与长尾
   72Hz≈13.89ms、90Hz≈11.11ms、120Hz≈8.33ms，而且并非全部预算归应用。应观察 P95/P99 CPU/GPU time、compositor wait、dropped frame 与 refresh mismatch。

移动 XR 受 Thermal 与 Battery 双重约束
   Quest/phone 等设备的 GPU、CPU、display、sensor、camera 与 wireless 共享功耗。质量 profile 应结合 GPU/CPU、thermal、battery 与 runtime hint，在 High/Balanced/ThermalSafe 等档位间带迟滞切换。

分辨率、Foveation 与 UI 应独立控制
   主 scene 可以 dynamic resolution/foveation；文字、交互 cursor、近距离 UI 应通过高质量 scene pass、SDF font 或 compositor layer 保护，避免性能降级优先破坏可操作信息。

真实项目架构需要五类模块协作
   Platform backend 管 session/frame/submit；Spatial system 管 anchor/environment；Input system 管 hand/controller/gaze；Scene renderer 管传统图形；Spatial UI 管交互状态和 layer 策略。最终统一生成 Composition Packet。

调试必须让平台状态可见
   每帧应能打印/可视化 view count、target size/layer、session state、swapchain usage、input ray、anchor validity、composition layer、CPU/GPU/compositor timing、thermal 与 fallback path。

关键路径
--------

跨平台一帧：

::

   platform backend poll session
   → wait/begin frame
   → predicted display time
   → query views/input/spatial state
   → acquire runtime targets
   → scene + spatial UI render graph
   → build color/depth/passthrough/UI layers
   → release targets
   → submit composition packet
   → platform compositor

能力选择：

::

   query core session/view support
   → query input capability
   → query passthrough/depth/anchor
   → query performance/foveation/refresh
   → select feature path
   → install explicit fallback for missing capability

平台问题排查：

::

   wrong XR output
   → verify session/focus state
   → verify predicted time and views
   → verify swapchain size/layer/ownership
   → verify anchor/input coordinate spaces
   → verify composition layer fields
   → inspect GPU/compositor/thermal metrics

概念辨析
--------

* **XR Runtime 与 Graphics API**：runtime 管设备时序和合成，Vulkan/D3D/Metal/OpenGL 负责真正写 GPU image。
* **Swapchain Image 与 Ordinary Render Target**：前者通常由 runtime 管理所有权和提交生命周期，不能按普通自有 texture 使用。
* **Scene Layer 与 Compositor Layer**：scene layer 更适合真实遮挡和材质效果，compositor layer 更适合高频文字和稳定 UI。
* **Platform Abstraction 与 Lowest Common Denominator**：跨平台层应稳定抽象核心语义，同时允许 capability extension，而不是把所有平台压到最弱功能集合。
* **Spatial Anchor 与 Object Transform**：anchor 是真实世界参考的定位实体，对象 transform 只是应用场景中的局部/世界变换。
* **Performance Profile 与 Quality Preset**：XR profile 还包含 refresh、thermal、battery、foveation 与 compositor 条件，不只是画质选项。

本章结论
--------

VR/AR 平台图形应按“Runtime Session—Frame Timing—View/Swapchain—Spatial/Input Capability—Render Graph—Composition Layers—Performance/Fallback”理解。跨平台的重点不是把同一套底层 API 强行复用，而是让每个平台后端稳定提供同一帧语义，让 renderer 明确知道姿态来自哪个时间、图像写入哪个资源、真实世界能力是否可信，以及在能力或功耗不足时如何安全降级。