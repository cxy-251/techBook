========================================================================
Chapter 17: 微表面 Cook-Torrance PBR 模型：GGX、几何遮蔽与 Fresnel-Schlick
========================================================================

.. note:: 前置背景与认知承接
   前一章构建了辐射度量学的基础物理量体系（通量、辐照度、辐射率），推导了朗伯余弦定律与 BRDF 三大物理守恒准则。理想朗伯漫反射仅能描述粗糙吸光材质的均匀散射行为，而真实世界中几乎所有金属与电介质物体表面都存在显著的镜面高光反射（Specular Reflection）。为了在宏观尺度上高保真模拟微观粗糙表面的复杂光反射行为，图形学建立了基于微表面理论的 Cook-Torrance 镜面反射 BRDF 模型。本章将系统解构微表面光学假设、半程向量（Half Vector）空间变换、Cook-Torrance 镜面 BRDF 核心方程推导，并逐一深入推导三大核心微架构函数：GGX / Trowbridge-Reitz 法线分布函数（NDF）、Smith 联合掩蔽阴影几何函数（Visibility Function）与 Fresnel-Schlick 菲涅尔近似方程，最后给出工业级金属度-粗糙度（Metallic-Roughness）材质流的完整 HLSL 着色器实现。

------------------------------------------------------------------------
17.1 微表面理论 (Microfacet Theory) 光学假设与空间映射
------------------------------------------------------------------------

在宏观光学尺度下，真实世界中哪怕打磨极度光滑的物体表面，在波长级别的微观尺度下依然布满了凹凸不平的微观微面元。**微表面理论（Microfacet Theory）** 建立了连接微观物理光学与宏观渲染着色的数学桥梁。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       微表面微观粗糙度与光学镜面反射模型                |
   +-------------------------------------------------------------------------+

   宏观宏表面法线 n
         ^
         |      入射光 l           出射视线 v
         |         \                 /
         |          \   半程向量 h   /
         |           \     ^       /
         |            \    |      /
   ------+-------------+---+-----+---------------------- 宏观平坦表面
                       |  /|\   |
         微观微表面:   | / | \  |
       _/\_/\__/\__/\__|/  m  \_|/\_/\__/\__/\_
                       +--------+
        [ 仅当微表面法线 m == 半程向量 h 时，光线才能被精确反射至视线方向 v! ]

核心光学假设与半程向量 (Half Vector)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **理想镜面微面元假设**：假设宏观表面由无数个随机朝向的绝对平整、微观各向同性的镜面微面元（Microfacets）构成，每个微面元自身严格遵守纯粹的斯涅尔反射定律（微面元法线为 $\mathbf{m}$）。
2. **半程向量（Half Vector）**：
   对于给定的入射光方向 $\mathbf{l}$ 与观察视线方向 $\mathbf{v}$，只有那些微表面法线 $\mathbf{m}$ 恰好严格对齐于二者角平分线（半程向量 $\mathbf{h}$）的微面元，其反射光才能进入摄像机镜头：

   .. math::

      \mathbf{h} = \frac{\mathbf{l} + \mathbf{v}}{\|\mathbf{l} + \mathbf{v}\|}

------------------------------------------------------------------------
17.2 Cook-Torrance 镜面反射 BRDF 总方程形式化推导
------------------------------------------------------------------------

基于微表面假设与辐射能量守恒积分推导，Robert Cook 与 Kenneth Torrance 于 1982 年提出了著名的 **Cook-Torrance 镜面反射 BRDF 方程**：

.. math::

   f_{r, 	ext{specular}}(\mathbf{l}, \mathbf{v}) = \frac{D(\mathbf{h}) \cdot G(\mathbf{l}, \mathbf{v}) \cdot F(\mathbf{v}, \mathbf{h})}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})}

Cook-Torrance 核心三大函数与分母分量拆解
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: Cook-Torrance BRDF 核心分量微架构物理意义
   :widths: 20 30 25 25
   :header-rows: 1
   :class: tight-table

   * - BRDF 核心分量
     - 物理微架构意义
     - 依赖的输入向量
     - 工业标准选择
   * - **$D(\mathbf{h})$
