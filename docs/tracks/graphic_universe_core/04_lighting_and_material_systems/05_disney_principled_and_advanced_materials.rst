========================================================================
Chapter 20: 进阶材质表达与着色：Disney Principled BRDF、次表面散射与各向异性
========================================================================

.. note:: 前置背景与认知承接
   前两章系统推导了基于物理的渲染（PBR）经典 Cook-Torrance 镜面反射微表面理论大厦，解构了 GGX 法线分布函数、Schlick 菲涅尔反射公式、Smith 高度相关几何遮蔽函数（$V$ 项）以及 Kulla-Conty 多重散射能量补偿模型。然而，标准 Cook-Torrance 模型主要针对各向同性的理想硬质电介质与单层导体金属。在工业级电影特效与高拟真游戏渲染中，现实世界的材质呈现出更为丰富的物理微观结构：人脸皮肤与玉石的半透明透光、拉丝金属与头发丝绸的方向性高光、汽车烤漆的双层镜面反射，以及天鹅绒织物的微纤维边缘泛光。本章将系统剖析以美术为中心的 Disney Principled BRDF 架构哲学、次表面散射（BSSRDF）从偶极子物理到屏幕空间 SSSS 的实时演进、各向异性（Anisotropic）微表面切线流场建模，以及清漆层（Clearcoat）与织物光泽（Sheen）等多层复合材质的高级着色体系。

------------------------------------------------------------------------
20.1 Disney Principled BRDF 核心设计哲学与参数拓扑
------------------------------------------------------------------------

在 PBR 技术推广初期，许多渲染系统直接暴露复杂的物理参数（如复折射率 $	ilde{n} = n + ik$、微表面斜率方差 $\sigma^2$ 等）。这导致美术艺术家极难直观调节材质，经常设置出打破物理能量守恒的极端数值。2012 年，迪士尼动画工作室的 Brent Burley 发表了具有里程碑意义的论文《Physically-Based Shading at Disney》，确立了 **Disney 原则化双向反射分布函数（Disney Principled BRDF）**。

Disney Principled 设计五大核心工程原则
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  Disney Principled BRDF 五大核心设计准则                |
   +-------------------------------------------------------------------------+

   1. 直观易懂 (Intuitive): 参数必须具备明确的直观视觉含义，杜绝晦涩的物理学术常数
   2. 参数精简 (Fewer Parameters): 尽可能压缩参数维度，去除相互耦合的冗余控制项
   3. 归一化区间 (Normalized): 绝大部分核心控制参数严格归一化映射在 [0.0, 1.0] 闭区间内
   4. 物理鲁棒 (Robust & Plausible): 任何参数组合输入均自动满足物理自洽性与能量守恒，杜绝画面穿帮
   5. 表达广泛 (Broad Expressiveness): 单一通用着色器模型必须能够无缝覆盖从金属、塑料、木材到布料、皮肤的全部材质

