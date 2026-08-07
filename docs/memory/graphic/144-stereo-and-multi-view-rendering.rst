第144章：Stereo 与 Multi-View Rendering
======================================

核心知识点
----------

Multi-View Frame = 共享世界状态 + Per-View 状态
   Mesh、material、instance、light、animation 等世界数据应尽量共享；eye pose、projection、camera position、viewport、depth、motion vector 和目标 layer 按 view 分离。多视图优化的核心是把差异集中到最少的数据结构中。

View Array 是多视图渲染的基本抽象
   每个 view 都有 pose、view matrix、projection matrix、viewport/target layer 与提交描述。双眼 VR 通常是两个 view，CAVE、光场等系统会扩展到更多 view。

View Order 必须贯穿所有阶段
   同一个 viewIndex 要同时选择 pose、FOV、projection、constant buffer slice、render target layer 和 composition sub-image。任何一个阶段错位，都可能造成左右眼交换、单眼漂移或重复图像。

视差来自 Eye Baseline 与 Per-Eye Projection
   近物左右眼差异更大，远物更小。IPD、world scale 与 projection 焦距共同影响视觉深度。XR 世界单位应与物理米制保持一致，否则场景尺度会整体失真。

Toe-In 不是实时 XR 的优选双眼模型
   直接把左右相机旋向同一 convergence point 容易产生垂直视差和投影不一致。实时 XR 更稳定的做法是使用 runtime eye pose 与每眼非对称 FOV。

Multiview/View Instancing 主要减少重复提交与顶点工作
   一份 draw 可以为多个 view 执行，shader 使用 view index 读取不同 view-projection，并写到 texture array 对应 layer。它不会让两个 view 共用最终像素结果。

Texture Array 是最常见的资源组织方式
   Color、depth、normal、motion 等 per-view 结果可按 array layer 保存；world-space material、mesh、shadow atlas、light/probe 等通常保持单份资源。

Shared Culling 与 Per-View Culling 是可调权衡
   双眼距离较近时，可用 union frustum 生成共享 visible set，减少 CPU 场景遍历；多屏或光场 view 分布较宽时，更适合按 view cluster 分组 culling，避免过度提交。

Depth 结果不能直接跨 View 共享
   最终 depth 由当前投影决定，左右眼必须有各自 depth layer。可共享的是 depth pipeline、draw list 生成逻辑与资源管理方式，而不是屏幕空间 depth 值。

Shadow 通常适合跨 View 共享
   Shadow map 主要由 light view 决定，不随左右眼轻微移动而变化，因此双眼通常可以采样同一 shadow atlas。极端 view-dependent shadow 或 screen-space contact shadow 属于例外。

Reflection 的共享边界更严格
   Environment probe/cubemap 可共享，SSR 必须按 view 使用当前 color/depth/normal；平面反射是否共享取决于反射视点与允许误差。

Screen-Space Pass 基本都需要 Per-View 执行
   SSAO、SSR、TAA、motion blur、UI composition、screen-space outline 等依赖当前投影、depth 与 motion vector，不能直接拿左眼结果给右眼。

资源共享判断应问“是否依赖当前屏幕投影”
   与 view 无关的世界数据优先共享；与 view-dependent screen mapping 相关的资源按 view 分离。这个规则比按资源类型死记更稳定。

Multi-View Extension 不是免费加速
   它减少 CPU command、state bind 与部分 vertex cost；fragment shading、depth write、透明 overdraw 和 bandwidth 仍按 view 发生。收益要用 draw count、vertex invocation、fragment time 与带宽验证。

AR Passthrough 多视图还需要真实世界对齐
   Camera calibration、environment depth、occlusion、spatial anchor、eye pose 与 compositor layer 必须处于同一空间语义。虚拟物体漂移不一定是 mesh 问题，常来自真实/虚拟坐标链失配。

CAVE 与光场系统扩大了 View Count 问题
   CAVE 的 view 来自物理屏幕面与观察者位置，常需要 off-axis projection；光场需要更多角度样本，必须依赖 view reuse、分级分辨率、reprojection 或 neural reconstruction 控制成本。

关键路径
--------

双眼 Multi-View：

::

   runtime view state
   → view array
   → per-view pose/FOV
   → view/projection constants
   → shared or grouped culling
   → multiview draw submission
   → color/depth array layers
   → projection-layer submit

资源共享：

::

   resource/pass
   → does it depend on current screen projection?
   → no: share world-space resource
   → yes: allocate per-view layer/result
   → profile bandwidth and duplicated work

单眼错误排查：

::

   one view wrong
   → verify view index/order
   → verify pose/FOV pair
   → verify viewProjection array
   → verify framebuffer/layer/view mask
   → verify depth/motion layer
   → verify submitted sub-image

概念辨析
--------

* **Stereo Rendering 与 Multi-View Rendering**：stereo 是双眼特例，multi-view 可扩展到多屏、CAVE、光场等更多观察点。
* **Shared World Data 与 Shared Screen Result**：世界资源常可共享，screen-space color/depth/motion 通常不能直接共享。
* **Union Frustum 与 Per-Eye Culling**：前者降低 CPU 遍历，后者减少过度提交；选择取决于 view 分布和场景规模。
* **Multiview 与 Zero Duplicate Work**：multiview 减少重复状态和部分顶点工作，不能消除每个 view 的像素输出。
* **IPD 与 Convergence**：IPD 是双眼物理基线，convergence 是观看时的生理/视觉结果，不应靠 toe-in 相机硬编码。
* **Shadow Sharing 与 SSR Sharing**：shadow 多由光源视角决定，SSR 完全依赖当前 view 的屏幕空间数据。

本章结论
--------

Stereo/Multi-View Rendering 应按“View Array—Per-View Matrices—Shared World Data—Per-View Screen Resources—Layer Output—Display Calibration”理解。稳定架构会让所有 view 共享同一帧世界状态，只把真正依赖观察点的矩阵、depth、motion 与 screen-space pass 分叉，并用统一 viewIndex 贯穿 shader、resource layer 和 compositor 提交。