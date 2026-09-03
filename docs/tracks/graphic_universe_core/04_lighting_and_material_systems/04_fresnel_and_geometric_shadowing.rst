========================================================================
Chapter 19: 菲涅尔反射与几何遮蔽项：Schlick 近似、Smith 函数与能量补偿
========================================================================

.. note:: 前置背景与认知承接
   前一章系统建立了基于物理的渲染（PBR）微表面理论大厦，推导了 Cook-Torrance 镜面反射 BRDF 框架分母项 $4(\mathbf{n}\cdot\mathbf{l})(\mathbf{n}\cdot\mathbf{v})$ 的微分几何雅可比转换，并深入解构了 GGX / Trowbridge-Reitz 法线分布函数（NDF）的长尾光学特征。在 Cook-Torrance 框架 $f_{	ext{spec}} = \frac{D \cdot F \cdot G}{4(\mathbf{n}\cdot\mathbf{l})(\mathbf{n}\cdot\mathbf{v})}$ 中，法线分布项 $D$ 仅决定了有多少微表面朝向反射方向，而最终射入人眼的反射光强，还严格受控于两个决定性的物理因子：**菲涅尔项（$F$）**——光线打在微表面时反射与折射的能量配比；**几何遮蔽项（$G$）**——微观凹凸沟壑之间的自阴影与自遮挡比例。本章将从麦克斯韦电磁波边界条件出发，深入推导电介质与导体金属的菲涅尔反射定律、Schlick 经验近似的误差界、Smith 遮蔽函数及其高度相关（Height-Correlated）模型、可见性项（$V$ 项）的 GPU 指令合并优化，以及高粗糙度微表面单次散射能量丢失的多重散射（Multiple Scattering）物理补偿算法。

------------------------------------------------------------------------
19.1 菲涅尔反射定律物理本质与电磁波界面方程
------------------------------------------------------------------------

光作为一种高频电磁波，在穿过两种不同折射率的介质交界面（如空气与水、玻璃或金属）时，由于边界处电场与磁场切向分量必须保持连续，入射波能量将被分割为两部分：一部分被界面弹回原介质，形成**反射波（Reflected Wave）**；另一部分透射进入新介质，形成**折射波（Refracted Wave）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  光波在介质交界面处的反射与折射电磁拓扑                 |
   +-------------------------------------------------------------------------+

              入射光 l (介质 1: 折射率 η1)           反射光 r
                    \                                /
                     \                              /
                   θi \                            / θr = θi
                       \                          /
        ----------------\------------------------/---------------- (介质交界面)
                         \                      /
                          \                    /
                        θt \                  /  (介质 2: 复折射率 η2 = n + ik)
                            \                /
                             \折射光 t      / 吸收/透射/内部散射

麦克斯韦电磁边界严格菲涅尔方程 (Fresnel Equations)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于未偏振的自然光，反射能量比率 $F(	heta_i)$ 是 s-偏振光（垂直电场分量）与 p-偏振光（平行电场分量）反射率的算术平均：

.. math::

   F = \frac{1}{2} (R_s + R_p)

根据斯涅尔折射定律 $n_1 \sin	heta_i = n_2 \sin	heta_t$，两分量的反射率由介质折射率与入射角 $	heta_i$、折射角 $	heta_t$ 严格给出：

.. math::

   R_s = \left| \frac{n_1 \cos	heta_i - n_2 \cos	heta_t}{n_1 \cos	heta_i + n_2 \cos	heta_t} \right|^2, \quad
   R_p = \left| \frac{n_2 \cos	heta_i - n_1 \cos	heta_t}{n_2 \cos	heta_i + n_1 \cos	heta_t} \right|^2

电介质 (Dielectrics) vs 导体金属 (Conductors) 的光学响应差异
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在固体物理学中，物质的光学介电常数由复折射率 $	ilde{n} = n + ik$ 描述，其中 $n$ 为真实折射率（决定光速与相位传播），$k$ 为**消光系数（Extinction Coefficient）**，决定光波在介质内部传播时的指数级电磁衰减强度（吸收率）。

