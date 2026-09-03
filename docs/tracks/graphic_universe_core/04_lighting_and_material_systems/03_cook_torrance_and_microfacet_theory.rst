========================================================================
Chapter 18: 基于物理的渲染 (PBR) 微表面理论：Cook-Torrance 框架与法线分布函数
========================================================================

.. note:: 前置背景与认知承接
   前一章系统解构了经典经验光照模型（Lambert、Half-Lambert、Phong 与 Blinn-Phong）的代数演进，剖析了半程向量作为微表面法线分布逼近的几何本质，并论证了经验模型在能量守恒、菲涅尔效应与材质物理分类上的局限。为了消除光照计算中随意填写的经验常数，使材质在任意动态光照环境下均能保持严格的物理自洽性与能量守恒，现代 3D 渲染全面转向了**基于物理的渲染（Physically Based Rendering - PBR）**。PBR 的核心理论基石是**微表面理论（Microfacet Theory）**与 **Cook-Torrance 镜面反射着色模型**。本章将从微观统计光学出发，深入推导微表面假设、Cook-Torrance 框架中分母项 $4(\mathbf{n}\cdot\mathbf{l})(\mathbf{n}\cdot\mathbf{v})$ 的严格微积分几何来源、微面法线分布函数（NDF）的投影面积归一化条件、经典 Beckmann 分布与统治现代工业界的 GGX / Trowbridge-Reitz 长尾分布模型、粗糙度感知线性化映射，以及各向异性（Anisotropic）扩展与 GPU 着色器实现。

------------------------------------------------------------------------
18.1 微表面理论 (Microfacet Theory) 的物理世界观
------------------------------------------------------------------------

在宏观尺度上，许多物体表面（如金属外壳、未经抛光的木材、磨砂玻璃）呈现出连续而平滑的几何轮廓。然而在光学微观尺度（波长级别 $\sim 0.5\mu	ext{m}$）下，任何物理表面都充满了凹凸不平的微观沟壑与微小起伏。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       微表面理论宏观与微观映射拓扑                      |
   +-------------------------------------------------------------------------+

   [ 宏观观测尺度 (Macro Scale) ]
   宏观表面法线 n (由顶点几何或法线贴图给定)
        |
        v
   ------------------------------------------------------------------------- (平滑表面)

   [ 微观光学尺度 (Micro Scale) ]
   微表面微元: 由无数各向同性的微小镜面平面 (Microfacets) 构成
   每个微平面拥有自己独立的微观法线 m:
          m1       m2           m3       m4          m5
          ^        ^            ^        ^           ^
         /          \          /          \         /
        /\    /\    /\        /\          /\       /\
       /  \  /  \  /  \  /\  /  \  /\    /  \     /  \
      /    \/    \/    \/  \/    \/  \  /    \   /    \
     /                                \/      \_/      \

微表面理论的三大核心光学假设
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **局部光学理想镜面反射假设**：每一个微小的微表面（Microfacet）在物理上都是一个绝对光滑的理想平面，其反射行为严格遵循菲涅尔反射定律与斯涅尔折射定律；
2. **镜面朝向有效性筛选准则**：在宏观入射光方向 $\mathbf{l}$ 与宏观出射观察方向 $\mathbf{v}$ 确定的情况下，**只有那些微观法线 $\mathbf{m}$ 恰好等于半程向量 $\mathbf{h} = \frac{\mathbf{l} + \mathbf{v}}{\|\mathbf{l} + \mathbf{v}\|}$ 的微表面，才能够将光线从 $\mathbf{l}$ 精确反射至观察方向 $\mathbf{v}$**；
3. **统计平均宏观涌现**：宏观上观察到的材质光泽度、高光漫溢与粗糙感，本质上是数以亿计的微观微表面法线随机分布在宏观积分下的统计物理结果。

------------------------------------------------------------------------
18.2 Cook-Torrance 镜面反射 BRDF 框架严格推导
------------------------------------------------------------------------

1981 年，Robert L. Cook 与 Kenneth E. Torrance 提出了划时代的基于微表面理论的镜面反射 BRDF 表达式：

.. math::

   f_{	ext{spec}}(\mathbf{l}, \mathbf{v}) = \frac{D(\mathbf{h}) F(\mathbf{v}, \mathbf{h}) G(\mathbf{l}, \mathbf{v}, \mathbf{h})}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})}

该公式由三大物理函数与一个分母几何校正项构成：

- **$D(\mathbf{h})$（法线分布函数，Normal Distribution Function - NDF）**：统计朝向为 $\mathbf{h}$ 的微表面面积占比；
- **$F(\mathbf{v}, \mathbf{h})$（菲涅尔项，Fresnel Equation）**：计算入射光被微表面镜面反射的能量比例（其余折射进入介质）；
- **$G(\mathbf{l}, \mathbf{v}, \mathbf{h})$（几何遮蔽与阴影项，Geometric Shadowing/Masking Term）**：计算微表面之间相互遮挡（Masking）与自身阴影（Shadowing）后可见微表面的有效比例；
- **$4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})$**：将微观微表面局部坐标系积分转换到宏观表面投影面积与立体角的几何转换因子。

