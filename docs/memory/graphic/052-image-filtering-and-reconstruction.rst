第052章：图像过滤与重建
======================

核心知识点
----------

过滤本质上是在一个采样邻域内重新分配频率
   低通滤波压低高频，适合 blur、mipmap、降噪和稳定缩小采样；高通滤波提取或强化快速变化，适合 sharpening，也会同步放大噪声、ringing、压缩误差与 temporal 残留。

重建解决“有限样本如何形成目标像素”的问题
   Downsample、upscale、抗锯齿、temporal accumulation 都属于 reconstruction。判断时先确认输入样本网格、输出网格和真实 pixel footprint，再决定 filter，而不是先调锐度或模糊半径。

不同 aliasing 来源需要不同工具
   几何轮廓锯齿看 coverage/MSAA/TAA；远处纹理闪烁看 mip、LOD 与 anisotropy；shader 高频看着色输出；透明粒子和快速运动残影看 motion/history/reactive mask；低分辨率到高分辨率输出看 temporal upscaler 的输入完整性。

Mipmap 是纹理 minification 的预过滤结构
   一个屏幕像素覆盖大量 texel 时，应从更粗 mip 读取已经低通的结果。负 LOD bias 可以让静态截图更锐，却经常增加移动时 shimmer；正确目标是时间稳定的有效细节，而不是最大瞬时锐度。

MSAA 主要解决几何 coverage
   它通过像素内多个 coverage/depth sample 改善多边形边缘，对 shader 生成的高频、alpha-tested 纹理、normal 闪烁和后处理 aliasing 作用有限。Resolve 后多 sample 信息消失，后续 pass 只能处理单张图像。

TAA 和 temporal upscaling 依赖可信 history
   当前帧 jitter 产生新的子像素样本，motion vector 用于重投影上一帧 history，depth、颜色邻域、velocity 和 reactive mask 决定历史是否可复用。History 权重过高会模糊和 ghosting，过低则失去时间稳定性。

Gaussian、Lanczos、Bilateral 的目标不同
   Gaussian 稳定且适合平滑扩散；Lanczos 更锐利但容易 ringing/overshoot；Bilateral 利用 depth、normal、luma 等 guide buffer 保护边缘，适合 AO、reflection、shadow 等 edge-aware denoise，但 guide 错误会变成 halo、漏光和斑块。

Sharpening 不能创造真实细节
   它只提升现有局部对比。TAA/upscale 后锐化较常见；过强 amount、多次锐化、负 LOD bias 与高锐重建叠加，会在轮廓产生亮边、暗边和噪声放大。HDR 阶段锐化与 tone-mapped LDR 阶段锐化的视觉含义也不同。

Filter 半径要绑定分辨率语义
   固定 3 texel 在 1440p 与 4K 对应不同屏幕尺度。动态分辨率、upscaler 前后和半分辨率 pass 中，radius、texelSize 与 kernel footprint 必须按实际输入/输出尺寸转换。

关键路径
--------

空间过滤：

::

   input texture
   → 确认 signal / color space
   → 确认 output pixel footprint
   → 选择 kernel / guide buffer
   → neighborhood sampling
   → weighted reconstruction
   → edge / overshoot clamp
   → output texture

Temporal reconstruction：

::

   jittered current color
   + depth
   + motion vector
   + previous history
   + reactive / validity mask
   → reproject history
   → validate / clamp
   → blend current + history
   → write resolved color
   → write next history

画质症状排查：

::

   固定相机 / 随机种子 / 分辨率
   → 保存 raw color 与 resolved color
   → 查看 depth / motion / history / mip LOD
   → 逐个关闭 filter
   → 只修改最接近根因的参数
   → 静止、慢移、快移、透明物、高亮、UI 回归

概念辨析
--------

* **低通与模糊**：低通是频率操作，blur 是常见视觉结果；mipmap 也是低通，但服务纹理缩小采样。
* **高通与真实细节**：高通只强化已有变化，不会恢复丢失的几何或纹理信息。
* **MSAA 与 TAA**：MSAA 增加同帧 coverage sample；TAA 通过跨帧 jitter/history 积累子像素信息。
* **FXAA 与 TAA**：FXAA 只看当前屏幕颜色估计边缘；TAA 还依赖 motion、depth 和历史状态。
* **Gaussian 与 Bilateral**：Gaussian 只按空间权重平滑；Bilateral 还根据 guide 相似度阻止跨边缘混合。
* **空间模糊与时间模糊**：前者来自低分辨率、mip、kernel 等；后者多来自 history 权重、velocity 和 reprojection 错误。
* **清晰度与稳定性**：锐利静态截图不代表高质量；真实目标是空间细节、时间稳定与性能的共同平衡。

本章结论
--------

图像过滤与重建应按“输入样本—pixel footprint—空间/时间证据—filter—输出尺度”理解。锯齿先找 coverage 来源，纹理闪烁先修 mip/LOD，ghosting 先修 motion/history，过锐先查 high-pass 与 pass 顺序，模糊则先比较 raw 与 resolved。只有先把采样链正确，再讨论锐度和风格，画质优化才不会用一个滤镜掩盖另一个错误。