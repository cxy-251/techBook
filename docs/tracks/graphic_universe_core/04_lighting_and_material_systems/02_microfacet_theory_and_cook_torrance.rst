========================================================================
Chapter 17: 微表面理论与 Cook-Torrance BRDF：D、G、F 三大核心项深度推导
========================================================================

.. note:: 前置背景与认知承接
   前一章从辐射度量学物理底座出发，推导了辐射通量、辐照度、辐射率、BRDF 微分定义以及理想朗伯漫反射的归一化因子。在真实物理世界中，除了各向同性体散射的漫反射外，绝大部分材质（如金属、光滑塑料、陶瓷、水面）的高光反射特性均由表面微观几何粗糙度决定。宏观上看似光滑的平面，在微米尺度上布满了朝向各异的微小镜面凹凸。1982 年 Robert Cook 与 Kenneth Torrance 提出的 Cook-Torrance 微表面镜面反射模型，奠定了现代工业界（Unreal Engine 5、Unity HDRP、Filament、Frostbite）物理渲染的绝对标准基石。本章将系统剖析微表面统计假设、分母微观到宏观投影转换因子的严密数学推导、法线分布函数（NDF - GGX/Trowbridge-Reitz）、几何遮挡函数（Smith Joint Masking-Shadowing）以及菲涅尔反射定律（Fresnel-Schlick 及其导体复折射率解析解），并在 GPU HLSL/GLSL 着色器层面给出无除零隐患的极致优化算子。

------------------------------------------------------------------------
17.1 微表面模型 (Microfacet Theory) 统计假设与物理建模
------------------------------------------------------------------------

在微观尺度（$1\mu	ext{m} \sim 100\mu	ext{m}$）下，光学平整的光滑表面是不存在的。微表面理论（Microfacet Theory）基于统计光学做出了三大核心假设：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       微表面理论三大物理统计假设                        |
   +-------------------------------------------------------------------------+

   [ 假设 1: 完美微观镜面 ]
   * 宏观表面由无数微小的局部光学平整平面 (Microfacets) 构成；
   * 每个微表面各自具有独立的微观法线 m，且完全遵循理想几何光学镜面反射规律。

   [ 假设 2: 严格半程向量对齐 (Half-Vector Alignment) ]
   * 只有当微表面的微观法线 m 恰好严格对齐于入射光向量 l 与视线观察向量 v 的
     半程向量 h 时 (m = h)，该微表面反射的光线才能精准射入相机镜头！
     半程向量定义: h = (l + v) / ||l + v||

   [ 假设 3: 统计宏观聚合 ]
   * 单个像素覆盖了数以亿计的微表面；
   * 宏观反射光强度由“法线朝向 h 的微表面比例 (D)”、“光线未被阻挡的比例 (G)”
     以及“微表面自身的菲涅尔反射率 (F)”共同决定。

Cook-Torrance 镜面反射 BRDF 表达式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

基于上述物理假设，Cook-Torrance 镜面反射双向反射分布函数具有如下经典的四因子乘积形式：

.. math::

   f_{r, 	ext{specular}}(\mathbf{l}, \mathbf{v}) = \frac{D(\mathbf{h}) \, G(\mathbf{l}, \mathbf{v}, \mathbf{h}) \, F(\mathbf{l}, \mathbf{h})}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})}

.. list-table:: Cook-Torrance BRDF 四大核心组件物理含义
   :widths: 15 25 35 25
   :header-rows: 1
   :class: tight-table

   * - 核心组件
     - 符号与命名
     - 物理微架构意义
     - 典型工业标准模型
   * - **D 项**
     - $D(\mathbf{h})$ 法线分布函数
     - 统计微表面法线 $\mathbf{m}$ 与半程向量 $\mathbf{h}$ 一致的面积概率密度
     - GGX (Trowbridge-Reitz)
   * - **G 项**
     - $G(\mathbf{l}, \mathbf{v}, \mathbf{h})$ 几何遮蔽函数
     - 评估微表面之间相互产生的自阴影（Shadowing）与自遮挡（Masking）比例
     - Smith Height-Correlated
   * - **F 项**
     - $F(\mathbf{l}, \mathbf{h})$ 菲涅尔项
     - 微观单晶镜面在特定局部入射角下的电磁波反射能量比率
     - Fresnel-Schlick 近似
   * - **分母因子**
     - $4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})$
     - **几何投影校正因子**：完成从微观微表面局部立体角到宏观微分面积的雅可比变换
     - 第一性原理积分推导解

