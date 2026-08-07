第032章：高级材质模型与微表面 BRDF
=================================

核心知识点
----------

微表面模型把宏观表面看成大量微小镜面的统计分布
   一个 fragment 的高光不是单一理想镜面，而是许多微面法线共同作用的结果。Roughness 控制这些微面朝向的离散程度，因此直接决定高光宽度、峰值和环境反射模糊程度。

Cook-Torrance 镜面项由 D、G、F 三部分组成
   ``D`` 是法线分布函数，决定有多少微面朝向半程向量；``G`` 描述 masking-shadowing，限制光线与视线能否同时看到这些微面；``F`` 是 Fresnel，决定当前角度下多少能量进入镜面反射。三项缺一都会破坏高光的能量和角度稳定性。

GGX 是实时 PBR 中常见的 D 项选择
   GGX 具有较长高光尾部，适合粗糙金属、塑料和环境反射。Roughness 往往先映射到微表面参数 alpha，再进入 D/G 计算；直接光、prefiltered IBL 和 BRDF LUT 必须共享同一 roughness 约定。

复杂材质本质上是多条能量路径的分层组合
   基础层处理 diffuse、metallic、roughness 与普通 specular；clearcoat 增加顶层薄镜面；sheen 表达布料微纤维的掠射角柔亮；transmission 处理进入表面后穿出的能量；anisotropy 改变 NDF 在 tangent/bitangent 方向的形状；SSS 则承担内部散射。

Clearcoat 应使用独立的顶层参数和法线
   车漆底层可以有粗糙金属 flakes，而顶层清漆仍保持平滑。共用同一张强 normal map 会让清漆高光碎裂。Clearcoat factor、roughness、normal 和 Fresnel 都应与底层材质分开观察，再进行能量组合。

Transmission 不能用 alpha coverage 代替
   玻璃即使高度透明，也仍具有 Fresnel 表面反射。Transmission 表示进入表面后穿出的光，alpha 更多描述 coverage 或混合权重；把二者合并会导致玻璃在透明时连边缘反射一起消失。

Sheen 与普通塑料镜面高光不同
   布料、天鹅绒的边缘柔亮来自微纤维近似，通常由 sheenColor 与 sheenRoughness 控制。它应产生宽而柔的掠射角响应，而不是低 roughness 塑料那种尖锐高光。

Anisotropy 依赖正确切线空间
   拉丝金属和纤维材质的高光会沿 tangent/bitangent 方向拉伸。模型旋转或 UV 方向变化时，高光方向应跟随切线基底；若高光固定在屏幕空间，优先检查 TBN、切线变换和 anisotropy rotation。

IBL 是高级材质暗部稳定性的关键
   Diffuse irradiance 提供低频环境漫反射，prefiltered radiance 根据 roughness 提供环境镜面，BRDF LUT 提供视角/粗糙度积分权重。金属暗部接近纯黑而主光高光正常，常见原因就是 specular IBL 缺失或 F0/roughness 映射错误。

复杂材质成本来自 ALU、采样、IBL 与控制流
   Clearcoat、transmission、sheen、anisotropy 都会增加公式、纹理或环境采样。优化应通过 LUT、预过滤环境、通道打包、材质分级和受控 variant 控制，而不是让所有像素永远执行完整材质模型。

关键路径
--------

基础微表面镜面：

::

   N、V、L
   → H = normalize(V + L)
   → roughness 映射到 alpha
   → D(N,H,alpha)
   → G(N,V,L,alpha)
   → F(V,H,F0)
   → D*G*F / (4*NoV*NoL)
   → 与 diffuse 能量组合
   → direct light
   → IBL 使用同一 roughness/F0 语义

复杂材质分层：

::

   baseColor / metallic / roughness / normal
   → 基础 diffuse + specular
   → 可选 clearcoat 顶层 Fresnel/normal
   → 可选 sheen
   → 可选 anisotropy 修改 NDF
   → 可选 transmission / absorption
   → 可选 SSS
   → 能量约束与 occlusion
   → direct light + IBL
   → 最终 HDR 输出

材质问题排查：

::

   固定白光、白色环境和曝光
   → 关闭 normal map 验证基础 D/G/F
   → 检查 baseColor、roughness、metallic、F0
   → 检查 prefiltered env 与 BRDF LUT
   → 逐层启用 clearcoat / sheen / transmission / anisotropy
   → 检查每层独立 normal、贴图通道和颜色空间
   → 最后恢复真实 HDR、纹理和完整变体

概念辨析
--------

* **D、G、F**：D 描述微面朝向概率，G 描述微面可见性，F 描述界面反射比例，三者职责不同。
* **Roughness 与 normal map**：roughness 描述微面统计分布，normal map 改变当前 fragment 的宏观着色方向；两者都会影响高光，但尺度和语义不同。
* **Clearcoat 与普通 specular**：clearcoat 是覆盖在基础材质上的额外顶层反射 lobe，应有独立 roughness/normal 和能量分配。
* **Transmission 与 alpha**：transmission 是光穿过介质的能量路径，alpha 通常表示 coverage 或混合权重；透明玻璃仍需要镜面反射。
* **Sheen 与 Fresnel specular**：sheen 是微纤维材质的专用边缘响应，不等于简单提高普通 Fresnel 高光。
* **Anisotropy 与 texture direction**：anisotropy 让 NDF 在切线空间拉伸，其方向来自 tangent basis 或专门旋转参数。
* **Advanced material 与更多参数**：高级材质的价值不是参数数量，而是每个参数对应明确的能量层和可观察视觉效果。
* **Uber shader 与材质变体**：uber shader 降低 pipeline 数量但提高寄存器、分支和编译复杂度；变体降低无效路径但会增加 pipeline cache，需按资源路径变化划分。

本章结论
--------

高级材质应先把基础 ``D/G/F`` 做正确，再逐层加入 clearcoat、sheen、transmission、anisotropy 和 SSS，并保证每层都有明确输入、法线、能量归属和禁用值。视觉上用固定测试球逐层验证，性能上用 LUT、预过滤环境、材质分级和有限 variant 控制成本；只有让每个额外 lobe 都能解释“它改变了什么画面、增加了什么资源和计算”，复杂 PBR 才能保持可维护。