Disney 原则化材质核心参数矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: Disney Principled BRDF 核心参数微架构与物理映射
   :widths: 18 15 27 40
   :header-rows: 1
   :class: tight-table

   * - 参数名称
     - 取值范围
     - 物理微观机制
     - 渲染管线内部计算映射
   * - **BaseColor**
     - RGB [0,1]
     - 材质的基础反射颜色
     - 电介质映射为漫反射反照率（Albedo）；金属映射为垂直菲涅尔反射率 $F_0$
   * - **Metallic**
     - 标量 [0,1]
     - 物质内部自由电子传导特性
     - 0 为纯电介质（$F_0=0.04$）；1 为纯金属（漫反射清零，高光染上 BaseColor）
   * - **Roughness**
     - 标量 [0,1]
     - 微表面法线微观偏离离散度
     - 内部执行平方映射 $\alpha = 	ext{Roughness}^2$，驱动 GGX 分布波瓣宽度
   * - **Specular**
     - 标量 [0,1]
     - 电介质垂直反射率的艺术微调
     - 线性映射电介质 $F_0 = 0.08 	imes 	ext{Specular}$（默认 0.5 对应 $F_0=0.04$）
   * - **SpecularTint**
     - 标量 [0,1]
     - 电介质高光受 BaseColor 染色的倾向
     - 插值白色与归一化 BaseColor 之间的电介质菲涅尔高光颜色
   * - **Anisotropic**
     - 标量 [0,1]
     - 切线与副切线方向粗糙度差异
     - 将单一 $\alpha$ 拆解为沿切线 $\mathbf{t}$ 的 $\alpha_x$ 与沿副切线 $\mathbf{b}$ 的 $\alpha_y$
   * - **Sheen**
     - 标量 [0,1]
     - 织物微纤维在掠射角产生的附加能量
     - 驱动专门针对布料边缘散射的软高光波瓣（Charlie Lobe）
   * - **Clearcoat**
     - 标量 [0,1]
     - 覆盖在底材表面的第二层透明保护漆
     - 激活独立的第二层微表面镜面反射项（固定折射率 $n=1.5, F_0=0.04$）
   * - **ClearcoatGloss**
     - 标量 [0,1]
     - 清漆保护层的表面平整光滑度
     - 映射清漆层专属粗糙度 $\alpha_c = (1 - 	ext{Gloss})^2$，驱动 GTR1 法线分布

------------------------------------------------------------------------
20.2 漫反射与粗糙度耦合：Disney Diffuse 与逆向反射
------------------------------------------------------------------------

经典图形学通常采用朗伯漫反射模型（Lambertian Diffuse，$f_{	ext{diffuse}} = \frac{\rho}{\pi}$），假设微表面内部多次散射出射的能量在半球范围内完全各向同性均匀分布。

朗伯漫反射的物理局限性与粗糙表面的逆向反射 (Retro-Reflection)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

物理测量数据表明：当微表面极其粗糙时（如粗糙石块、泥土、石膏），**掠射角方向会出现强烈的逆向反射（Retro-Reflection）现象**——光线从入射方向沿原路返回的能量显著高于侧向散射能量，且掠射边缘不再随余弦衰减变暗，反而呈现出平坦甚至泛亮的视觉特征。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |               传统 Lambert 漫反射 vs Disney 粗糙漫反射波瓣对比          |
   +-------------------------------------------------------------------------+

   [ 传统 Lambert 漫反射 ]
        出射均匀半球
            ^
          / | \        * 假设: 表面完全各向同性均匀出射
         /  |  \       * 缺陷: 粗糙物体在掠射视角下边缘严重变暗 (Dark Rim)，
        +---+---+              无法还原月球表面或粗糙岩石的真实散射！

   [ Disney 漫反射 (含逆向反射波瓣) ]
       逆向反射增强 (Retro-reflection Peak)
          \   /
           \ /   出射
            +---->     * 机制: 掠射视角与粗糙度深度耦合，微表面阴影内部发生多次反弹，
        +-------+              使得掠射边缘能量被重新推回视线，呈现真实平坦明亮感！

Disney Diffuse 数学模型严格推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Brent Burley 提出了将菲涅尔因子与微表面粗糙度深度绑定的漫反射经验解析公式：

.. math::

   f_{	ext{diffuse}}(\mathbf{l}, \mathbf{v}) = \frac{	ext{BaseColor}}{\pi} \cdot F_{	ext{diffuse}}(\mathbf{n} \cdot \mathbf{l}) \cdot F_{	ext{diffuse}}(\mathbf{n} \cdot \mathbf{v})

其中单向漫反射菲涅尔因子 $F_{	ext{diffuse}}(\cos	heta)$ 定义为基于 Schlick 近似的插值形式：

.. math::

   F_{	ext{diffuse}}(\cos	heta) = 1 + (F_{D90} - 1)(1 - \cos	heta)^5

关键在于掠射角最大反射极值 $F_{D90}$ 不再固定为 1.0，而是由**粗糙度 $\alpha$ 与半角向量点积**动态决定：