分母 $4(\mathbf{n} \cdot \mathbf{l})(\mathbf{n} \cdot \mathbf{v})$ 的第一性原理严格数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

分母中的 $4(\mathbf{n} \cdot \mathbf{l})(\mathbf{n} \cdot \mathbf{v})$ 经常被误认为是经验配凑参数。实际上，它是**从微观立体角到宏观积分测度的雅可比行列式变换因子**。

1. 设宏观微分面积为 $dA$，微表面微观总面积为 $dA_m$。根据微表面几何投影，法线朝向 $\mathbf{h}$ 的微表面在宏观平面的投影面积比例由法线分布函数给出：$dA_m(\mathbf{h}) = D(\mathbf{h}) (\mathbf{n} \cdot \mathbf{h}) \, d\omega_h \, dA$；
2. 单个微表面反射的总微分通量为 $d\Phi_h = L_i \, d\omega_i \, dA_m(\mathbf{h}) (\mathbf{l} \cdot \mathbf{h}) F(\mathbf{l}, \mathbf{h})$；
3. 出射光线立体角 $d\omega_o$ 与半程向量立体角 $d\omega_h$ 的微分关系满足球坐标映射变换：
   由于 $\mathbf{v}$ 关于 $\mathbf{h}$ 与 $\mathbf{l}$ 镜面对称，通过雅可比行列式计算得到：
   
   .. math::
   
      d\omega_h = \frac{d\omega_o}{4 (\mathbf{l} \cdot \mathbf{h})}

4. 将微表面微分通量代入宏观 BRDF 定义式 $f_r = \frac{dL_o}{dE_i} = \frac{d\Phi_h / (dA \cos	heta_v \, d\omega_o)}{L_i \cos	heta_l \, d\omega_i}$，消去中间变量后，分母中精确析出 $4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})$ 项！

------------------------------------------------------------------------
17.2 法线分布函数 (NDF / D 项)：从 Beckmann 到 GGX
------------------------------------------------------------------------

法线分布函数（Normal Distribution Function - NDF）$D(\mathbf{h})$ 描述了表面微观粗糙度在空间半球上的统计取向分布。

NDF 的归一化物理约束方程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

任何物理合法的 NDF 必须在整个半球空间 $\Omega^+$ 上满足**投影面积守恒公理**：所有微表面在宏观法线 $\mathbf{n}$ 方向上的垂直投影面积之和，必须严格等于宏观单位平面面积（即数值 1）：

.. math::

   \int_{\Omega^+} D(\mathbf{m}) (\mathbf{n} \cdot \mathbf{m}) \, d\omega_m = 1

若 NDF 违反此积分归一化条件，材质在粗糙度变化时将凭空增减总反射能量，导致光照过曝或暗化。

经典 NDF 演进与缺陷对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **Blinn-Phong NDF**：$D_{	ext{Blinn}}(\mathbf{h}) = \frac{\alpha + 2}{2\pi} (\mathbf{n} \cdot \mathbf{h})^\alpha$，高光边缘衰减过快，呈现类似塑料的生硬高光切边；
2. **Beckmann NDF**：$D_{	ext{Beckmann}}(\mathbf{h}) = \frac{1}{\pi \alpha^2 (\mathbf{n} \cdot \mathbf{h})^4} \exp\left( -\frac{1 - (\mathbf{n} \cdot \mathbf{h})^2}{\alpha^2 (\mathbf{n} \cdot \mathbf{h})^2} \right)$，基于高斯斜率分布推导，但在极粗糙表面下高光衰减依然偏陡。