.. list-table:: 电介质与金属导体光学物理属性对比
   :widths: 18 22 28 32
   :header-rows: 1
   :class: tight-table

   * - 材质类别
     - 复折射率特征
     - 垂直入射反射率 $F_0$
     - 折射光去向与漫反射本质
   * - **电介质 (绝缘体)**
     - $k \approx 0$（消光系数几乎为零）
     - **极低（通常在 $0.02 \sim 0.05$ 之间，非金属通识取 $0.04$）**
     - 光线穿透进入内部，在次表面颗粒多次散射后折射出射，形成**漫反射（Diffuse）**
   * - **导体 (金属)**
     - $k \gg 0$（存在大量自由电子海，消光系数极大）
     - **极高（通常在 $0.60 \sim 0.95$ 之间，且对不同波长 $\lambda$ 呈现明显差异）**
     - 进入金属的光波在几纳米内被自由电子全部吸收转化为热能，**零次表面散射，漫反射项严格为 0**

掠射角菲涅尔全反射极限 (Fresnel at Grazing Angle)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

观察菲涅尔方程的边界行为：当入射角趋于掠射角极限（$	heta_i 	o 90^\circ$，即 $\cos	heta_i 	o 0$）时，无论是玻璃、塑料、水面还是粗糙的锈铁：

.. math::

   \lim_{	heta_i 	o 90^\circ} R_s = 1.0, \quad \lim_{	heta_i 	o 90^\circ} R_p = 1.0 \quad \Longrightarrow \quad F(90^\circ) = 1.0

**物理定律推论**：任何物理表面在掠射视角下，都呈现出 100% 的理想镜面反射特性（即著名的“菲涅尔边缘泛光”现象）。

------------------------------------------------------------------------
19.2 Schlick 经验近似公式推导与误差分析
------------------------------------------------------------------------

精确的麦克斯韦菲涅尔方程包含多次开方与三角函数解算，在 GPU 实时渲染管线中执行开销过高。1994 年，Christophe Schlick 提出了基于有理多项式拟合的 **Schlick 菲涅尔近似公式**。

Schlick 近似代数推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设光线垂直入射（$	heta_i = 0^\circ$）时的基础反射率为 $F_0$。对于电介质（$n_1 = 1.0$ 空气，$n_2 = n$ 材质）：

.. math::

   F_0 = \left( \frac{n - 1}{n + 1} \right)^2

Schlick 观察到菲涅尔曲线在 $	heta_i \in [0^\circ, 90^\circ]$ 区间内的变化趋势类似于 5 次幂曲线，提出了两点插值函数：

.. math::

   F_{	ext{Schlick}}(\mathbf{v}, \mathbf{h}) = F_0 + (1 - F_0) (1 - (\mathbf{v} \cdot \mathbf{h}))^5

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Schlick 5 次方菲涅尔插值曲线形态                    |
   +-------------------------------------------------------------------------+

   反射率 F
    1.0 |                                                     * * * (F90 = 1.0)
        |                                                 * *
        |                                             * *
        |                                         * *
        |                                     * *
    F0  |* * * * * * * * * * * * * * * * * *
        +------------------------------------------------------------> 入射夹角 θ
        0° (垂直视线: v·h = 1)                                   90° (掠射角: v·h = 0)

Schlick 近似误差分析与工业地位
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **电介质精度**：对于折射率 $n \in [1.3, 1.8]$（涵盖水 $1.33$、塑料 $1.5$、玻璃 $1.52$、红宝石 $1.76$）的常见电介质，Schlick 近似与精确解的最大相对误差小于 **1.2%**，视觉上完全不可辨识；
- **金属导体精度**：对于消光系数 $k$ 极大的金属，虽然高阶色散存在微弱偏差，但 Schlick 近似通过将 $F_0$ 扩展为 RGB 三通道向量（如铜的 $F_0 = [0.95, 0.64, 0.54]$，金的 $F_0 = [1.00, 0.71, 0.29]$），能够完美复现金属性质的有色镜面高光；
- **计算效率**：仅需 1 次减法、4 次乘法和 1 次加法，成为了当代所有实时图形 API、游戏引擎与工业离线渲染器的通用标准。

------------------------------------------------------------------------
19.3 几何遮蔽与阴影项 (Geometric Shadowing/Masking - G 项)
------------------------------------------------------------------------