法线分布函数 (NDF)**
     - 统计微表面法线 $\mathbf{m}$ 朝向等于半程向量 $\mathbf{h}$ 的概率密度
     - 宏观法线 $\mathbf{n}$, 半程向量 $\mathbf{h}$, 粗糙度 $\alpha$
     - **GGX / Trowbridge-Reitz**
   * - **$G(\mathbf{l}, \mathbf{v})$
几何遮蔽函数 (Geometry)**
     - 计算微表面之间相互自遮挡（Masking）与自阴影（Shadowing）的存活比例
     - 宏观法线 $\mathbf{n}$, 光照 $\mathbf{l}$, 视角 $\mathbf{v}$, 粗糙度 $\alpha$
     - **Smith 联合关联遮蔽模型**
   * - **$F(\mathbf{v}, \mathbf{h})$
菲涅尔方程 (Fresnel)**
     - 计算光波在微表面交界面处被反射的能量占总入射能量的比例
     - 视角 $\mathbf{v}$, 半程向量 $\mathbf{h}$, 基础反射率 $F_0$
     - **Fresnel-Schlick 近似**
   * - **$4(\mathbf{n} \cdot \mathbf{l})(\mathbf{n} \cdot \mathbf{v})$
分母修正因子**
     - 微观微分微面元立体角变换到宏观投影立体角时引入的雅可比行列式（Jacobian）
     - 宏观法线 $\mathbf{n}$, 入射方向 $\mathbf{l}$, 观察方向 $\mathbf{v}$
     - 物理积分严格推导导出

------------------------------------------------------------------------
17.3 法线分布函数 (NDF) - GGX / Trowbridge-Reitz 推导
------------------------------------------------------------------------

法线分布函数（Normal Distribution Function - NDF）$D(\mathbf{h})$ 决定了高光亮斑的形状、边缘衰减锐度与漫光晕（Tail）分布。

传统 Blinn-Phong NDF 与 GGX 的物理优劣
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- 传统的 Blinn-Phong NDF（$D_{	ext{Blinn}}(\mathbf{h}) = \frac{s+2}{2\pi}(\mathbf{n} \cdot \mathbf{h})^s$）高光边缘衰减过快呈指数截断，导致渲染出的金属质感过于生硬，缺乏真实世界材料常见的“柔和拖尾长光晕”。
- **Trowbridge-Reitz / GGX 分布（Walter et al. 2007）** 基于更真实的微表面粗糙度统计分布，呈现出狭窄的高亮核心与极具真实感的平滑长拖尾光晕，成为当今影视与游戏工业的绝对事实标准。

GGX 严格数学公式与感知线性化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. math::

   D_{	ext{GGX}}(\mathbf{h}) = \frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}

- **粗糙度感知线性化（Roughness Remapping）**：
  若直接使用粗糙度参数作为 $\alpha$，在粗糙度较低时高光变化过于陡峭。工业界统一采用平方重映射：
  
  .. math::
     \alpha = 	ext{Roughness}^2

- **物理归一化守恒定律**：
  在整个上半球积分上，微表面在宏观法线上的投影面积总和必须严格等于宏观单位面积，即：

  .. math::
     \int_{\Omega^+} D(\mathbf{h}) (\mathbf{n} \cdot \mathbf{h}) \, d\omega_h = 1.0

------------------------------------------------------------------------
17.4 几何遮蔽函数 (Geometric Shadowing) - Smith 联合模型
------------------------------------------------------------------------

在微观粗糙表面上，部分微面元发射的反射光会被相邻的微表面微观凸起所阻挡：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     微表面微观遮蔽 (Masking) 与阴影 (Shadowing)         |
   +-------------------------------------------------------------------------+

        入射光 l                       出射视线 v
          \                             /
           \      自阴影 (Shadowing)   /      自遮蔽 (Masking)
            \       +---+             /         +---+
             \     /     \           /         /     \
              \   /       \         /         /       \
   ------------+-+---------+-------+---------+---------+----------------
               入射光被前方阻挡    微表面反射光被视线前方的微表面阻挡!

Smith 联合遮蔽模型 (Smith Joint Masking-Shadowing)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Smith 假设微表面法线与微表面高度相互独立，将双向几何遮蔽分解为光照方向的遮蔽 $G_1(\mathbf{l})$ 与视线方向的遮蔽 $G_1(\mathbf{v})$ 的乘积：