.. math::

   F_{D90} = 0.5 + 2 \cdot \alpha \cdot (\mathbf{l} \cdot \mathbf{h})^2

- **光滑表面极限（$\alpha 	o 0$）**：$F_{D90} 	o 0.5$。在掠射角处，漫反射菲涅尔因子衰减至 $0.5$ 甚至更低，因为入射光能量被强大的镜面反射（$F 	o 1.0$）优先抢占，漫反射自动变暗，完美满足能量守恒；
- **粗糙表面极限（$\alpha 	o 1$）**：$F_{D90} 	o 2.5$。在掠射角处，漫反射能量在边缘呈现出高达 $2.5$ 倍的逆向散射峰值，准确复现了月球及粗糙微表面的扁平漫散射质感。

------------------------------------------------------------------------
20.3 次表面散射 (BSSRDF) 微观物理与实时近似模型
------------------------------------------------------------------------

在电介质材质中，并非所有折射进入内部的光线都在进入点的极小微观邻域内出射。对于半透明介质（如人类皮肤、玉石、牛奶、蜡烛、树叶、水果果肉），光线穿透表面后，会在介质内部穿行相当长的物理距离（从毫米级到厘米级），经历成千上万次微观粒子散射，最终从**完全不同的另一处表面位置透射出射**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |           BRDF 局部单点局部散射 vs BSSRDF 跨表面非局部次表面散射        |
   +-------------------------------------------------------------------------+

   [ BRDF 模型 (单点局部假设) ]
   光线在点 x 入射 ---> \       / ---> 光线在同一点 x 立即出射 (忽略光线在介质内扩散)
                         \     /
       -------------------+-x-+------------------- (表面)

   [ BSSRDF 模型 (跨表面非局部散射) ]
   光线在点 xi 入射 ---> \
                          \          光线在内部经历多次粒子碰撞散射 (Mean Free Path)
        -------------------+-xi-------------------------xo-+------------------- (表面)
                            \       / \                 /
                             \_____/   \_______/\______/ ---> 光线从远距离点 xo 透射出射!
                                                              形成柔和阴影与通透血色辉光!

BSSRDF 积分方程定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

双向散射表面反射分布函数（Bidirectional Scattering Surface Reflectance Distribution Function - BSSRDF，记为 $S(\mathbf{x}_i, \omega_i; \mathbf{x}_o, \omega_o)$）将出射辐射度 $L_o(\mathbf{x}_o, \omega_o)$ 表达为对全表面积 $A$ 及全半球入射立体角 $\Omega_i$ 的八维广义积分：

.. math::

   L_o(\mathbf{x}_o, \omega_o) = \int_{A} \int_{\Omega_i} S(\mathbf{x}_i, \omega_i; \mathbf{x}_o, \omega_o) \cdot L_i(\mathbf{x}_i, \omega_i) (\mathbf{n}_i \cdot \omega_i) \, d\omega_i \, dA(\mathbf{x}_i)

Jensen 偶极子扩散剖面 (Dipole Diffusion Profile)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

2001 年，Henrik Wann Jensen 提出了经典的偶极子扩散模型（Dipole Diffusion Model）。Jensen 假设介质内部光子扩散满足扩散方程，通过在表面上方和下方镜像放置一对正负虚拟点光源，推导出了光线从 $\mathbf{x}_i$ 扩散至 $\mathbf{x}_o$ 的径向漫反射剖面函数 $R_d(r)$（其中 $r = \|\mathbf{x}_i - \mathbf{x}_o\|$）：

