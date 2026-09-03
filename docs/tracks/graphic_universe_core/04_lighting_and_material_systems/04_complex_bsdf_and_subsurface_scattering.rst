========================================================================
Chapter 19: 复杂材质表述：次表面散射、各向异性、清漆与织物微纤维
========================================================================

.. note:: 前置背景与认知承接
   前一章深入剖析了标准金属度/粗糙度与镜面反射/光泽度两大工业级 PBR 工作流，建立了 G-Buffer 4 槽位极限压缩排布与 Cook-Torrance 硬表面着色管线。然而，经典 BRDF 模型基于“局域单点反射（Local Illumination, $x_i = x_o$）”与“均质各向同性（Isotropic）”的理想化假设，无法准确还原真实世界中广泛存在的半透明透光、微观定向沟槽、多层复合涂层与微纤维织物。人类皮肤、玉石、蜡烛依赖**次表面散射（BSSRDF）**呈现通透温润感；拉丝金属、唱片、发丝展现出被拉伸延展的**各向异性高光**；汽车金属车漆展现出底层珠光与表层清亮反射共存的**双层清漆（Clear Coat）**结构；天鹅绒与丝绸在掠射边缘呈现柔和的**微纤维光晕（Sheen）**。本章将系统解构超越标准 BRDF 的高阶材质物理方程、数学推导与实时着色器实现方案。

------------------------------------------------------------------------
19.1 从 BRDF 到 BSSRDF：次表面散射物理机理与偶极子扩散
------------------------------------------------------------------------

经典双向反射分布函数（BRDF）假设光线射入物体表面的某一点后，仅在**完全相同的空间点**发生反射与出射。对于金属与紧密致密电介质，该假设高度精确。但对于非致密或半透明介质（皮肤、脂肪、牛奶、大理石、玉石），光子会折射穿透表面，在内部微观颗粒间经历成千上万次弹性碰撞与多重散射（Multiple Scattering），最终从距离入射点一段距离 $r = \|\mathbf{x}_o - \mathbf{x}_i\|$ 的另一位置穿出表面：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                BRDF 局域反射 vs BSSRDF 次表面散射物理路径对比           |
   +-------------------------------------------------------------------------+

   [ 经典 BRDF (单点局域反射) ]               [ BSSRDF (非局域次表面多次散射) ]
          入射光 Li       出射光 Lo                  入射光 Li(xi)       出射光 Lo(xo)
             \             /                            \                     /
              \           /                              \                   /
   ============\=========/=============       ============\=================/=============
                \       / (折射光在极小局域                 \   o   *   o  *  /
                 \     /   内被吸收或返回)                   \ *  o   *  o  / (内部多次散射)
                  \   /                                       *   o  *   o
                   \_/                                         \_______/
                                                                距离 r

BSSRDF 8 维双向散射面反射分布函数
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

次表面出射辐射率由**双向散射面反射分布函数（BSSRDF - Bidirectional Scattering-Surface Reflectance Distribution Function）** $S(\mathbf{x}_i, \omega_i; \mathbf{x}_o, \omega_o)$ 严密描述：

.. math::

   L_o(\mathbf{x}_o, \omega_o) = \int_{A} \int_{\Omega} S(\mathbf{x}_i, \omega_i; \mathbf{x}_o, \omega_o) L_i(\mathbf{x}_i, \omega_i) (\omega_i \cdot \mathbf{n}_i) \, d\omega_i \, dA(\mathbf{x}_i)

