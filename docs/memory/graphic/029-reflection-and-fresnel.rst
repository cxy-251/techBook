第029章：反射与 Fresnel
======================

核心知识点
----------

反射方向与 Fresnel 解决两个不同问题
   反射方向回答“镜面贡献从哪个方向取得”，Fresnel 回答“当前视角下有多少能量进入镜面反射”。环境反射错误先检查 ``N/V/R``，反射强弱错误再检查 ``F0``、Fresnel 与材质能量分配。

反射向量依赖统一且正确的方向约定
   PBR 中 ``V`` 常定义为从表面指向相机，环境采样通常使用 ``reflect(-V,N)``。法线、观察方向和光照方向必须处于同一空间，并先归一化；符号或空间错误会让 cubemap 采样方向翻转或高光出现在错误半球。

F0 是正入射镜面反射率
   对常见介电体，``F0`` 通常是较低的灰色值，可由 IOR 近似得到 ``((ior-1)/(ior+1))^2``；IOR 约 1.5 时 ``F0≈0.04``。金属的 F0 通常较高且带颜色，来源于 baseColor 或实测光学数据。

Schlick 近似是实时 Fresnel 的主力形式
   常用表达为 ``F = F0 + (1-F0)(1-cosθ)^5``。直接光微表面路径常使用 ``V·H``，IBL 或轮廓观察常围绕 ``N·V``。固定五次方可用连乘实现，减少通用 ``pow`` 成本。

Fresnel 让掠射角反射增强
   ``cosθ`` 越小，反射越接近高值，因此塑料、玻璃、水和皮肤在轮廓处都会比正视角更亮。这个亮度变化来自反射比例增加，不等于表面变得更光滑。

Roughness 与 Fresnel 分工不同
   Fresnel 控制镜面能量随角度变化，roughness 控制这部分能量分布到多宽的方向范围。低 roughness 产生清晰、集中的反射；高 roughness 产生宽而模糊的反射。判断“过亮”和“过锐”时必须分开检查。

Metallic 工作流通过 F0 区分金属与非金属
   常见形式是 ``F0 = mix(vec3(0.04), baseColor, metallic)``，同时 ``diffuseColor = baseColor * (1-metallic)``。金属颜色应进入镜面路径，普通漫反射随 metallic 增大而消失；若金属像有色塑料，通常是这一能量分配没有生效。

IBL 镜面路径依赖反射方向、预过滤环境与 BRDF LUT
   Prefiltered environment 根据 ``R`` 和 roughness 提供环境辐射，BRDF LUT 根据 ``N·V`` 与 roughness 近似微表面积分，F0 再决定材质基础镜面反射。主光正确而环境反射异常时，应优先检查这三者的一致性。

玻璃和皮肤需要在 Fresnel 之外继续分流能量
   玻璃正视角大量能量进入 transmission，边缘反射增强；皮肤只有表层 Fresnel 反射，内部 diffuse/SSS 另走散射路径。因此强行提高 F0 不能替代透明或次表面模型。

关键路径
--------

环境镜面反射：

::

   world/view normal N
   + view direction V
   → R = reflect(-V, N)
   → baseColor / metallic / IOR 得到 F0
   → 计算 Fresnel
   → roughness 选择 prefiltered env mip
   → NoV + roughness 查询 BRDF LUT
   → specular IBL
   → 与 diffuse / transmission / SSS 等剩余能量合成

Fresnel 问题排查：

::

   输出 N、V、R 调试色
   → 检查 NdotV 分布
   → 固定 F0=0.04 验证介电体
   → 固定 roughness 验证角度变化
   → 检查 metallic 到 F0 与 diffuse 的映射
   → 恢复 prefiltered environment
   → 检查 BRDF LUT、mip、颜色空间和曝光

概念辨析
--------

* **Reflection vector 与 Fresnel**：前者决定镜面采样方向，后者决定镜面能量比例。
* **F0 与 IOR**：F0 是正入射反射率；IOR 是介质光学属性之一，可用于推导介电体 F0，但二者不是同一个参数。
* **Fresnel 与 roughness**：Fresnel 改角度权重，roughness 改反射分布宽度；亮度和清晰度要分别判断。
* **Metallic 与 colored specular**：metallic 工作流用 metallic 决定 baseColor 是否进入镜面 F0；金属高光带颜色不等于普通塑料高光染色。
* **Reflection 与 transmission**：玻璃即使高度透明也保留 Fresnel 反射；alpha coverage 不能替代光学透射。
* **Direct specular 与 specular IBL**：前者评估少量明确光源，后者近似整个环境半球；两条路径应共享同一 roughness/F0 语义。
* **Schlick 与完整 Fresnel 方程**：Schlick 是实时近似，适合常规 PBR；需要精确介质或复折射率时应使用更完整模型或预计算数据。

本章结论
--------

反射问题应按“方向—F0—角度 Fresnel—roughness—环境积分”逐层定位。``R`` 决定从哪里取镜面光，``F0`` 决定正视角基础反射，Fresnel 决定掠射角增强，roughness 决定反射扩散程度；金属、塑料、玻璃和皮肤的差异，最终来自这些量与 diffuse、transmission、SSS 等剩余能量路径的不同分配。