在微表面模型中，由于微观几何微元高低错落，光线与视线在微表面上的传播不可避免地会发生相互阻挡：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     微表面微观自遮蔽与自阴影几何分类                    |
   +-------------------------------------------------------------------------+

          入射光线 l                                    出射观察视线 v
              \                                             /
               \                                           /
                \           遮蔽 (Masking)                /           阴影 (Shadowing)
                 \                \                      /                /
                  \                v                    /                v
                   \             +----+                /               +----+
                    \            |    |               /                |    |
                     \           |    |              /                 |    |
                      v          |    |             v                  |    |
                      \    m     |    |            /     m             |    |
                       \   ^     |    |           /      ^             |    |
                        \  |     |    |          /       |             |    |
   ----------------------+-+-----+----+---------+-------+-------------+----+-------- (表面)

1. **遮蔽（Masking）**：微表面法线 $\mathbf{m} = \mathbf{h}$，能够将光反射向视线 $\mathbf{v}$，但出射光线在离开表面时被前方的微表面阻挡，无法到达观察者；
2. **阴影（Shadowing）**：微表面朝向 $\mathbf{h}$，但入射光线 $\mathbf{l}$ 在照射到该微表面前被邻近高耸的微表面阻挡，未能照亮该微元。

省略几何项 $G$ 的灾难性后果：分母掠射角爆炸
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Cook-Torrance 框架的分母包含 $(\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})$。当观察者处于掠射角（$\mathbf{n} \cdot \mathbf{v} 	o 0$）或光源处于掠射角（$\mathbf{n} \cdot \mathbf{l} 	o 0$）时，分母迅速趋近于 0。若没有几何项 $G$ 在分子上提供相应的衰减，BRDF 表达式将直接趋近于 $+\infty$，导致物体边缘产生极不真实的刺眼纯白高光瑕疵（Grazing Edge Glitch）。