Jensen 偶极子扩散近似 (Dipole Diffusion Approximation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于 8 维积分无法直接数值求解，Henrik Wann Jensen 等人将 BSSRDF 解耦为入射菲涅尔透过率 $F_t$、出射菲涅尔透过率 $F_t$ 与各向同性**径向漫反射扩散剖面（Radial Diffusion Profile $R_d(r)$）**：

.. math::

   S(\mathbf{x}_i, \omega_i; \mathbf{x}_o, \omega_o) \approx \frac{1}{\pi} F_t(\mathbf{x}_i, \omega_i) R_d(\|\mathbf{x}_o - \mathbf{x}_i\|) F_t(\mathbf{x}_o, \omega_o)

扩散剖面 $R_d(r)$ 描述了光子在介质内部穿行距离 $r$ 后逸出表面的能量密度分布。Jensen 引入了虚拟镜像光源（偶极子 Dipole），使介质表面满足零通量外推边界条件，推导出解析公式：

.. math::

   R_d(r) = \frac{\alpha'}{4\pi} \left[ z_r \left( \sigma_{	ext{tr}} + \frac{1}{d_r} \right) \frac{e^{-\sigma_{	ext{tr}} d_r}}{d_r^2} + z_v \left( \sigma_{	ext{tr}} + \frac{1}{d_v} \right) \frac{e^{-\sigma_{	ext{tr}} d_v}}{d_v^2} \right]

其中 $\sigma_{	ext{tr}} = \sqrt{3 \sigma_a \sigma'_s}$ 为有效有效衰减系数，$\alpha' = \sigma'_s / (\sigma_a + \sigma'_s)$ 为约化散射反照率，$z_r, z_v$ 分别为实光源与虚光源距表面的法向距离，$d_r, d_v$ 为采样点到两光源的空间欧氏距离。

------------------------------------------------------------------------
19.2 实时次表面散射：屏幕空间模糊 (SSSSS) 与预积分皮肤着色
------------------------------------------------------------------------

在实时游戏引擎与交互管线中，直接对全场景几何网格执行表面积多重积分 $dA(\mathbf{x}_i)$ 计算成本不可接受。工业界衍生出两大实时解算流派：

方案 1：屏幕空间次表面散射 (Screen-Space SSS / SSSSS)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Jorge Jimenez 等人提出的 **SSSSS（Separable Screen-Space Subsurface Scattering）** 算法，将 3D 次表面散射近似为在 2D 屏幕空间对漫反射光照图进行的自适应可分离核卷积：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  屏幕空间次表面散射 (SSSSS) 执行流水线                  |
   +-------------------------------------------------------------------------+

   [ Pass 1: 几何与常规着色通道 (GBuffer / Base Pass) ]
   * 输出普通漫反射颜色缓冲 DiffuseColor 与镜面高光缓冲 SpecularColor
   * 输出 SSS 材质掩码 (SSS Profile ID) 与局部散射平均自由程 (Mean Free Path)
        |
        v
   [ Pass 2: 水平方向 1D 自适应卷积模糊 (Horizontal Blur Pass) ]
   * 沿屏幕 X 轴采样邻近像素漫反射光照
   * 采用 6 阶高斯函数拟合真实皮肤扩散剖面 (Sum of Gaussians):
     R 通道扩散距离最远 (红润血色)，G 通道次之，B 通道最近 (几乎不扩散)
   * 结合深度缓冲 Depth 执行双边滤波 (Bilateral Weight)，跨越深度断层时截断卷积！
        |
        v
   [ Pass 3: 垂直方向 1D 自适应卷积模糊 (Vertical Blur Pass) ]
   * 沿屏幕 Y 轴对 Pass 2 结果二次卷积，输出柔化后的通透皮肤漫反射
        |
        v
   [ Pass 4: 镜面反射叠加 (Specular Re-composite) ]
   * 将清晰锐利的 Cook-Torrance 镜面高光与 SSS 漫反射叠加 (高光绝对不能被模糊!)

.. list-table:: 皮肤次表面散射 6 阶高斯拟合核参数 (Sum-of-Gaussians Profile)
   :widths: 15 25 20 20 20
   :header-rows: 1
   :class: tight-table

   * - 高斯阶数 $i$
     - 方差 $\sigma_i^2$ (扩散宽度)
     - 红色权重 $w_{r,i}$
     - 绿色权重 $w_{g,i}$
     - 蓝色权重 $w_{b,i}$
   * - **高斯 1**
     - 0.0064
     - 0.233
     - 0.455
     - 0.649
   * - **高斯 2**
     - 0.0484
     - 0.100
     - 0.118
     - 0.123
   * - **高斯 3**
     - 0.1870
     - 0.118
     - 0.198
     - 0.000
   * - **高斯 4**
     - 0.5670
     - 0.113
     - 0.003
     - 0.000
   * - **高斯 5**
     - 1.9900
     - 0.358
     - 0.004
     - 0.000
   * - **高斯 6**
     - 7.4100
     - 0.078
     - 0.000
     - 0.000

方案 2：预积分皮肤着色 (Pre-Integrated Skin Shading)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对移动端或算力受限平台，Penner 提出的**预积分 LUT 方案**将球体表面的次表面散射卷积结果离线烘焙至 2D 查找表：
- **查找表横轴**：$\mathbf{N} \cdot \mathbf{L}$（法线与光照夹角余弦，表征几何迎光度）；
- **查找表纵轴**：$1/r$（网格局部曲率 Curvature，表征皮肤表面凹凸弯曲程度，如鼻尖曲率大、脸颊曲率小）；
- **着色器执行**：片元着色器仅需通过 `ddx(N)/ddy(N)` 导数估算曲率，单次采样 2D LUT 即可输出包含暗部红润渐变（Penumbra Bleed）的完美次表面漫反射。

.. code-block:: hlsl

   // 预积分皮肤漫反射查找 (HLSL)
   float3 EvaluatePreintegratedSkin(float NdotL, float curvature, Texture2D skinLUT, SamplerState linearSampler) {
       float2 lutUV = float2(NdotL * 0.5f + 0.5f, curvature);
       return skinLUT.Sample(linearSampler, lutUV).rgb;
   }

------------------------------------------------------------------------
19.3 各向异性材质模型 (Anisotropic BSDF) 与切线流场
------------------------------------------------------------------------

标准 Cook-Torrance 模型假设微表面法线分布关于宏观几何法线 $\mathbf{N}$ 呈轴对称分布（各向同性 Isotropic）。但当材质表面具有沿特定方向排列的微观沟槽（如拉丝金属、车床金属圈、黑胶唱片、毛发）时，光斑会沿垂直于沟槽的方向被强烈拉伸，呈现条状或环状各向异性高光。

各向异性 GGX 法线分布函数 (Anisotropic GGX NDF)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

通过在切线空间引入相互正交的切线矢量 $\mathbf{T}$ 与副切线矢量 $\mathbf{B}$，并为两轴分配独立的粗糙度分量 $\alpha_x, \alpha_y$，Burley 与 Heitz 推导出各向异性 GGX 公式：

.. math::

   D_{	ext{aniso}}(\mathbf{m}) = \frac{1}{\pi \alpha_x \alpha_y \left[ \left( \frac{\mathbf{m} \cdot \mathbf{T}}{\alpha_x} \right)^2 + \left( \frac{\mathbf{m} \cdot \mathbf{B}}{\alpha_y} \right)^2 + (\mathbf{m} \cdot \mathbf{N})^2 \right]^2}

其中感知粗糙度 $R \in [0, 1]$ 与各向异性度 $A \in [-1, 1]$ 转换为分量粗糙度的经典映射关系为：

.. math::

   \alpha = R^2, \quad \alpha_x = \alpha \sqrt{1 + A}, \quad \alpha_y = \alpha \sqrt{1 - A}

各向异性联合遮蔽可见性项 (Anisotropic Smith Visibility)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. math::

   V_{	ext{aniso}} = \frac{0.5}{\Lambda_L + \Lambda_V}

.. math::

   \Lambda_V = \sqrt{ \alpha_x^2 (\mathbf{V} \cdot \mathbf{T})^2 + \alpha_y^2 (\mathbf{V} \cdot \mathbf{B})^2 + (\mathbf{V} \cdot \mathbf{N})^2 }

.. math::

   \Lambda_L = \sqrt{ \alpha_x^2 (\mathbf{L} \cdot \mathbf{T})^2 + \alpha_y^2 (\mathbf{L} \cdot \mathbf{B})^2 + (\mathbf{L} \cdot \mathbf{N})^2 }

切线流场 (Tangent Flow Map) 控制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在复杂曲面上绘制如唱片同心圆或发旋高光，引擎采用 2 通道 **各向异性流向贴图（Anisotropic Direction Map）**。贴图存储切线在切平面的旋转角度 $	heta$，运行时动态重构正交切线矢量：

.. code-block:: hlsl

   // 切线矢量在表面切平面上的动态旋转
   float2 dir = g_AnisotropyMap.Sample(g_LinearSampler, uv).rg * 2.0f - 1.0f;
   float3 T_rotated = normalize(T * dir.x + B * dir.y);
   float3 B_rotated = normalize(cross(N, T_rotated));

------------------------------------------------------------------------
19.4 清漆双层涂层 (Clear Coat) 与能量守恒层叠模型
------------------------------------------------------------------------

汽车金属面漆、打蜡木地板、涂油皮革呈现出一种独特的视觉特征：底层展现出粗糙或带珠光颗粒的漫反射与金属反射，而表面覆盖着一层极平整、高反光且完全透明的薄电介质层——**清漆层（Clear Coat）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     双层 Clear Coat 能量守恒传输模型                    |
   +-------------------------------------------------------------------------+

   入射光 Li
       \
        +---- 顶层清漆镜面反射 (比例: F_coat, 极小粗糙度, F0=0.04)
        |
        v [ 穿透能量: (1.0 - F_coat) ]
   (清漆透明介质吸收衰减)
        |
        v
   [ 底层基础材质 Base Layer ] (金属/电介质混合)
        |  * 发生底层微表面反射与漫反射
        v
   [ 再次穿出清漆表面: 能量再次经过 (1.0 - F_coat) 透射折损! ]
        |
        v
   出射光 Lo = F_coat * Specular_coat + (1.0 - F_coat)^2 * Lo_base

分层着色模型数学表达 (Filament / UE5 工业规范)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设清漆层强度参数为 $C_{	ext{strength}} \in [0, 1]$，清漆层感知粗糙度为 $C_{	ext{roughness}}$，清漆层法线为 $\mathbf{N}_{	ext{coat}}$（支持独立的清漆法线贴图）：

1. **顶层清漆菲涅尔项与高光计算**：
   清漆层为纯聚氨酯/树脂电介质，其折射率 $n = 1.5$，对应垂直基础反射率 $F_{0, 	ext{coat}} = 0.04$：

   .. math::

      F_{	ext{coat}} = C_{	ext{strength}} 	imes \left( 0.04 + 0.96 	imes (1 - \mathbf{V} \cdot \mathbf{H}_{	ext{coat}})^5 \right)

   .. math::

      f_{	ext{spec, coat}} = D_{	ext{GGX}}(\mathbf{N}_{	ext{coat}}, \mathbf{H}_{	ext{coat}}, C_{	ext{roughness}}) \cdot V_{	ext{Kelemen}}(\mathbf{V} \cdot \mathbf{H}_{	ext{coat}}) \cdot F_{	ext{coat}}

2. **底层能量遮蔽与合成**：
   穿透至底层的光强被顶层镜面反射拦截，必须乘以双向透射率 $(1 - F_{	ext{coat}})$：

   .. math::

      f_{	ext{total}} = f_{	ext{spec, coat}} + f_{	ext{base}}(\mathbf{N}, \mathbf{V}, \mathbf{L}) 	imes (1.0 - F_{	ext{coat}})^2

------------------------------------------------------------------------
19.5 织物与微纤维材质模型 (Cloth & Sheen Velvet BRDF)
------------------------------------------------------------------------

布料、丝绸、粗花呢与天鹅绒的表面由纵横交错的细小圆柱形纺织纤维（Microfiber Fuzz）织成。这类材质在宏观上表现出两大反常光学特性：
1. **掠射角强烈泛光（Sheen Effect）**：在视线与法线夹角接近 90 度（掠射角）时，直立的微纤维侧壁大量反射光线，在边缘形成柔和明亮的边缘光晕；
2. **反向散射（Retro-reflection）与阴影衰减**：在正对视角下，由于纤维深处发生自遮蔽，漫反射强度大幅减弱并呈现出柔和的平坦哑光感。

Charlie 倒钟形法线分布函数 (Estevez-Kulla Sheen NDF)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Alejandro Estevez 与 Christopher Kulla 提出了专用于模拟天鹅绒绒毛反射的 **Charlie 分布模型**，其法线分布采用正弦波多项式，使法线概率密度在极度偏离宏观法线处大幅隆起：

.. math::

   D_{	ext{Charlie}}(\mathbf{m}) = \frac{\left( 2 + \frac{1}{\alpha_{	ext{sheen}}} \right) \sin(	heta_m)^{\frac{1}{\alpha_{	ext{sheen}}}}}{2\pi}

配合无微表面高度相关的 Ashikhmin 几何阴影遮蔽项：

.. math::

   V_{	ext{Ashikhmin}} = \frac{1}{4 \left( (\mathbf{N} \cdot \mathbf{L}) + (\mathbf{N} \cdot \mathbf{V}) - (\mathbf{N} \cdot \mathbf{L})(\mathbf{N} \cdot \mathbf{V}) \right)}

.. list-table:: 工业界四大复杂材质模型核心物理特性与着色器分支矩阵
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 材质扩展类型
     - 核心物理现象
     - 关键微表面/辐射数学函数
     - 典型应用材质
   * - **次表面散射 (BSSRDF)**
     - 光子内部多重散射，非局域逸出
     - Jensen 偶极子公式、6 阶高斯扩散剖面
     - 人类皮肤、玉石、蜡烛、果肉
   * - **各向异性 (Anisotropic)**
     - 定向微观沟槽拉伸高光
     - Anisotropic GGX NDF、切线流向图
     - 拉丝铝合金、金属唱片、毛发
   * - **清漆涂层 (Clear Coat)**
     - 双层分层复合结构，双向能量透射折损
     - Kelemen 遮蔽项、$(1 - F_{	ext{coat}})^2$ 能量衰减
     - 汽车车漆、钢琴烤漆、碳纤维
   * - **织物光晕 (Sheen / Cloth)**
     - 掠射边缘微纤维圆柱散射
     - Charlie 倒钟形 NDF、Ashikhmin 遮蔽项
     - 天鹅绒、丝绸、粗花呢西装

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章突破了标准 BRDF 均质不透明表面的理论局限，系统解构了次表面散射 BSSRDF 的 8 维传输方程与实时屏幕空间 6 阶高斯可分离模糊滤波、预积分皮肤 LUT、各向异性 GGX 椭圆高光微表面解算、双层清漆涂层的严格物理能量守恒层叠模型，以及针对纺织面料微纤维的 Estevez-Kulla Sheen 材质模型。

在掌握了全套微表面光学与复杂物理材质理论后，下一章我们将深入工业级资产管线与管线底层集成——**材质创作与着色管线集成：法线贴图切线空间计算、高度置换与材质分层混合**，系统解构 MikkTSpace 切线空间正交化、视差遮蔽映射（POM）与材质多层混合的底层实现。