.. math::

   R_d(r) = \frac{\alpha'}{4\pi} \left[ z_r \left( \sigma_{	ext{tr}} + \frac{1}{d_r} \right) \frac{e^{-\sigma_{	ext{tr}} d_r}}{d_r^2} + z_v \left( \sigma_{	ext{tr}} + \frac{1}{d_v} \right) \frac{e^{-\sigma_{	ext{tr}} d_v}}{d_v^2} \right]

其中 $\sigma_{	ext{tr}} = \sqrt{3 \sigma_a \sigma_s'}$ 为有效输运衰减系数，描述了光线在不同波长下的衰减速度（由于红光在人体血液中的吸收系数 $\sigma_a$ 远小于蓝绿光，红光扩散距离最远，因而在背光与明暗交界线上呈现出标志性的血红色渐变辉光）。

工业级实时次表面散射三大核心方案
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于全局 BSSRDF 表面积积分在实时渲染中计算开销过高，现代游戏与实时引擎建立了三套主流的工程近似实现：

.. list-table:: 实时次表面散射 (Real-Time SSS) 工业级方案对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 方案名称
     - 核心数学机理
     - 性能与带宽开销
     - 视觉优势与适用场景
   * - **预积分皮肤着色 (Pre-Integrated Skin)**
     - 将散射剖面 $R_d(r)$ 与表面局部几何曲率（Curvature）在离线阶段预积分为 2D LUT（输入为 $\mathbf{n}\cdot\mathbf{l}$ 与 Curvature）
     - **极快（单次 2D 贴图采样，0 额外带宽）**
     - 完美处理面部鼻翼、面颊等平滑几何的红色渐变阴影；但无法处理耳朵等透光投射
   * - **屏幕空间次表面散射 (SSSS)**
     - 将扩散剖面拟合为 4~6 个高斯函数线性组合，在后处理阶段沿屏幕空间对漫反射缓冲区执行可分离横纵模糊卷积
     - 中等（需 1~2 个后处理模糊通道与深度掩码）
     - **工业界 AAA 人脸渲染事实标准**；阴影交界线柔化极自然，真实感极高
   * - **厚度透光深度图 (Shadow Map Transmission)**
     - 从光源视角读取 Shadow Map 深度值，计算视线光线穿透物体的物理厚度 $d$，按指数衰减 $\exp(-\sigma d)$ 叠加透光
     - 极低（复用 Shadow Map 采样）
     - **专门用于耳朵、手指、树叶与薄壁玉石的背光强透射（Translucency）**

------------------------------------------------------------------------
20.4 各向异性材质 (Anisotropic BRDF) 与切线流场建模
------------------------------------------------------------------------

标准 Cook-Torrance 模型假设微表面在所有水平切线方向上具有相同的粗糙度（各向同性 Isotropic）。然而在拉丝金属（Brushed Metal）、黑胶唱片、丝绸织物（Silk）以及头发发丝（Hair）表面，微观几何结构存在明显的**定向凹凸沟壑（Directional Grooves）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |               各向同性圆形高光 vs 各向异性拉伸光斑微观拓扑              |
   +-------------------------------------------------------------------------+

   [ 各向同性微表面 (Isotropic) ]           [ 各向异性定向沟壑微表面 (Anisotropic) ]
       微表面法线随机散布                        微表面具有严格平行排列的微观划痕
             ^                                           ^
           / | \                                       / | \   (沿划痕法线发散极广，
          +--+--+                                     +--+--+   沿垂直轴发散极窄)
             |                                           |
             v                                           v
   屏幕高光呈现: 正圆形高光点                 屏幕高光呈现: **垂直于划痕方向的狭长拉伸亮带**

各向异性 GGX (Anisotropic Trowbridge-Reitz) 数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了数学化描述各向异性高光，法线分布函数必须引入局部的**正交几何切线坐标系 $(\mathbf{t}, \mathbf{b}, \mathbf{n})$**，并定义切线方向粗糙度 $\alpha_x$ 与副切线方向粗糙度 $\alpha_y$：

.. math::

   D_{	ext{aniso}}(\mathbf{h}, \alpha_x, \alpha_y) = \frac{1}{\pi \alpha_x \alpha_y \left( \frac{(\mathbf{h} \cdot \mathbf{t})^2}{\alpha_x^2} + \frac{(\mathbf{h} \cdot \mathbf{b})^2}{\alpha_y^2} + (\mathbf{h} \cdot \mathbf{n})^2 \right)^2}

各向异性椭圆粗糙度映射
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Disney Principled 将用户输入的标量粗糙度 $	ext{Roughness} \in [0, 1]$ 与各向异性程度 $	ext{Anisotropic} \in [-1, 1]$ 映射为正交轴粗糙度：

.. math::

   	ext{aspect} = \sqrt{1 - 0.9 	imes 	ext{Anisotropic}}, \quad
   \alpha_x = \frac{	ext{Roughness}^2}{	ext{aspect}}, \quad
   \alpha_y = 	ext{Roughness}^2 	imes 	ext{aspect}

切线流场贴图 (Flow Map) 与副切线正交重构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在 3D 复杂曲面上控制拉丝金属与头发发流的旋转走向，渲染管线通常采样一张 **切线流场贴图（Flow Map / Direction Map）**。贴图中的 2D 向量 $(u, v) \in [-1, 1]^2$ 表示当前像素切线相对于网格原生切线的旋转偏角 $\phi$：

.. math::

   \mathbf{t}_{	ext{flow}} = \mathbf{t} \cos\phi + \mathbf{b} \sin\phi, \quad
   \mathbf{b}_{	ext{flow}} = 	ext{normalize}(\mathbf{n} 	imes \mathbf{t}_{	ext{flow}})

通过将经过流场扰动后的 $\mathbf{t}_{	ext{flow}}$ 与 $\mathbf{b}_{	ext{flow}}$ 代入 $D_{	ext{aniso}}$，渲染器能够精确重现锅底同心圆拉丝高光以及发型螺旋流动的光泽质感。

------------------------------------------------------------------------
20.5 多层物理材质复合：清漆层 (Clearcoat) 与织物光泽 (Sheen)
------------------------------------------------------------------------

现实世界中的高级物体很少由单一材质层构成。例如豪华汽车车漆由底层的金属漆颗粒（Base Layer）与外层覆盖的透明高反射聚氨酯树脂清漆层（Clearcoat Layer）复合而成。

清漆层 (Clearcoat) 双层 BRDF 叠加架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     双层汽车烤漆 (Clearcoat) 光学反射拓扑               |
   +-------------------------------------------------------------------------+

   入射光 l
        \
         +---- 1. 顶层清漆层镜面反射 (Clearcoat Specular): 产生极锐利的白色次高光
          \       (固定 F0=0.04, GTR1 / Berry 分布, 绝缘体纯白光斑)
           \
            v (折射穿透清漆层进入底层)
             \
              +---- 2. 底层金属漆颗粒 (Base Metal Layer): 产生粗糙的有色强高光
                       (受 BaseColor 与金属度控制，呈现红/蓝/金深层闪烁)

- **GTR1 (Generalized Trowbridge-Reitz 1) 法线分布**：清漆层表面虽然极其光滑，但总有偶发微观瑕疵。Disney 采用指数 $\gamma=1$ 的 GTR1 分布（又称 Berry 分布），其中心极尖锐且带有较长尾部，非常贴合清漆反光特性：

.. math::

   D_{	ext{GTR1}}(\mathbf{n} \cdot \mathbf{h}, \alpha_c) = \frac{\alpha_c^2 - 1}{2\pi \ln(\alpha_c)} \cdot \frac{1}{1 + (\alpha_c^2 - 1)(\mathbf{n} \cdot \mathbf{h})^2}

- **清漆层菲涅尔衰减与能量守恒**：顶层清漆层反射的能量比例 $F_c = F_{	ext{Schlick}}(\mathbf{v} \cdot \mathbf{h}, 0.04)$ 会直接扣减进入底层的光能。底层所有光照计算结果必须乘以 $(1 - 	ext{Clearcoat} 	imes F_c)$，严格杜绝能量越界增益。

织物微纤维层 (Sheen) 与 Charlie Lobe
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于丝绒、棉布、毛衣等织物，微观表面垂直立起无数细小纤维微毛。光线照射时，纤维侧壁在**掠射角方向（Grazing Angles）**产生极强的前向与背向散射，使布料轮廓边缘产生柔和发亮的“绒毛辉光（Velvet Sheen）”。

Disney 引入了 Charlie 漫高光分布函数：

.. math::

   D_{	ext{Charlie}}(\mathbf{n} \cdot \mathbf{h}, \alpha_{	ext{sheen}}) = \frac{(2 + 1/\alpha_{	ext{sheen}})}{2\pi} (1 - (\mathbf{n} \cdot \mathbf{h})^2)^{\frac{1}{2\alpha_{	ext{sheen}}}}

该函数在法线垂直方向（$\mathbf{n}\cdot\mathbf{h} 	o 1$）取值极低，但在掠射切向（$\mathbf{n}\cdot\mathbf{h} 	o 0$）迅速攀升，完美还原了天鹅绒织物独特的漫感边缘亮边。

------------------------------------------------------------------------
20.6 现代 GPU 工业级 HLSL 综合着色器源码实现
------------------------------------------------------------------------

以下给出工业级通用 PBR 着色器中支持 Disney Principled 全特性的核心 HLSL 实现：

.. code-block:: hlsl

   // HLSL: 工业级 Disney Principled BRDF 综合着色解算实现
   // 涵盖: Disney Diffuse, Anisotropic Specular, Clearcoat (GTR1), Sheen (Charlie)

   #define PI 3.14159265359f

   // 1. GTR1 (Berry) 清漆层法线分布函数
   float DistributionGTR1(float NdotH, float a) {
       if (a >= 1.0f) return 1.0f / PI;
       float a2 = a * a;
       float t = 1.0f + (a2 - 1.0f) * NdotH * NdotH;
       return (a2 - 1.0f) / (PI * log(a2) * t);
   }

   // 2. 各向异性 GGX 法线分布函数
   float DistributionAnisotropicGGX(float3 H, float3 T, float3 B, float3 N, float ax, float ay) {
       float HdotT = dot(H, T);
       float HdotB = dot(H, B);
       float NdotH = dot(N, H);
       
       float term = (HdotT * HdotT) / (ax * ax) + (HdotB * HdotB) / (ay * ay) + NdotH * NdotH;
       return 1.0f / (PI * ax * ay * term * term);
   }

   // 3. Charlie 织物微纤维法线分布函数 (Sheen)
   float DistributionCharlie(float NdotH, float roughness) {
       float invR = 1.0f / max(roughness, 1e-4f);
       float cos2h = NdotH * NdotH;
       float sin2h = max(1.0f - cos2h, 0.0078125f); // 2^(-7) 保护
       return (2.0f + invR) * pow(sin2h, invR * 0.5f) / (2.0f * PI);
   }

   // 4. Disney Principled 全特性光照求值入口
   float3 EvaluateDisneyPrincipled(
       float3 N, float3 V, float3 L, float3 T, float3 B,
       float3 baseColor, float metallic, float roughness, float specularTint,
       float anisotropic, float clearcoat, float clearcoatGloss, float sheen
   ) {
       float3 H = normalize(V + L);
       float NdotL = saturate(dot(N, L));
       float NdotV = saturate(dot(N, V));
       float NdotH = saturate(dot(N, H));
       float VdotH = saturate(dot(V, H));
       float LdotH = saturate(dot(L, H));

       if (NdotL <= 0.0f || NdotV <= 0.0f) return float3(0, 0, 0);

       // -------------------------------------------------------------
       // 1. 基础反射率 F0 计算 (电介质调色与金属染色)
       // -------------------------------------------------------------
       float3 specColor = lerp(float3(1, 1, 1), baseColor / max(dot(baseColor, float3(0.3, 0.6, 0.1)), 1e-4f), specularTint);
       float3 F0 = lerp(0.08f * 0.5f * specColor, baseColor, metallic);

       // -------------------------------------------------------------
       // 2. Disney Diffuse 漫反射项 (含逆向反射)
       // -------------------------------------------------------------
       float FD90 = 0.5f + 2.0f * roughness * LdotH * LdotH;
       float F_L = 1.0f + (FD90 - 1.0f) * pow(saturate(1.0f - NdotL), 5.0f);
       float F_V = 1.0f + (FD90 - 1.0f) * pow(saturate(1.0f - NdotV), 5.0f);
       float3 diffuseTerm = (baseColor / PI) * F_L * F_V * (1.0f - metallic);

       // -------------------------------------------------------------
       // 3. 各向异性主镜面反射项 (Specular GGX)
       // -------------------------------------------------------------
       float aspect = sqrt(1.0f - 0.9f * anisotropic);
       float ax = max(0.001f, (roughness * roughness) / aspect);
       float ay = max(0.001f, (roughness * roughness) * aspect);
       float D_spec = DistributionAnisotropicGGX(H, T, B, N, ax, ay);
       float3 F_spec = F0 + (1.0f - F0) * pow(saturate(1.0f - VdotH), 5.0f);
       float V_spec = VisibilitySmithGGXCorrelated(NdotL, NdotV, roughness);
       float3 specularTerm = D_spec * F_spec * V_spec;

       // -------------------------------------------------------------
       // 4. 清漆层 (Clearcoat Layer - GTR1)
       // -------------------------------------------------------------
       float3 clearcoatTerm = float3(0, 0, 0);
       float F_clearcoat = 0.0f;
       if (clearcoat > 0.0f) {
           float a_c = lerp(0.1f, 0.001f, clearcoatGloss);
           float D_c = DistributionGTR1(NdotH, a_c);
           F_clearcoat = 0.04f + (1.0f - 0.04f) * pow(saturate(1.0f - VdotH), 5.0f);
           // 清漆层采用近似几何遮蔽 V_c = 1 / (4 * (N·L) * (N·V)) -> 取 0.25
           clearcoatTerm = clearcoat * (0.25f * D_c * F_clearcoat);
       }

       // -------------------------------------------------------------
       // 5. 织物微纤维层 (Sheen Layer)
       // -------------------------------------------------------------
       float3 sheenTerm = float3(0, 0, 0);
       if (sheen > 0.0f) {
           float D_sheen = DistributionCharlie(NdotH, roughness);
           sheenTerm = sheen * baseColor * D_sheen * 0.25f;
       }

       // -------------------------------------------------------------
       // 6. 能量平衡综合输出
       // -------------------------------------------------------------
       // 清漆层扣减透射能量
       float3 directLight = ((diffuseTerm + specularTerm + sheenTerm) * (1.0f - clearcoat * F_clearcoat) + clearcoatTerm) * NdotL;

       return directLight;
   }

------------------------------------------------------------------------
小结与下卷导读
------------------------------------------------------------------------

本章系统解构了现代图形学工业级材质表示的标准范式——Disney Principled BRDF 架构哲学，剖析了粗糙漫反射与逆向反射物理机理，深入推导了次表面散射（BSSRDF）从偶极子扩散到屏幕空间 SSSS 的演进路径，建立了各向异性微表面切线流场的双轴椭圆法线分布数学模型，并给出了汽车烤漆清漆层（Clearcoat）与天鹅绒织物微毛层（Sheen）的多层复合渲染闭环。

至此，《图形渲染全栈与GPU架构内核全景深度剖析》**第四模块：光照理论与物理材质系统（04_lighting_and_material_systems）圆满全量收官（5/5 节）！全书已累计完工 20 / 45 节（完成度达 44.4%）！**

在完成了微表面光照与材质的深度探索后，全书将正式跨入复杂空间几何与阴影遮蔽算法的广阔领域——**第 5 模块：阴影算法与空间加速结构 (05_shadows_and_spatial_acceleration)**。下一章我们将开启第五模块第一章——**阴影映射核心原理与瑕疵消除：Shadow Map、自阴影粉刺 (Acne)、Peter Panning 悬浮与斜率比例偏差 (Slope-Scaled Bias)**，从光源空间投影变换出发，系统解构现代实时硬阴影与自阴影走样排查的底层技术体系。