.. math::

   G(\mathbf{l}, \mathbf{v}) = G_1(\mathbf{l}) \cdot G_1(\mathbf{v})

采用 Schlick-GGX 近似形式：

.. math::

   G_1(\mathbf{v}) = \frac{\mathbf{n} \cdot \mathbf{v}}{(\mathbf{n} \cdot \mathbf{v})(1 - k) + k}

针对直接光照（Direct Lighting），常数 $k$ 为：

.. math::

   k_{	ext{direct}} = \frac{(\alpha + 1)^2}{8} = \frac{(	ext{Roughness}^2 + 1)^2}{8}

工业级可见性函数 (Visibility Term) 合并优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 HLSL 着色器实现中，为了避免重复计算除法与乘法，工业界通常将几何函数 $G$ 与分母 $4(\mathbf{n}\cdot\mathbf{l})(\mathbf{n}\cdot\mathbf{v})$ 合并为统一的**可见性函数（Visibility Term $V$）**：

.. math::

   V(\mathbf{l}, \mathbf{v}) = \frac{G(\mathbf{l}, \mathbf{v})}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})} = \frac{0.5}{(\mathbf{n} \cdot \mathbf{l}) \sqrt{(\mathbf{n} \cdot \mathbf{v})^2(1 - \alpha^2) + \alpha^2} + (\mathbf{n} \cdot \mathbf{v}) \sqrt{(\mathbf{n} \cdot \mathbf{l})^2(1 - \alpha^2) + \alpha^2}}

此时 Cook-Torrance 镜面项优雅地简化为：

.. math::

   f_{r, 	ext{specular}} = D(\mathbf{h}) \cdot V(\mathbf{l}, \mathbf{v}) \cdot F(\mathbf{v}, \mathbf{h})

------------------------------------------------------------------------
17.5 菲涅尔方程 (Fresnel Equations) 与 Fresnel-Schlick 近似
------------------------------------------------------------------------

光线在两种折射率不同的介质交界面上传播时，一部分发生折射进入介质，另一部分发生反射。**菲涅尔反射率随入射角增大而急剧上升**。

Fresnel-Schlick 经典经验近似方程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

精确的麦克斯韦电磁菲涅尔方程包含复数与极化分量，计算极其沉重。Christophe Schlick 于 1994 年提出的多项式近似具有高达 99% 的物理精确度与极高的 GPU 执行效率：

.. math::

   F_{	ext{Schlick}}(\mathbf{v}, \mathbf{h}) = F_0 + (1.0 - F_0) \Big( 1.0 - (\mathbf{v} \cdot \mathbf{h}) \Big)^5

- **基础反射率 $F_0$**：表示光线沿宏观表面法线垂直入射（$	heta = 0^\circ$）时的反射能量比例。

电介质 (Dielectrics) 与金属导体 (Conductors) 的光学物理差异
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 电介质与金属光学反射物理特征对照
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 材质类别
     - $F_0$ 基础反射率特征
     - 折射光与次表面行为
     - 宏观着色表现
   * - **电介质 (绝缘体)
(塑料/木材/水/皮肤)**
     - **极低且非彩色**
标量 $F_0 \approx 0.02 \sim 0.08$
(默认通用参考值: **0.04**)
     - 光线穿透进入内部介质，发生多次散射与吸收后溢出形成**漫反射 (Diffuse)**
     - 高光反射为纯白光源色；物体固有色完全由漫反射项决定
   * - **金属导体
(金/银/铜/铁)**
     - **极高且具色彩**
RGB 向量 $F_0 \approx 0.70 \sim 0.98$
(如纯金: `(1.00, 0.71, 0.29)`)
     - 内部海量自由电子瞬间吸收折射光能（消光系数 $k \gg 0$），**绝对零漫反射 ($k_d = 0$)**
     - 高光反射呈现金属特有色彩；物体完全没有漫反射颜色

------------------------------------------------------------------------
17.6 工业级金属度-粗糙度 (Metallic-Roughness) 材质流与 HLSL 实现
------------------------------------------------------------------------

