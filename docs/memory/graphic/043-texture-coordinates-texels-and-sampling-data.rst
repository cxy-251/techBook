第043章：纹理坐标、Texel 与采样数据
====================================

核心知识点
----------

纹理系统是一条完整数据链
   Mesh 提供 UV，光栅化阶段对 UV 做透视校正插值，fragment shader 使用插值后的坐标读取 texture，sampler 决定过滤、寻址和 LOD，采样结果再被解释成 base color、normal、roughness、metallic、AO、height 或 mask。定位问题时必须区分“坐标错、资源错、sampler 错、语义解释错”。

UV、Texel 与 Sampler 属于不同层级
   UV 是连续几何属性；texel 是纹理中的离散存储样本；sampler 是读取规则。相同 texture 配不同 sampler 可以得到不同边界和过滤结果，相同 UV 读取不同纹理又会进入完全不同的材质语义。

Tiling、offset 与 wrap mode 共同决定二维定位
   常见材质变换为 ``uv2 = uv * tiling + offset``。UV 超出 ``[0,1]`` 后，repeat、mirror、clamp-to-edge、clamp-to-border 会产生完全不同结果。图案不重复或边缘大片拉伸时，优先检查 sampler address mode，而不是先改 mesh。

UV seam 是几何连续与纹理不连续的边界
   一条几何边可以在 UV 空间拆成两条不连续边。Base color 会出现花纹断裂；normal map 还会受到 tangent basis、镜像 UV 和 bitangent sign 影响。Atlas 进一步放大 seam 问题，因为 linear filter 和 mip 会跨 sub-rect 边界取样，因此必须留 padding。

颜色纹理与数据纹理必须分开处理
   Base color、emissive 通常按 sRGB 解码到线性空间；normal、roughness、metallic、AO、height、mask 应按线性数据读取。把 RMA 当 sRGB 会直接改变材质参数曲线，把 base color 当 linear 又会破坏能量关系。

Normal map 的完整路径是“解码—归一化—空间变换”
   采样值先从 ``[0,1]`` 映射到 ``[-1,1]``，再根据 TBN 转到 world/view space，并重新归一化。绿色通道约定、tangent.w、镜像 UV 与切线生成工具任一不一致，都可能让凹凸反向或高光在接缝处跳变。

通道打包减少采样，但增加协议约束
   RMA/ORM 等贴图把多个独立标量放在 RGB 通道中，可减少纹理数量、descriptor 和采样次数。代价是导出器、导入器、shader、调试视图必须共享完全一致的通道表，并保持 linear 读取。

普通纹理采样隐含 LOD 选择
   Fragment shader 通常根据屏幕空间 UV 导数估计 footprint 并自动选择 mip。远处闪烁不一定是“贴图太锐”，更常见原因是 mip chain 缺失、min filter 错误、UV 不连续或 atlas padding 不够。

关键路径
--------

二维材质采样：

::

   mesh vertex UV
   → perspective-correct interpolation
   → fragment UV
   → tiling / offset / atlas transform
   → sampler address / filter / LOD
   → texture / mip lookup
   → raw sampled value
   → color-space decode / channel unpack
   → normal / roughness / metallic / AO 等材质参数
   → lighting / BRDF

Normal map：

::

   tangent-space normal texture
   → linear sample
   → rgb * 2 - 1
   → normalYSign / swizzle
   → normalize
   → TBN transform
   → world/view normal
   → direct light + IBL

故障排查：

::

   输出 frac(UV) / checker
   → 检查 texture 资源与 mip
   → 检查 sampler filter / address / LOD
   → 输出原始纹理采样
   → 输出 normal / RMA 等语义参数
   → 检查 sRGB 与 linear
   → 最后恢复 lighting

概念辨析
--------

* **UV 与 texel**：UV 是连续坐标，texel 是离散样本；采样器负责把前者转换为后者的组合结果。
* **Texture 与 sampler**：texture 保存数据与 mip；sampler 保存如何读，包括 filter、address 和 LOD。
* **Seam 与 atlas bleeding**：seam 来自 UV 不连续；atlas bleeding 来自过滤跨越 sub-rect，二者都可能在低 mip 被放大。
* **Base color 与 mask**：前者是颜色数据，通常需要 sRGB 解码；后者是数值数据，应保持线性。
* **Geometry normal 与 normal map**：几何法线给出基础表面方向，normal map 只是在局部坐标中扰动着色法线。
* **Tiling 与 texel density**：tiling 改变重复频率；texel density 描述单位表面覆盖多少纹理样本，二者相关但不是同一概念。
* **LOD 问题与资源问题**：硬件可能选择了正确 LOD，但高分 mip 尚未驻留；也可能资源齐全而导数/采样状态选择了错误 mip。

本章结论
--------

纹理贴图应按“UV 坐标—texture 存储—sampler 状态—shader 语义—lighting”理解。拉伸先查 UV，边缘异常查 address mode 与 atlas padding，远处闪烁查 mip/LOD，凹凸反向查 normal/TBN，颜色或粗糙度异常查 sRGB 与通道约定。只要坐标、资源、采样状态和语义分层清楚，复杂材质问题就能被稳定定位。