分母项 $4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})$ 的微积分几何推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

许多图形学初学者将分母中的 4 视为经验系数。事实上，该分母项是严格推导宏观反射辐射率与微观辐射通量之间雅可比行列式（Jacobian）转换的必然结果：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             微观微表面立体角 dω_h 到宏观反射立体角 dω_o 的几何映射      |
   +-------------------------------------------------------------------------+

                 入射光 l                  半程向量 h                 出射光 v
                      \                         |                         /
                       \                        | θ_d                    /
                        \                       |                       /
                         \                      |                      /
                          \                     |                     /
                           \            θ_d     |     θ_d            /
                            \                   |                   /
        ---------------------\------------------+------------------/-----------------
                                                 表面微元 dA

1. 设宏观表面微元面积为 $dA$，朝向 $\mathbf{h}$ 的微表面微分面积为 $dA_h = D(\mathbf{h}) dA d\omega_h$；
2. 入射光照在微表面 $dA_h$ 上的微分辐射通量为：
   $$d\Phi_i = L_i (\mathbf{l}) (\mathbf{l} \cdot \mathbf{h}) dA_h = L_i (\mathbf{l}) (\mathbf{l} \cdot \mathbf{h}) D(\mathbf{h}) dA d\omega_h$$
3. 经过微表面镜面反射后，出射辐射通量为 $d\Phi_r = F(\mathbf{v}, \mathbf{h}) G(\mathbf{l}, \mathbf{v}, \mathbf{h}) d\Phi_i$；
4. 宏观出射辐射率 $L_o(\mathbf{v})$ 定义为出射通量除以宏观投影面积与出射立体角微分：
   $$L_o(\mathbf{v}) = \frac{d\Phi_r}{dA (\mathbf{n} \cdot \mathbf{v}) d\omega_o} = \frac{F(\mathbf{v}, \mathbf{h}) G(\mathbf{l}, \mathbf{v}, \mathbf{h}) L_i (\mathbf{l}) (\mathbf{l} \cdot \mathbf{h}) D(\mathbf{h}) dA d\omega_h}{dA (\mathbf{n} \cdot \mathbf{v}) d\omega_o}$$
5. **立体角微分变换关系**：根据半程向量的球面几何关系，出射立体角微分 $d\omega_o$ 与半程向量立体角微分 $d\omega_h$ 之间满足变换：
   $$d\omega_o = 4 (\mathbf{l} \cdot \mathbf{h}) d\omega_h \quad \Longrightarrow \quad \frac{d\omega_h}{d\omega_o} = \frac{1}{4 (\mathbf{l} \cdot \mathbf{h})}$$
6. 代入化简：
   $$L_o(\mathbf{v}) = \frac{D(\mathbf{h}) F(\mathbf{v}, \mathbf{h}) G(\mathbf{l}, \mathbf{v}, \mathbf{h}) (\mathbf{l} \cdot \mathbf{h})}{(\mathbf{n} \cdot \mathbf{v}) \cdot 4 (\mathbf{l} \cdot \mathbf{h})} L_i(\mathbf{l}) = \frac{D(\mathbf{h}) F(\mathbf{v}, \mathbf{h}) G(\mathbf{l}, \mathbf{v}, \mathbf{h})}{4 (\mathbf{n} \cdot \mathbf{v})} L_i(\mathbf{l})$$
7. 根据 BRDF 的定义 $f_{	ext{spec}} = \frac{L_o(\mathbf{v})}{L_i(\mathbf{l}) (\mathbf{n} \cdot \mathbf{l}) d\omega_i}$，即刻严格导出分母为 $4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})$！

------------------------------------------------------------------------
18.3 微面法线分布函数 (NDF) 的统计学本质与物理约束
------------------------------------------------------------------------

法线分布函数 $D(\mathbf{m})$（NDF）描述了在微观尺度下，单位立体角内法线方向为 $\mathbf{m}$ 的微表面面积占比。

投影面积归一化物理约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于任意物理真实的表面，$D(\mathbf{m})$ 不能随意拟合，它必须满足一个核心的几何守恒约束：**所有微表面在宏观法线 $\mathbf{n}$ 上的正投影面积之和，必须严格等于宏观表面的单位面积（1.0）**。

.. math::

   \int_{\Omega} D(\mathbf{m}) (\mathbf{n} \cdot \mathbf{m}) d\omega_m = 1

此外，从任意视角 $\mathbf{v}$ 观察，所有朝向可见微表面在视线方向的投影面积之和，必须等于宏观微元在视线方向的投影面积：