在现代工业界（Unreal Engine, Unity, glTF 2.0），材质流统一采用 **BaseColor-Metallic-Roughness** 参数化模型：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  金属度-粗糙度材质参数流能量解耦与守恒流程              |
   +-------------------------------------------------------------------------+

   输入参数: BaseColor (RGB), Metallic (0~1), Roughness (0~1)
        |
        +---> 1. 基础反射率融合: F0 = lerp(0.04, BaseColor, Metallic)
        |
        +---> 2. 镜面高光系数: ks = FresnelSchlick(F0, v, h)
        |
        +---> 3. 漫反射能量守恒剔除: kd = (1.0 - ks) * (1.0 - Metallic)
        |        (注: 纯金属 Metallic=1 时, kd 严格归零!)
        |
        v
   [ 最终合成 BRDF ]: f_r = kd * (BaseColor / PI) + D * V * F

完整工业级 HLSL PBR 着色器代码实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: hlsl

   #define PI 3.14159265359f

   // 1. GGX / Trowbridge-Reitz 法线分布函数
   float DistributionGGX(float3 N, float3 H, float roughness)
   {
       float a = roughness * roughness;
       float a2 = a * a;
       float NdotH = max(dot(N, H), 0.0f);
       float NdotH2 = NdotH * NdotH;

       float denom = (NdotH2 * (a2 - 1.0f) + 1.0f);
       denom = PI * denom * denom;

       return a2 / max(denom, 0.0000001f); // 防除零保护
   }

   // 2. Smith 联合几何可见性函数 (合并 4*NdotL*NdotV 分母优化)
   float VisibilitySmith(float NdotV, float NdotL, float roughness)
   {
       float a = roughness * roughness;
       float a2 = a * a;

       float ggxV = NdotL * sqrt(NdotV * NdotV * (1.0f - a2) + a2);
       float ggxL = NdotV * sqrt(NdotL * NdotL * (1.0f - a2) + a2);

       return 0.5f / max(ggxV + ggxL, 0.0000001f);
   }

   // 3. Fresnel-Schlick 菲涅尔近似
   float3 FresnelSchlick(float cosTheta, float3 F0)
   {
       return F0 + (1.0f - F0) * pow(saturate(1.0f - cosTheta), 5.0f);
   }

   // 4. Cook-Torrance 直接光照完整着色解算
   float3 EvaluateCookTorrancePBR(
       float3 N, float3 V, float3 L, float3 lightRadiance,
       float3 albedo, float metallic, float roughness)
   {
       float3 H = normalize(V + L);
       float NdotV = max(dot(N, V), 0.00001f);
       float NdotL = max(dot(N, L), 0.00001f);
       float HdotV = max(dot(H, V), 0.0f);

       // 依据金属度解算基础反射率 F0
       float3 F0 = lerp(float3(0.04f, 0.04f, 0.04f), albedo, metallic);

       // 计算 D, V, F 三大核心项
       float  D = DistributionGGX(N, H, roughness);
       float  Vis = VisibilitySmith(NdotV, NdotL, roughness);
       float3 F = FresnelSchlick(HdotV, F0);

       // 镜面反射项
       float3 specular = D * Vis * F;

       // 能量守恒分配漫反射系数 kd
       float3 kS = F;
       float3 kD = (float3(1.0f, 1.0f, 1.0f) - kS) * (1.0f - metallic);

       // 漫反射项 (朗伯漫反射除以 PI)
       float3 diffuse = kD * (albedo / PI);

       // 渲染方程单光源最终出射辐射率累加
       return (diffuse + specular) * lightRadiance * NdotL;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从微表面理论第一性原理出发，系统推导了 Cook-Torrance 镜面反射 BRDF 方程、GGX 法线分布函数的长尾高光特性、Smith 联合几何遮蔽可见性优化，以及基于 Fresnel-Schlick 方程与金属度-粗糙度解耦的严格能量守恒材质管线。

然而，Cook-Torrance 模型假设折射进入介质的光线均在微观同一点就地散射出射，这对于玉石、蜡烛、牛奶以及最关键的**人类皮肤**等半透明材质而言会呈现出非物理的死黑阴影。下一章我们将深入**次表面散射 (SSS) 与半透明材质：偶极子扩散剖面、屏幕空间 SSS 与预积分皮肤渲染**，深入解构光子在介质内部长距离扩散的 BSSRDF 物理微架构与实时近似算法。