GGX (Trowbridge-Reitz) 分布函数与长尾物理特征
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

2007 年 Walter 等人将 Trowbridge-Reitz 分布引入计算机图形学（工业界通称 **GGX**），其数学闭式解如下：

.. math::

   D_{	ext{GGX}}(\mathbf{h}, \alpha) = \frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                GGX vs 经典高斯分布的光强空间拖尾曲线对比               |
   +-------------------------------------------------------------------------+

   反射光辐射率
      ^
      |         | | (高光中心亮点)
      |        /   \
      |       /     \
      |      /       \      GGX 分布: 具有极宽的“长尾光晕 (Long Heavy Tail)”
      |  ---/---------\---  完美匹配真实镀铬、金属拉丝表面的微观漫晕散射！
      |  _--           --_
      | /  Beckmann      \  Beckmann/Phong: 高光边缘以高斯指数迅速坠跌归零
      +------------------------------------------------------------> 视线夹角

- **Disney 感知线性粗糙度重映射**：在美术创作中，线性调节粗糙度参数 $r \in [0, 1]$ 时，高光大小变化极不均匀。Disney 提出令物理参数 $\alpha = r^2$（即 $\alpha = 	ext{Roughness}^2$），使粗糙度滑块在感知视觉上呈现完全线性的高光扩散过渡。

------------------------------------------------------------------------
17.3 几何阴影遮蔽函数 (G 项) 与 Smith 联合遮蔽模型
------------------------------------------------------------------------

微观表面的凹凸起伏必然导致微表面之间发生相互遮挡。几何函数（Geometric Shadowing-Masking Function）$G(\mathbf{l}, \mathbf{v}, \mathbf{h}) \in [0, 1]$ 描述了未被几何结构阻挡的光线比例。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       微表面几何阻挡的两大物理形态                      |
   +-------------------------------------------------------------------------+

   [ 1. 光源自阴影 (Light Shadowing) ]            [ 2. 视线自遮蔽 (View Masking) ]
         \ 入射光线 l                                              / 视线 v
          \                                                       /
           v                                                     ^
       /\      /\                                            /\ /    /\
      /  \    /  \                                          /  \    /  \
     /    \--/    \                                        /    \--/    \
           ^ 前方微表面阻挡了入射光                                 ^ 前方微表面阻挡了反射出射光

Smith 几何模型的单向遮蔽函数 $G_1$
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据 Smith 统计模型，微表面在单向入射方向 $\mathbf{v}$ 上的不可见概率由微表面高度分布的积分导出。对应于 GGX 法线分布的单向 Smith 遮蔽函数 $G_1$ 严格为：

.. math::

   G_1(\mathbf{v}, \alpha) = \frac{2 (\mathbf{n} \cdot \mathbf{v})}{(\mathbf{n} \cdot \mathbf{v}) + \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{v})^2}}

高度相关 Smith 联合遮蔽函数 (Height-Correlated Smith G2)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传统 Smith 模型假设光线方向 $\mathbf{l}$ 与视线方向 $\mathbf{v}$ 的遮挡是相互统计独立的（$G = G_1(\mathbf{l}) \cdot G_1(\mathbf{v})$）。然而在物理真实中，如果一个微表面处于较高的海拔位置，它既不容易被入射光遮蔽，也不容易被观察视线遮蔽——**遮挡在高度维度存在极强的自相关性（Correlation）**。

Eric Heitz 于 2014 年给出了高度相关 Smith 遮蔽函数的精确形式：

.. math::

   G(\mathbf{l}, \mathbf{v}, \alpha) = \frac{2 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})}{(\mathbf{n} \cdot \mathbf{v}) \Lambda(\mathbf{l}, \alpha) + (\mathbf{n} \cdot \mathbf{l}) \Lambda(\mathbf{v}, \alpha)}