.. math::

   \int_{\mathbf{v} \cdot \mathbf{m} > 0} D(\mathbf{m}) (\mathbf{v} \cdot \mathbf{m}) d\omega_m = \mathbf{n} \cdot \mathbf{v}

这两个积分约束不仅保证了材质在任何粗糙度下都不会凭空创造或销毁能量，而且构成了后续推导阴影遮蔽项 $G$ 的数学前提。

------------------------------------------------------------------------
18.4 主流法线分布函数 (NDF) 演进与 GGX / Trowbridge-Reitz 推导
------------------------------------------------------------------------

在图形学演进历程中，出现了数种代表性的 NDF 统计分布：

.. list-table:: 工业级主流微表面法线分布函数 (NDF) 特征全景对比
   :widths: 18 32 25 25
   :header-rows: 1
   :class: tight-table

   * - NDF 模型
     - 数学表达式 $D(\mathbf{h})$
     - 高光尾部特征 (Tail Profile)
     - 工业应用现状
   * - **Blinn-Phong**
     - $\frac{\alpha_p + 2}{2\pi} (\mathbf{n} \cdot \mathbf{h})^{\alpha_p}$
     - 高斯快速截断，无边缘光晕
     - 已被现代 PBR 彻底淘汰
   * - **Beckmann**
     - $\frac{1}{\pi \alpha^2 (\mathbf{n} \cdot \mathbf{h})^4} \exp\left(-\frac{1 - (\mathbf{n} \cdot \mathbf{h})^2}{\alpha^2 (\mathbf{n} \cdot \mathbf{h})^2}\right)$
     - 中等衰减尾部，符合高斯微观斜率分布
     - 偶尔用于粗糙金属、皮肤次表面高光
   * - **GGX (Trowbridge-Reitz)**
     - $\frac{\alpha^2}{\pi \left( (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right)^2}$
     - **极具物理真实感的重尾 (Heavy-Tailed) 扩散光晕**
     - **现代电影与游戏工业绝对事实标准**

GGX / Trowbridge-Reitz 分布的数学推导与长尾效应 (Heavy Tail)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1975 年，T. S. Trowbridge 与 K. P. Reitz 在研究粗糙表面光学散射时提出了基于椭球体微观微表面的概率密度模型。2007 年，Bruce Walter 等人将其引入计算机图形学，命名为 **GGX 分布**。

.. math::

   D_{	ext{GGX}}(\mathbf{n}, \mathbf{h}, \alpha) = \frac{\alpha^2}{\pi \left[ (\mathbf{n} \cdot \mathbf{h})^2 (\alpha^2 - 1) + 1 \right]^2}

其中 $\alpha$ 为材质的微观粗糙度参数（$\alpha \in [0, 1]$）：

- **当表面极度光滑（$\alpha 	o 0$）**：若 $\mathbf{h} = \mathbf{n}$（$(\mathbf{n} \cdot \mathbf{h}) = 1$），则 $D 	o \frac{1}{\pi \alpha^2} 	o \infty$；若 $\mathbf{h} 
eq \mathbf{n}$，则 $D 	o 0$。GGX 退化为狄拉克 $\delta$ 函数，表现为完美的镜面反射；
- **长尾效应（Heavy-Tailed Profile）**：与 Beckmann 的指数高斯衰减不同，GGX 采用有理分式代数衰减。当偏离高光中心（$(\mathbf{n}\cdot\mathbf{h}) < 1$）时，分母增长较为平缓，使得高光边缘能够延伸出一圈柔和而宽广的微弱光晕（Glow/Halo），这与绝大多数真实物理材质（抛光木材、车漆、金属外壳）的宏观光学表现完全吻合。

Disney 粗糙度感知线性化映射 (Perceptually Linear Roughness)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在数字内容创作（DCC 工具如 Substance Painter、Blender）中，若直接让美术人员调节物理参数 $\alpha \in [0, 1]$，会发现高光尺寸的变化极度不均匀（在 $[0, 0.1]$ 区间内微小滑动就会引起高光剧烈剧变，而 $[0.5, 1.0]$ 区间视觉变化极其迟钝）。

Disney 工程师 Brent Burley 提出将美术人员输入的感知粗糙度参数 $	ext{Roughness} \in [0, 1]$ 进行**平方映射**：

.. math::

   \alpha = 	ext{Roughness}^2

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Disney 感知粗糙度平方映射曲线几何对应                    |
   +-------------------------------------------------------------------------+

   美术感知参数 Roughness: [ 0.0 ------- 0.25 ------- 0.50 ------- 0.75 ------- 1.0 ]
                                 |            |            |            |
                                 v            v            v            v  (α = Roughness^2)
   物理微观粗糙度 α:        [ 0.00 ------ 0.0625 ----- 0.25 ------ 0.5625 ---- 1.0 ]

- **工程价值**：平方映射极大地扩展了光滑区间的参数精度，使得高光光斑大小随输入参数呈线性平滑缩放，成为了当代 PBR 材质标准（UE5、Unity HDRP、Filament）的统一规范。

------------------------------------------------------------------------
18.5 各向异性 NDF (Anisotropic GGX) 理论与拉丝材质
------------------------------------------------------------------------

当物体表面的微观沟壑具有明显的晶格方向性或机械打磨纹理（如拉丝金属盘、发丝、唱片纹路、碳纤维布料）时，微表面法线分布在切线方向 $\mathbf{t}$ 与副切线方向 $\mathbf{b}$ 上不再对称。

各向异性 Trowbridge-Reitz NDF 方程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设表面在切线方向的粗糙度为 $\alpha_x$，副切线方向的粗糙度为 $\alpha_y$：

.. math::

   D_{	ext{Aniso}}(\mathbf{h}, \mathbf{t}, \mathbf{b}, \mathbf{n}, \alpha_x, \alpha_y) = \frac{1}{\pi \alpha_x \alpha_y \left[ \left(\frac{\mathbf{t} \cdot \mathbf{h}}{\alpha_x}\right)^2 + \left(\frac{\mathbf{b} \cdot \mathbf{h}}{\alpha_y}\right)^2 + (\mathbf{n} \cdot \mathbf{h})^2 \right]^2}

- **退化性质**：当 $\alpha_x = \alpha_y = \alpha$ 时，由于正交基底满足 $(\mathbf{t}\cdot\mathbf{h})^2 + (\mathbf{b}\cdot\mathbf{h})^2 + (\mathbf{n}\cdot\mathbf{h})^2 = \|\mathbf{h}\|^2 = 1$，上式精确退化为标准各向同性 GGX 方程；
- **视觉特征**：高光光斑沿粗糙度较小的轴向延伸为狭长条带状，呈现出拉丝金属特有的十字形或放射状高光条纹。

------------------------------------------------------------------------
18.6 现代 GPU 工业级 HLSL 实现与数值防除零保护
------------------------------------------------------------------------

在 GPU 像素着色器中实现 GGX NDF 时，必须解决浮点下溢与除零崩溃（尤其在 $	ext{Roughness} 	o 0$ 且 $(\mathbf{n} \cdot \mathbf{h}) 	o 1$ 的镜面边界）：

.. code-block:: hlsl

   // HLSL: 工业级标准 GGX 法线分布函数实现 (含防除零保护)
   #define PI 3.141592653589793f

   // 1. 各向同性 GGX NDF
   float DistributionGGX(float NdotH, float roughness) {
       // Disney 感知粗糙度平方映射
       float a = roughness * roughness;
       float a2 = a * a;

       // 限制 a2 最小值，防止在极低粗糙度下分母除以零或产生 NaN
       a2 = max(a2, 1e-4f);

       float NdotH2 = NdotH * NdotH;
       
       // 分母项: ((N·H)^2 * (a^2 - 1) + 1)^2
       float denom = (NdotH2 * (a2 - 1.0f) + 1.0f);
       denom = PI * denom * denom;

       return a2 / denom;
   }

   // 2. 各向异性 GGX NDF
   float DistributionGGXAnisotropic(float NdotH, float TdotH, float BdotH, float ax, float ay) {
       ax = max(ax, 1e-4f);
       ay = max(ay, 1e-4f);

       float termX = (TdotH * TdotH) / (ax * ax);
       float termY = (BdotH * BdotH) / (ay * ay);
       float termZ = (NdotH * NdotH);

       float denom = termX + termY + termZ;
       denom = PI * ax * ay * denom * denom;

       return 1.0f / max(denom, 1e-7f);
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从微观统计光学世界观出发，系统确立了微表面理论的三大核心假设，推导了 Cook-Torrance 镜面反射框架中分母几何项的微积分雅可比来源，论证了法线分布函数（NDF）的投影面积归一化条件，深入对比了经典 Beckmann 与现代 GGX / Trowbridge-Reitz 分布的长尾光学特征，并给出了各向异性扩展与 GPU 数值安全实现。

在完整解析了法线分布项 $D$ 之后，Cook-Torrance 框架中还剩下决定光能反射比例的菲涅尔项 $F$ 以及解决微表面自遮蔽的几何项 $G$。下一章我们将开启第四模块第四章——**菲涅尔反射与几何遮蔽项：Schlick 经验近似、Smith 遮蔽函数与多重散射能量补偿**，系统推导麦克斯韦电磁波边界条件、电介质与金属导体的菲涅尔解算、Smith 阴影遮蔽高度相关模型，以及高粗糙度表面能量丢失的多重散射补偿算法。