Smith 几何阴影遮蔽框架 (Smith Formulation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1967 年，B. G. Smith 提出了统计光学中最著名的阴影遮蔽分析框架。Smith 假设微表面的自遮挡与自阴影在空间上相互独立，将双向几何项分解为两个单向可见性因子的乘积：

.. math::

   G(\mathbf{l}, \mathbf{v}, \mathbf{h}) = G_1(\mathbf{l}, \mathbf{h}) \cdot G_1(\mathbf{v}, \mathbf{h})

其中 $G_1(\mathbf{v}, \mathbf{h})$ 表示从视角 $\mathbf{v}$ 观察时微观法线为 $\mathbf{h}$ 的微表面未被遮挡的概率。Smith 推导出 $G_1$ 与辅助阴影函数 $\Lambda(\mathbf{v})$ 的严格解析关系：

.. math::

   G_1(\mathbf{v}, \mathbf{h}) = \frac{\chi^+(\mathbf{v} \cdot \mathbf{h})}{1 + \Lambda(\mathbf{v})}

其中 $\chi^+(x)$ 为阶跃函数（当 $x > 0$ 时为 1，否则为 0）。辅助函数 $\Lambda(\mathbf{v})$ 描述了视线方向微表面微观斜率超出可见范围的积分面积比。对于 **GGX / Trowbridge-Reitz 分布**，$\Lambda(\mathbf{v})$ 具有精确的解析形式：

.. math::

   \Lambda(\mathbf{v}) = \frac{-1 + \sqrt{1 + \alpha^2 	an^2	heta_v}}{2} = \frac{-1 + \sqrt{1 + \alpha^2 \frac{1 - (\mathbf{n} \cdot \mathbf{v})^2}{(\mathbf{n} \cdot \mathbf{v})^2}}}{2}

代入 $G_1$ 即可得到著名的 **Smith-GGX 单向遮蔽函数**：

.. math::

   G_1(\mathbf{v}) = \frac{2 (\mathbf{n} \cdot \mathbf{v})}{(\mathbf{n} \cdot \mathbf{v}) + \sqrt{\alpha^2 + (1 - \alpha^2) (\mathbf{n} \cdot \mathbf{v})^2}}

------------------------------------------------------------------------
19.4 高度相关几何遮蔽 (Height-Correlated G 项) 与可见性函数 ($V$ 项)
------------------------------------------------------------------------

传统的分离式 Smith 模型假设光线入射遮蔽与视线出射遮蔽是完全独立的。然而在物理现实中，**位置较高的微表面既容易被光照亮，也容易被观察者看见**（高度相关性 Height Correlation）。

Smith 分离式 vs Smith 高度相关模型对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

2014 年，Eric Heitz 在经典论文《Understanding the Masking-Shadowing Function in Microfacet-Based BRDFs》中证明了高度相关模型的物理优越性：

.. math::

   G_{	ext{Smith-Joint}}(\mathbf{l}, \mathbf{v}) = \frac{\chi^+(\mathbf{v} \cdot \mathbf{h}) \chi^+(\mathbf{l} \cdot \mathbf{h})}{1 + \Lambda(\mathbf{l}) + \Lambda(\mathbf{v})}

.. list-table:: 几何阴影遮蔽项（$G$ 项）模型演进对比
   :widths: 20 30 25 25
   :header-rows: 1
   :class: tight-table

   * - 几何项模型
     - 数学表达结构
     - 物理自洽性与能量特性
     - 工业应用现状
   * - **Cook-Torrance 隐式**
     - $G = \min\left(1, \frac{2(n\cdot h)(n\cdot v)}{v\cdot h}, \frac{2(n\cdot h)(n\cdot l)}{v\cdot h}\right)$
     - 经验对称 V 型槽假设，非光滑可导，边缘不连续
     - 已被现代 PBR 彻底弃用
   * - **Smith 分离式 (Separable)**
     - $G = G_1(\mathbf{l}) \cdot G_1(\mathbf{v})$
     - 假设阴影与遮蔽统计独立，高粗糙度下偏暗
     - 早期 UE4 / Unity Standard
   * - **Smith 高度相关 (Correlated)**
     - $G = \frac{1}{1 + \Lambda(\mathbf{l}) + \Lambda(\mathbf{v})}$
     - **严格考虑微表面高度关联性，完美消除过度变暗**
     - **当代现代图形引擎统治级标准**

可见性函数 (Visibility Function - $V$ 项) 代数合并优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 GPU 着色器中，直接计算 Cook-Torrance 分子中的 $G$ 再除以分母 $4(\mathbf{n} \cdot \mathbf{l})(\mathbf{n} \cdot \mathbf{v})$，会造成大量重复的开方与乘法指令。现代引擎将几何项与分母项合并定义为**可见性函数（Visibility Function - $V$ 项）**：

.. math::

   V(\mathbf{l}, \mathbf{v}) = \frac{G(\mathbf{l}, \mathbf{v})}{4 (\mathbf{n} \cdot \mathbf{l}) (\mathbf{n} \cdot \mathbf{v})}

将高度相关的 Smith-GGX 展开代入 $V(\mathbf{l}, \mathbf{v})$，分子分母中的公共项可以进行优雅的代数抵消：

.. math::

   V_{	ext{Smith-GGX}}(\mathbf{l}, \mathbf{v}, \alpha) = \frac{0.5}{(\mathbf{n} \cdot \mathbf{l}) \sqrt{(\mathbf{n} \cdot \mathbf{v})^2 (1 - \alpha^2) + \alpha^2} + (\mathbf{n} \cdot \mathbf{v}) \sqrt{(\mathbf{n} \cdot \mathbf{l})^2 (1 - \alpha^2) + \alpha^2}}

此时，整个 Cook-Torrance 镜面反射项被精简为极致优美的形式：

.. math::

   f_{	ext{spec}}(\mathbf{l}, \mathbf{v}) = D(\mathbf{h}) \cdot F(\mathbf{v}, \mathbf{h}) \cdot V(\mathbf{l}, \mathbf{v})

在 GPU 着色器指令级别，该公式不仅杜绝了除以 0 的风险，而且消除了额外的除法指令，大幅提升了 ALU 流水线吞吐率。

------------------------------------------------------------------------
19.5 高粗糙度能量丢失与多重散射 (Multiple Scattering) 补偿
------------------------------------------------------------------------

微表面理论建立在“单次散射（Single Scattering）”的简化假设之上，即假设光线打在微表面后发生一次反射便离开表面或被彻底吸收。

炉温测试 (Furnace Test) 揭示的能量黑洞危机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

将一个反射率为 1.0（无吸收全反射金属球）置于均匀白光环境中（各个方向入射光强均为 1.0）。根据热力学第一定律与能量守恒定律，渲染出来的球体表面任意像素颜色值必须恒等于 1.0（不可变亮，也不可变暗）。

然而，当增加材质粗糙度（$\alpha 	o 1.0$）时，测试结果显示球体边缘出现严重的灰暗暗斑，整体反射能量衰减高达 **30% ~ 50%**！

.. code-block:: text

   +-------------------------------------------------------------------------+
   |              单次散射能量丢失 vs 多重散射 (Multiple Scattering) 补偿    |
   +-------------------------------------------------------------------------+

   [ 单次散射假设 (Single Scattering) ]
   入射光 l ---> \       /
                  \     /
                   \   / 被几何遮蔽 (Masked)
                    \ v
                     +-----> 被微表面挡住的光线被直接视为“全部消失 (Lost Energy)”!
                             导致粗糙金属呈现脏灰暗淡的非物理外观!

   [ 真实物理多重散射 (Multiple Scattering) ]
   入射光 l ---> \       / ---> 二次/多次反射光线最终成功弹射出表面!
                  \     /       (携带高阶能量重新射向视线方向 v)
                   \   /
                    \ /
                     +-----> 能量守恒闭环: 恢复丢失的 30%~50% 反射辐射通量!

Kulla-Conty (2017) 实时多重散射能量补偿模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

2017 年，Christopher Kulla 与 Alejandro Conty 提出了现代工业界广泛采用的微表面多重散射能量补偿解析方案。

1. **预积分单次散射方向反照率（Directional Albedo $E(\mu)$）**：
   离线预计算单次散射在给定视线余弦角 $\mu = \mathbf{n} \cdot \mathbf{v}$ 与粗糙度 $\alpha$ 下的积分反照率表：
   $$E(\mu, \alpha) = \int_{\Omega} f_{	ext{spec}}(\mathbf{l}, \mathbf{v}) (\mathbf{n} \cdot \mathbf{l}) d\omega_l$$
   丢失的能量比例即为 $1 - E(\mu, \alpha)$；
2. **多重散射能量补偿波瓣（Multiple-Scattering Lobe）**：
   Kulla 与 Conty 构建了一个满足互易性与能量守恒的附加各向同性镜面反射叶 $f_{	ext{ms}}$：
   $$f_{	ext{ms}}(\mathbf{l}, \mathbf{v}) = \frac{(1 - E(\mathbf{n} \cdot \mathbf{l})) (1 - E(\mathbf{n} \cdot \mathbf{v}))}{\pi (1 - E_{	ext{avg}})} \cdot \frac{F_{	ext{avg}} E_{	ext{avg}}}{1 - F_{	ext{avg}} (1 - E_{	ext{avg}})}$$
   其中 $E_{	ext{avg}} = 2 \int_0^1 E(\mu) \mu d\mu$ 为半球平均方向反照率，$F_{	ext{avg}} = \frac{1}{21} + \frac{20}{21} F_0$ 为平均菲涅尔反射率；
3. **最终 PBR 镜面反射合成**：
   $$f_{	ext{spec\_complete}} = f_{	ext{spec\_single}} + f_{	ext{ms}}$$
   加入 $f_{	ext{ms}}$ 后，粗糙金属在极端高粗糙度下能够完美通过炉温测试，彻底消除了金属在暗光边缘发灰发脏的顽疾。

------------------------------------------------------------------------
19.6 现代 GPU 工业级 HLSL 源码实现
------------------------------------------------------------------------

以下给出工业级渲染引擎中直接调用的标准 HLSL 核心实现函数：

.. code-block:: hlsl

   // HLSL: 工业级 PBR 菲涅尔项、几何遮蔽项与可见性函数实现

   // 1. Schlick 菲涅尔反射函数 (支持三通道彩色 F0)
   float3 FresnelSchlick(float cosTheta, float3 F0) {
       // clamp 防止浮点误差导致的负数
       float oneMinusCos = saturate(1.0f - cosTheta);
       float oneMinusCos5 = oneMinusCos * oneMinusCos * oneMinusCos * oneMinusCos * oneMinusCos;
       return F0 + (1.0f - F0) * oneMinusCos5;
   }

   // 2. 粗糙度感知的 IBL 菲涅尔函数 (防止粗糙表面掠射角反射过度饱和)
   float3 FresnelSchlickRoughness(float cosTheta, float3 F0, float roughness) {
       float oneMinusCos = saturate(1.0f - cosTheta);
       float oneMinusCos5 = oneMinusCos * oneMinusCos * oneMinusCos * oneMinusCos * oneMinusCos;
       return F0 + (max(float3(1.0f - roughness, 1.0f - roughness, 1.0f - roughness), F0) - F0) * oneMinusCos5;
   }

   // 3. 高度相关 Smith-GGX 联合可见性函数 V = G / (4 * NdotL * NdotV)
   float VisibilitySmithGGXCorrelated(float NdotL, float NdotV, float roughness) {
       float a = roughness * roughness; // Disney 感知粗糙度映射
       float a2 = a * a;

       // 限制 a2 极小值防止除零
       a2 = max(a2, 1e-5f);

       float lambdaV = NdotL * sqrt(NdotV * NdotV * (1.0f - a2) + a2);
       float lambdaL = NdotV * sqrt(NdotL * NdotL * (1.0f - a2) + a2);

       float v = 0.5f / (lambdaV + lambdaL + 1e-5f);
       return saturate(v);
   }

   // 4. 完整的 Cook-Torrance 镜面反射着色解算
   float3 EvaluateCookTorranceSpecular(
       float3 N, float3 V, float3 L, 
       float3 albedo, float metallic, float roughness,
       out float3 kS, out float3 kD
   ) {
       float3 H = normalize(V + L);
       float NdotL = saturate(dot(N, L));
       float NdotV = saturate(dot(N, V));
       float NdotH = saturate(dot(N, H));
       float VdotH = saturate(dot(V, H));

       // 计算介质基础反射率 F0 (非金属取 0.04, 金属取 albedo)
       float3 F0 = lerp(float3(0.04f, 0.04f, 0.04f), albedo, metallic);

       // 1. 法线分布项 D (GGX)
       float D = DistributionGGX(NdotH, roughness);

       // 2. 菲涅尔项 F (Schlick)
       float3 F = FresnelSchlick(VdotH, F0);

       // 3. 几何可见性项 V (Smith-GGX Correlated, 已内化分母 4*NdotL*NdotV)
       float V_term = VisibilitySmithGGXCorrelated(NdotL, NdotV, roughness);

       // 镜面反射能量比例即为菲涅尔反射率
       kS = F;
       // 漫反射能量比例遵循能量守恒 (金属无漫反射)
       kD = (float3(1.0f, 1.0f, 1.0f) - kS) * (1.0f - metallic);

       // 最终镜面反射 BRDF
       float3 specularBRDF = D * F * V_term;

       return specularBRDF;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从经典麦克斯韦电磁波交界面条件出发，系统剖析了电介质与金属导体的光学反射本质，深入推导了 Schlick 5 次方近似公式的误差边界，解析了微表面几何遮蔽项（$G$ 项）消除掠射角分母爆炸的力学原理，确立了 Smith 高度相关模型及可见性函数（$V$ 项）的 GPU 指令级合并优化，并阐释了 Kulla-Conty 实时多重散射能量补偿模型。

在掌握了法线分布 $D$、菲涅尔反射 $F$ 与几何遮蔽 $G$ 三大微表面核心支柱之后，下一章我们将深入第四模块收官之作——**进阶材质表达与着色：Disney Principled BRDF、次表面散射 (BSSRDF) 与各向异性材质**，系统解构以美术为中心的 Disney 材质模型、用于皮肤玉石渲染的次表面散射偶极子/高斯模型、清漆层（Clearcoat）与织物光泽（Sheen）等多层复杂物理材质的高级着色体系。