其中 $\Lambda(\mathbf{x}, \alpha) = \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{x})^2}$。

可视性函数 (Visibility Term, $V$ 项) 的合并与除法消除
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 GPU 着色器实现中，Cook-Torrance BRDF 的分母项 $4(\mathbf{n} \cdot \mathbf{l})(\mathbf{n} \cdot \mathbf{v})$ 与分子中的 $G$ 项具备相同的代数公因式。工业界直接定义**可视性函数（Visibility Function, $V$）**：

.. math::

   V(\mathbf{l}, \mathbf{v}, \alpha) = \frac{G(\mathbf{l}, \mathbf{v}, \alpha)}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})} = \frac{0.5}{(\mathbf{n} \cdot \mathbf{v}) \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{l})^2} + (\mathbf{n} \cdot \mathbf{l}) \sqrt{\alpha^2 + (1 - \alpha^2)(\mathbf{n} \cdot \mathbf{v})^2}}

- **工程收益**：将复杂的 $G$ 项与分母彻底合并为一个单一的 $V$ 函数，**完全消除了昂贵的浮点除法运算，并且从数学上根除了 $(\mathbf{n} \cdot \mathbf{l}) 	o 0$ 时的除零溢出崩溃隐患**！

------------------------------------------------------------------------
17.4 菲涅尔项 (F 项)：麦克斯韦方程与 Fresnel-Schlick 拟合
------------------------------------------------------------------------

菲涅尔效应描述了光线投射在不同介质的分界面时，反射能量与折射能量随入射角动态分配的电磁学规律。

电介质 (Dielectrics) vs 金属导体 (Conductors)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 电介质与导体光学反射特性对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 物质分类
     - 经典材质举例
     - 基础反射率 $F_0$ (垂直入射)
     - 掠射角反射率 $F_{90}$ 与色彩
   * - **电介质 (绝缘体)**
     - 塑料、玻璃、水、木材、皮肤
     - 极低（$2\% \sim 5\%$，纯灰度常数）
     - $90^\circ$ 掠射角剧烈上升至 $100\%$；高光呈光源白色
   * - **导体 (金属)**
     - 黄金、白银、纯铜、铝、铁
     - **极高（$70\% \sim 95\%$，带强彩色调）**
     - $90^\circ$ 掠射角上升至 $100\%$ 白色；**无内部折射漫反射**（光子被自由电子吸收）

Fresnel-Schlick 工业级经验近似公式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1994 年 Christophe Schlick 提出的多项式经验逼近，将复杂的麦克斯韦复数三阶方程简化为单条高效公式：

.. math::

   F_{	ext{Schlick}}(\mathbf{v}, \mathbf{h}, F_0) = F_0 + (1 - F_0) \left( 1 - (\mathbf{v} \cdot \mathbf{h}) \right)^5

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Fresnel-Schlick 反射率随观察夹角变化曲线            |
   +-------------------------------------------------------------------------+

   反射率 F
    100% |                                                     / (掠射角 F90 = 1.0)
         |                                                    /
         |                                                   /
         |                                                  /
         |                                                 /
      F0 +------------------------------------------------'
         +------------------------------------------------------------> 夹角 theta
         0度 (正入射 Normal)                                  90度 (掠射 Grazing)

粗糙度对掠射角菲涅尔的衰减修正 (Roughness-Modified Fresnel)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在粗糙表面上，微表面在掠射角处相互遮蔽严重，导致宏观掠射角反射率无法达到理想的 $100\%$。Sébastien Lagarde 给出修正公式：

.. math::

   F_{	ext{Roughness}}(\mathbf{v}, \mathbf{h}, F_0, \alpha) = F_0 + \left( \max(1 - \alpha, F_0) - F_0 \right) \left( 1 - (\mathbf{v} \cdot \mathbf{h}) \right)^5

------------------------------------------------------------------------
17.5 工业级 Cook-Torrance BRDF 着色器算子工程实现
------------------------------------------------------------------------

