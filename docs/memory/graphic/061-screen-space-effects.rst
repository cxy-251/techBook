第061章：屏幕空间效果
====================

核心知识点
----------

屏幕空间效果只使用当前帧已经可见的数据
   SSAO、SSR 等技术主要复用 depth、normal、roughness、motion vector 和 HDR color。它们不重新遍历完整场景，因此速度快，但天然看不到屏幕外、被遮挡、背面和未写入当前 buffer 的几何。

Depth reconstruction 是第一正确性边界
   屏幕 depth 必须按当前 projection、depth range、reverse-Z 和无限远平面约定还原到 view/world space。重建错误会让 SSAO radius 随距离失真，也会让 SSR ray 与真实表面产生系统性偏移。

SSAO 是局部半球遮蔽近似
   当前点根据 normal 建立半球采样方向，把 sample 投影回屏幕读取 scene depth，通过深度差估计局部遮挡。``radius`` 决定作用尺度，``bias`` 抑制自遮挡，sample count 与 noise 决定原始噪声。

SSAO 的滤波必须保护几何边缘
   低采样数通常先制造高频噪声，再通过 bilateral/depth-aware blur 平滑。跨 depth discontinuity 或 normal discontinuity 的混合会制造 halo 和黑边，因此 blur/upsample 的边缘权重与 raw AO 同样重要。

SSR 是屏幕上的反射射线搜索
   根据表面 normal 和 view direction 得到 reflection ray，在 view/screen space 沿 ray marching 采样 depth，寻找 ray 与当前可见表面的交点，再读取 HDR color 作为反射 radiance。

SSR 的核心边界是单层 depth
   ``thickness`` 用来容忍 ray 与离散 depth 的误差。过小容易穿过薄物体，过大会吸附到错误表面。屏幕边缘 miss、遮挡后 miss 和屏幕外物体缺失不是参数错误，而是屏幕空间可见域的结构性限制。

Hierarchical depth 能减少 SSR 无效步进
   全分辨率固定步长 marching 会产生大量 depth fetch。使用 HZB/depth pyramid 后，可以在粗 mip 上跳过明显空区域，再在命中附近 refinement；同时通过 roughness/tile classification 只给值得反射的像素分配 ray。

Roughness 决定反射质量与 fallback
   低 roughness 表面需要稳定清晰的 hit；中等 roughness 可低分辨率 trace 后 denoise；高 roughness 继续做昂贵 SSR 通常收益低，应逐渐过渡到 probe、prefiltered environment 或其它低频反射。

Temporal reuse 既稳定结果也会制造 ghosting
   SSAO/SSR 都可复用历史帧，但必须利用 motion vector、depth、normal、roughness、hit distance 和颜色邻域验证 history。Disocclusion、相机快速运动和反射命中点变化时应降低历史权重。

屏幕空间结果必须有 fallback
   SSR ray 离开屏幕、命中不可见表面或 roughness 超阈值时，需要 edge fade、probe、sky、planar reflection 或 ray tracing 接管。稳定系统不是强行让 SSR 覆盖所有像素，而是明确哪些像素由哪种证据负责。

关键路径
--------

SSAO：

::

   depth + normal
   → reconstruct view position
   → build normal-oriented hemisphere
   → project samples to screen
   → compare scene depth
   → raw AO
   → depth/normal-aware blur
   → ambient / indirect composite

SSR：

::

   depth + normal + roughness + HDR color
   → reflection direction
   → screen-space ray marching / HZB traversal
   → thickness depth test
   → hit UV / miss reason
   → sample reflection radiance
   → temporal validation / denoise
   → probe / sky / RT fallback
   → HDR composite

伪影排查：

::

   linear depth / normal view
   → raw AO / SSR hit mask
   → sample count / ray-step view
   → blur / upsample edge weights
   → history rejection mask
   → fallback weight
   → final composite

概念辨析
--------

* **屏幕空间与场景空间**：屏幕空间只知道当前相机已经写入 buffer 的表面；场景空间查询可以访问屏幕外和遮挡后的几何。
* **SSAO 与真实 GI**：SSAO 只提供局部可见深度的遮蔽近似，不传播真实间接光能。
* **SSR 与 Ray Tracing Reflection**：SSR 查询当前屏幕 depth/color；RT 通过场景加速结构查询真实几何，覆盖范围更完整但成本更高。
* **Thickness 与真实几何厚度**：SSR thickness 是深度比较容差，不是物体真实物理厚度。
* **Half-resolution 与低质量**：低分辨率本身不是错误，关键在 depth-aware upsample、roughness 分层和边缘保护。
* **Ghosting 与单帧错误**：关闭 history 后仍然错误，问题在当前帧输入或 tracing；只有开启历史才出现，则优先查 reprojection 与 rejection。
* **Miss 与 Bug**：屏幕边缘、遮挡后和屏幕外反射 miss 是算法边界，应进入 fallback，而不是无限增大 ray distance。

本章结论
--------

屏幕空间效果应按“已有 buffer—空间重建—局部采样/追踪—边缘保护—历史验证—fallback”理解。SSAO 的质量主要受 depth/normal、radius、bias 和边缘滤波控制；SSR 的质量主要受 depth precision、thickness、HZB traversal、roughness、history 和 fallback 控制。真正稳定的实现会把 raw mask、hit/miss、history weight 和 fallback weight 都做成可观察资源，让每种伪影能落回明确的数据边界。