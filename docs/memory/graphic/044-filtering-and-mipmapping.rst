第044章：过滤与 Mipmapping
=========================

核心知识点
----------

纹理过滤解决屏幕像素与纹理 texel 尺度不一致的问题
   放大采样时，一个 texel 可能覆盖多个像素；缩小采样时，一个像素可能覆盖大量 texel。Magnification 主要处理插值，minification 主要处理高频信息如何预过滤并稳定汇总。

Nearest、Bilinear、Trilinear 解决的层级不同
   Nearest 取单个 texel，适合离散数据和像素风；bilinear 在同一 mip 的 2x2 texel 内插值；trilinear 再在两个相邻 mip 之间混合。Trilinear 主要消除 mip 层级切换带来的 LOD popping，并不能独自解决斜视角 footprint。

Mip chain 是缩小采样的预过滤结果
   每一级宽高通常减半，直到 1x1。它把高频内容提前低通，使远处像素不必直接从 base level 随机抽取大量细节。完整 2D mip chain 的额外存储约为 base level 的三分之一。

LOD 通常由屏幕空间 UV 导数估计
   GPU 利用 ``ddx/ddy`` 估计当前 pixel footprint。UV 在屏幕上变化越快，footprint 越大，LOD 越高，采样越粗。强非线性 UV 变换、手写 ray marching 或特殊投影可能需要显式 ``textureGrad`` 或 ``textureLod``。

Mip 生成必须考虑纹理语义
   Base color 应在线性空间进行合理低通；normal map 不能只把 RGB 当普通颜色平均，通常还需重归一化；roughness 等参数的 mip 会影响远处高光能量。错误 mip 内容会被 sampler 稳定地放大到最终画面。

Mip bias 是清晰度与稳定性的直接杠杆
   正 bias 推向更粗 mip，画面更稳但更糊；负 bias 推向更细 mip，画面更锐但更易 shimmer 和 moire。Bias 应建立在正确 mip 与 footprint 上，而不是用来掩盖错误资源或导数。

各向异性过滤处理拉长的采样 footprint
   斜视地面、道路和墙面中，footprint 往往是一条细长椭圆。普通 mip 近似为方形尺度，会连短轴细节一起抹掉；anisotropic filtering 沿长轴增加采样，从而同时降低 aliasing 并保留更多细节，代价是更多纹理访问。

Sampler 与资源 mip 范围必须一致
   Vulkan、Direct3D 等都把 min/mag filter、mipmap mode、LOD bias、min/max LOD、anisotropy、address mode 写入 sampler。Texture view 若只暴露部分 mip，或 streaming 尚未驻留目标 mip，即使 sampler 设置正确也可能表现为模糊或跳变。

Comparison sampler 属于深度比较路径
   Shadow map 常使用 comparison sampler，把深度读取和参考值比较结合起来。它与普通 base color、normal、roughness 采样语义不同，误绑会直接把纹理输出变成比较结果。

Shimmer、moire、blur、LOD popping 应分别定位
   Shimmer 与 moire 通常指向 minification、mip、负 bias 或 anisotropy；blur 可能来自粗 LOD、streaming、源图或 mip filter；LOD popping 来自离散 mip 切换或资源驻留突变；固定块状污染则更多指向压缩格式而非 sampler。

关键路径
--------

普通隐式 LOD 采样：

::

   interpolated UV
   → ddx / ddy
   → estimate texture footprint
   → derive LOD
   → apply mip bias / LOD clamp
   → choose mip level(s)
   → point / bilinear / trilinear / anisotropic filtering
   → sampled value

远处闪烁排查：

::

   判断是否处于 minification
   → 显示 UV 与导数
   → 确认完整 mip chain
   → 显示 mip-level debug
   → 固定 LOD 检查各级 mip 内容
   → 检查 mip bias
   → 开启/对比 anisotropy
   → 检查 streaming residency
   → 最后比较压缩前后

发糊排查：

::

   fixed-Lod 逐级观察
   → 判断是选择了过粗 mip 还是 mip 内容本身过软
   → 检查 positive bias / LOD clamp
   → 检查高分 mip 是否驻留
   → 检查 source resolution / mip generator
   → 斜视面再检查 anisotropy

概念辨析
--------

* **Magnification 与 minification**：前者是纹理样本不足以覆盖像素，后者是单像素覆盖过多纹理细节。
* **Bilinear 与 trilinear**：bilinear 只在单级 mip 内插值；trilinear 还混合相邻 mip。
* **Mipmapping 与 anisotropy**：mip 解决尺度变化，各向异性进一步处理 footprint 方向性，两者通常配合使用。
* **Mip bias 与 streaming**：bias 改变逻辑 LOD；streaming 决定目标 mip 是否实际驻留。
* **自动 LOD 与显式 LOD**：自动路径依赖导数；显式路径由 shader 指定，灵活性更高，也更容易写错。
* **Sampler 过滤与压缩伪影**：过滤决定如何读 texel；压缩改变 texel 本身的近似值。块状污染不能靠换 bilinear/trilinear 根治。
* **清晰与正确**：更锐不等于更正确。负 bias 或关闭 mip 可以让截图更锐，同时在运动中产生严重 aliasing。

本章结论
--------

过滤与 mipmapping 的核心是“根据真实 pixel footprint 选择合适预过滤尺度，再用匹配 footprint 的过滤器重建”。远处闪烁先查 mip 和 LOD，斜视发糊再查 anisotropy，整体发糊要区分 sampler 选择、streaming 与 mip 内容。通过 UV 导数、mip debug、固定 LOD 和 sampler 对比，就能把主观清晰度问题转成可复查的采样链路。