以下给出在现代高性能渲染管线中执行的 Cook-Torrance 镜面反射与能量守恒漫反射组合着色器实现（HLSL 规范）：

.. code-block:: hlsl

   // 常量定义与浮点下溢防护
   #define PBR_PI 3.14159265359f
   #define PBR_EPSILON 1e-5f

   // 1. GGX / Trowbridge-Reitz 法线分布函数 (D 项)
   float DistributionGGX(float NdotH, float roughness) {
       float a = roughness * roughness;
       float a2 = a * a;
       float NdotH2 = NdotH * NdotH;
       
       float denom = (NdotH2 * (a2 - 1.0f) + 1.0f);
       denom = PBR_PI * denom * denom;
       
       return a2 / max(denom, PBR_EPSILON);
   }

   // 2. 合并分母的 Height-Correlated Smith 联合可视性函数 (V 项)
   float VisibilitySmithGGXCorrelated(float NdotV, float NdotL, float roughness) {
       float a = roughness * roughness;
       float a2 = a * a;
       
       float lambdaV = NdotL * sqrt(NdotV * (NdotV - a2 * NdotV) + a2);
       float lambdaL = NdotV * sqrt(NdotL * (NdotL - a2 * NdotL) + a2);
       
       return 0.5f / max(lambdaV + lambdaL, PBR_EPSILON);
   }

   // 3. Fresnel-Schlick 菲涅尔近似项 (F 项)
   float3 FresnelSchlick(float VdotH, float3 F0) {
       float fc = pow(1.0f - VdotH, 5.0f);
       return F0 + (1.0f - F0) * fc;
   }

   // 4. 完整 Cook-Torrance 表面点着色解算
   float3 EvaluateCookTorranceBRDF(
       float3 N, float3 V, float3 L, 
       float3 albedo, float metallic, float roughness) 
   {
       float3 H = normalize(V + L);
       
       float NdotL = max(dot(N, L), 0.0f);
       float NdotV = max(dot(N, V), 1e-4f); // 避免观察掠射角完全除零
       float NdotH = max(dot(N, H), 0.0f);
       float VdotH = max(dot(V, H), 0.0f);
       
       // 电介质基础反射率默认 0.04 (塑料/常规绝缘体)，金属则直接使用 Albedo 自身作为彩色 F0
       float3 F0 = lerp(float3(0.04f, 0.04f, 0.04f), albedo, metallic);
       
       // 求解 D、V、F 三项
       float D = DistributionGGX(NdotH, roughness);
       float V_term = VisibilitySmithGGXCorrelated(NdotV, NdotL, roughness);
       float3 F = FresnelSchlick(VdotH, F0);
       
       // 镜面高光反射项 (分母已内嵌于 V 项中)
       float3 specularBRDF = D * V_term * F;
       
       // 能量守恒: 漫反射能量比例 kD = (1 - F) * (1 - metallic)
       float3 kS = F;
       float3 kD = (float3(1.0f, 1.0f, 1.0f) - kS) * (1.0f - metallic);
       
       // 漫反射项 (Lambertian)
       float3 diffuseBRDF = kD * (albedo / PBR_PI);
       
       // 最终反射出射辐射率 (乘以入射辐照度因子 NdotL)
       return (diffuseBRDF + specularBRDF) * NdotL;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了 Cook-Torrance 微表面理论的物理统计基础、分母雅可比几何投影校正推导、GGX (Trowbridge-Reitz) 长尾法线分布、高度相关 Smith 联合几何遮蔽模型 $V$ 项合并，以及电介质与导体麦克斯韦菲涅尔反射定律与 GPU 极致优化算子。

在确立了微观 BRDF 的物理数学大厦之后，下一章我们将深入工业级材质管线的数据资产集成与工作流——**工业级 PBR 材质模型：金属度/粗糙度工作流与镜面反射/光泽度工作流解析**，剖析 G-Buffer 压缩存储通道排布、两种主流工作流的互相转换矩阵，以及电介质与金属交界处的物理假走样消除技巧。
