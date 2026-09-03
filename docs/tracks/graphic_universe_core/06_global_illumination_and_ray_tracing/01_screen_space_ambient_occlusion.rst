========================================================================
Chapter 26: 屏幕空间环境光遮蔽 (SSAO)：从球体采样、HBAO 到 GTAO 与弯曲法线
========================================================================

.. note:: 前置背景与认知承接
   在上一卷（Part 5）中，我们系统解构了直接光照下的阴影映射（Shadow Mapping、CSM、PCSS）与全局空间加速结构（BVH）。直接光阴影解决了光源可见性问题，但在真实物理世界中，物体表面接收的光能除了来自直射光源，还包含大量来自天空穹顶（Sky Dome）、环境反射以及周围物体多次漫反射弹射的间接光（Indirect Light）。

   在经典光栅化着色模型中，若仅仅为无直射光区域施加一个全局恒定的环境光常量 $I_{	ext{ambient}}$，会导致场景失去空间深度感，物体呈现出悬浮、塑料化以及背光面均匀泛白的严重失真。**环境光遮蔽（Ambient Occlusion - AO）通过评估物体表面局部几何微环境对半球环境光的物理遮挡程度，在接触面、缝隙、凹坑与折角处生成柔和的接触阴影（Contact Shadows / Crevice Shading），是现代物理渲染管线中构建空间立体感与几何质感的最关键基石。** 本章将系统解构从 Crytek 原始 SSAO、地平线基准 HBAO 到现代微表面真实感 GTAO 的演进脉络，推导基于投影积分的闭式解析解，剖析弯曲法线（Bent Normals）对 PBR 间接光照的各向异性重构，并交付工业级 HLSL 降噪与着色实现。

------------------------------------------------------------------------
26.1 环境光遮蔽的物理本质与渲染方程解耦
------------------------------------------------------------------------

在辐射度量学中，物体表面点 $\mathbf{x}$ 沿观察方向 $\omega_o$ 出射的漫反射辐射亮度可由通用渲染方程描述：

.. math::

   L_o(\mathbf{x}, \omega_o) = \int_{\Omega^+} L_i(\mathbf{x}, \omega_i) f_r(\mathbf{x}, \omega_i, \omega_o) V(\mathbf{x}, \omega_i) (\mathbf{n} \cdot \omega_i) d\omega_i

其中 $V(\mathbf{x}, \omega_i) \in [0, 1]$ 为空间几何可见性函数（Visibility Term），$\Omega^+$ 为以法线 $\mathbf{n}$ 为中心的上半球立体角空间。

环境光遮蔽的积分定义与假设解耦
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

计算全场景任意方向的连续间接光入射亮度 $L_i(\mathbf{x}, \omega_i)$ 代价极其高昂。环境光遮蔽技术基于以下两项核心物理假设对渲染方程进行解耦：

1. **环境光各向同性假设**：假设入射环境光在整个上半球范围内是空间均匀或低频分布的常量亮度 $L_{	ext{ambient}}$；
2. **朗伯漫反射材质假设**：假设表面为理想朗伯漫反射体，双向反射分布函数 $f_r = \frac{\rho}{\pi}$（$\rho$ 为反照率 Albedo）。

基于上述假设，渲染方程中的入射光与材质项可从积分号中提取，剩余部分即为纯几何属性的**可接近度积分（Accessibility Integral）**：

.. math::

   L_{	ext{ambient\_out}}(\mathbf{x}) = \frac{\rho}{\pi} L_{	ext{ambient}} \int_{\Omega^+} V(\mathbf{x}, \omega_i) (\mathbf{n} \cdot \omega_i) d\omega_i

将无遮挡状态下的上半球投影立体角积分 $\int_{\Omega^+} (\mathbf{n} \cdot \omega_i) d\omega_i = \pi$ 作为归一化分母，定义点 $\mathbf{x}$ 的**环境光可接近度（Ambient Accessibility）$A(\mathbf{x})$** 与 **环境光遮蔽度（Ambient Occlusion）$	ext{AO}(\mathbf{x})$**：

.. math::

   A(\mathbf{x}) = \frac{1}{\pi} \int_{\Omega^+} V(\mathbf{x}, \omega_i) (\mathbf{n} \cdot \omega_i) d\omega_i, \quad 	ext{AO}(\mathbf{x}) = 1.0 - A(\mathbf{x})

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             环境光遮蔽 (AO) 半球空间可见性与余弦投影积分物理模型        |
   +-------------------------------------------------------------------------+

                 入射环境光 (均布漫反射)
                 \   \   \   |   /   /   /
                  \   \   \  |  /   /   /
                   v   v   v v v   v   v
                +-------------------------+
                |    上半球空间 \Omega^+   |
                |           .---.         |
                |         /   |   \       |
                |  遮挡物/ \  | n / \     |
                |  +---+    \ | /    \    |
                |  |   |=====>|====== \   |  <--- 遮挡区域 V(x, \omega_i) = 0
                |  |   |     \|/       \  |
                +--+---+------x-----------+
                    墙角缝隙  着色点 x (A(x) < 1.0, 产生柔和暗角)

.. list-table:: 典型几何拓扑结构下的理论环境光可接近度 $A(\mathbf{x})$ 与视觉效果
   :widths: 20 22 25 33
   :header-rows: 1
   :class: tight-table

   * - 几何拓扑结构
     - 半球可见立体角空间
     - 理论可接近度 $A(\mathbf{x})$
     - 物理着色表现
   * - **完全开阔平面**
     - 完整上半球 ($2\pi$ sr)
     - $A(\mathbf{x}) = 1.00$ ($	ext{AO}=0$)
     - 无遮蔽，接收完整漫反射环境光
   * - **$90^\circ$ 直角墙角 (内折角)**
     - 半个上半球 ($\pi$ sr)
     - $A(\mathbf{x}) \approx 0.50$ ($	ext{AO}=0.5$)
     - 呈现典型直角阴影过渡
   * - **$90^\circ$ 三维墙角 (凹三面折角)**
     - 四分之一上半球 ($\frac{\pi}{2}$ sr)
     - $A(\mathbf{x}) \approx 0.25$ ($	ext{AO}=0.75$)
     - 强烈接触暗角，空间深陷感
   * - **微观狭缝与深孔内部**
     - 接近零立体角 ($\approx 0$ sr)
     - $A(\mathbf{x}) 	o 0.00$ ($	ext{AO} 	o 1.0$)
     - 几乎完全无光，呈现深邃接触黑缝

------------------------------------------------------------------------
26.2 经典 SSAO：半球采样、深度比较与固有缺陷
------------------------------------------------------------------------

在 CryEngine 2（Crytek, 2007）提出 SSAO 之前，高精度 AO 只能在离线渲染中通过蒙特卡洛光线追踪或预计算光照贴图（Bake Lightmaps）生成，无法应用于全动态场景。**屏幕空间环境光遮蔽（SSAO）的核心创新在于：将昂贵的三维场景几何求交问题，退化为利用 G-Buffer 深度图（Depth Buffer）与法线图在屏幕后处理阶段进行的 2.5D 几何近似计算。**

经典 SSAO 算法流程与几何重构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于屏幕上的每个像素 $(u, v)$：

1. **重建观察空间坐标**：读取硬件深度图 $z_{	ext{depth}}$，结合摄像机投影反矩阵 $\mathbf{P}^{-1}$ 重建着色点在观察空间中的三维坐标 $\mathbf{P}_{	ext{view}}$ 与法线 $\mathbf{N}_{	ext{view}}$：

   .. math::

      \mathbf{P}_{	ext{view}} = 	ext{ReconstructViewPos}(u, v, z_{	ext{depth}})

2. **生成切线空间半球采样核心 (Sample Kernel)**：在以着色点为原点的法线半球内预先生成 $K$ 个随机采样偏移向量 $\mathbf{v}_i$（$i \in [0, K-1]$，通常 $K=16 \sim 64$）。为了强化近距离微细节遮挡，采样点沿半径采用非线性二次方分布：

   .. math::

      \mathbf{v}_i = 	ext{normalize}(\mathbf{r}_i) \cdot 	ext{scale}_i, \quad 	ext{scale}_i = 	ext{lerp}\left(0.1, 1.0, \left(\frac{i}{K}\right)^2\right)

3. **随机旋转与去条带化 (De-banding)**：为了避免固定采样点引起的规则条带状人工痕迹（Banding Artifacts），引入一张尺寸为 $4 	imes 4$ 的重复平铺随机旋转纹理（Random Normal Texture）。在片元着色器中读取随机向量 $\mathbf{R}$，通过 Gram-Schmidt 正交化构建局部切线坐标系 $\mathbf{T}, \mathbf{B}, \mathbf{N}$，将半球采样点旋转至当前像素的随机朝向。

4. **屏幕空间投影与深度对比**：
   对于每个半球采样点 $\mathbf{P}_{	ext{sample}} = \mathbf{P}_{	ext{view}} + \mathbf{v}_i \cdot R_{	ext{radius}}$：
   - 将其通过摄像机投影矩阵变换至屏幕坐标 $(u_s, v_s)$；
   - 采样该屏幕位置处的实际场景深度 $z_{	ext{actual}} = 	ext{SampleDepth}(u_s, v_s)$；
   - **遮挡判定**：若 $z_{	ext{actual}}$ 比采样点自身的理论深度 $z_{	ext{sample}}$ 更靠近摄像机（即 $z_{	ext{actual}} < z_{	ext{sample}}$ 且在半径衰减范围内），则判定该采样点被遮挡。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                经典 SSAO 半球采样与深度比较几何原理                     |
   +-------------------------------------------------------------------------+

                             观察方向 (View Direction)
                                        ^
                                        |
                   屏幕采样位置 (u_s, v_s)   着色点像素 (u, v)
                           |                    |
                           v                    v
   视平面 (Near Plane):  [---*--------------------*-----------------]
                              \                  /
                               \                /
                                \              /
                                 \            /
   观察空间 (View Space):         \          /
       场景表面几何:               \        /      半球采样球体 (Radius R)
              +---------------------+      /         . - - - - .
              | 实际场景深度         |     /       /     . (未遮挡) \
              | z_actual (遮挡发生)  |    /       |     /           |
              |       * (挡在前面)   |   /        |    x (着色点 P)  |
              +-------+--------------+  /         |   / \           |
                       \               /           \ . * (已遮挡)  /
                        \             /              ' - - - - '
                         \           /          采样点深度 z_sample
                          \         /           (位于场景表面实体内部)
                           \       /
                            +-----+

经典 SSAO 的四大固有技术缺陷
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 经典 SSAO 算法固有缺陷与物理成因
   :widths: 20 35 45
   :header-rows: 1
   :class: tight-table

   * - 缺陷类型
     - 物理表现现象
     - 底层几何与算法成因
   * - **平坦表面自遮挡 (Self-Occlusion)**
     - 完全平坦的墙面出现大面积脏斑与随机噪点
     - 半球采样点有一半落在切平面微下方，离散深度采样误差导致其误判为被遮挡。
   * - **暗晕伪影 (Dark Haloing)**
     - 前景物体在远景背景上投射出不真实的黑色光晕
     - 屏幕空间仅有单一表面深度，算法无法感知物体厚度，将远景像素错误判定为被前景遮挡。
   * - **几何对比度缺失**
     - 折角阴影模糊、发虚，缺乏物理锐度
     - 均匀球形采样未与真实半球余弦积分对齐，缺乏地平线连续遮蔽判断。
   * - **高频噪声与带宽开销**
     - 旋转采样产生严重颗粒噪波，降噪开销巨大
     - 纯蒙特卡洛离散点采样收敛速度慢，单像素需要 32~64 次 Texture Fetch。

------------------------------------------------------------------------
26.3 地平线基准环境光遮蔽 (HBAO)
------------------------------------------------------------------------

为了彻底根除经典 SSAO 的平坦表面自遮挡与阴影发虚问题，Bavoil 与 Sainz（NVIDIA, 2008）提出了 **地平线基准环境光遮蔽（Horizon-Based Ambient Occlusion - HBAO）**。HBAO 首次将屏幕空间环境光遮蔽从盲目的“点采样判断”提升为符合连续积分几何学的“地平线角度积分”。

地平线仰角几何模型推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于观察空间中的着色点 $\mathbf{P}$ 与表面法线 $\mathbf{N}$，视线方向向量为 $\mathbf{V} = -	ext{normalize}(\mathbf{P})$。

HBAO 在屏幕空间中以着色点为中心，沿 $M$ 个均匀分布的极坐标旋转方向（Directions $	heta_m = \frac{2\pi m}{M}$）发射光线。在每个二维方向上，沿屏幕向外步进 $N$ 个离散步长，采样场景表面点 $\mathbf{S}_i$。

定义着色点 $\mathbf{P}$ 到采样点 $\mathbf{S}_i$ 的三维位移向量为 $\mathbf{D}_i = \mathbf{S}_i - \mathbf{P}$。

在由视线向量 $\mathbf{V}$ 与采样方向构成的二维投影切面内，着色点的**切线角（Tangent Angle）$t$** 定义为表面切平面与视平面的夹角；而采样点 $\mathbf{S}_i$ 相对于视平面的**地平线仰角（Horizon Angle）$h$** 定义为：

.. math::

   \sin(h) = \frac{\mathbf{D}_i \cdot \mathbf{V}}{\|\mathbf{D}_i\|}, \quad h = \arcsin\left( \frac{\mathbf{D}_i \cdot \mathbf{V}}{\|\mathbf{D}_i\|} \right)

在当前步进方向上，随着沿视线向外步进，遍历所有采样点并动态维护**最大地平线仰角 $h_{\max} = \max_i(h_i)$**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                HBAO 二维截面地平线角度 (Horizon Angle) 积分几何模型      |
   +-------------------------------------------------------------------------+

                                视线方向 V
                                   ^
                                   |      实际地平线最高点 S_max
                                   |       /
                                   |      /  最大遮蔽仰角 h_max
                                   |     /  . - - - - - -
                                   |    / .
                                   |   / '  遮蔽扇形区域 \Delta\Omega
                                   |  / .
                                   | / '
                                   |/ .
               切线方向 T -------- x ' ------------- 视平面基准线 (Angle = 0)
                                  / \ 切线角 t
                                 /   \
                                /     \  表面法线 N
                               /       \
                         着色点 P      场景实体内部

切面一维连续积分与距离衰减
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据微积分几何推导，在单个切面方向 $	heta$ 上，从切线角 $t$ 到最大地平线角 $h_{\max}$ 的遮蔽贡献可通过一维角度积分精确求解：

.. math::

   A_	heta = 1.0 - \int_{t}^{h_{\max}} \frac{1}{2} \cos(\alpha) d\alpha = 1.0 - \frac{1}{2} (\sin(h_{\max}) - \sin(t))

对所有 $M$ 个空间切面方向取平均，并引入物理距离衰减加权函数 $W(r)$ 以消除远距离物体的错误遮蔽，得到最终 HBAO 积分方程：

.. math::

   	ext{AO}_{	ext{HBAO}} = \frac{1}{M} \sum_{m=0}^{M-1} \left( \sin(h_{m,\max}) - \sin(t_m) \right) \cdot W(\|\mathbf{D}_{\max}\|)

.. math::

   W(r) = \max\left(0, 1.0 - \frac{r^2}{R_{\max}^2}\right)

**HBAO 的核心工业级优势**：
1. **天然免疫自遮挡**：积分下限由几何切线角 $\sin(t)$ 严格限定，平坦表面上 $h_{\max} = t$，积分结果恒为 0，彻底消除自遮挡脏斑；
2. **极高几何锐度**：准确捕捉细小管道、阶梯与凹槽处的尖锐接触阴影；
3. **样本利用率倍增**：仅需 4~8 个方向、每方向 4 个步进点（共 16~32 个采样），着色质量即可超越 64 次采样的经典 SSAO。

------------------------------------------------------------------------
26.4 地表真实感环境光遮蔽 (GTAO)
------------------------------------------------------------------------

尽管 HBAO 较经典 SSAO 有了质的飞跃，但其在二维截面积分向三维半球积分的累加映射中存在经验启发式近似，无法完全等价于渲染方程中的余弦加权积分。Jimenez 等人（Activision, 2016）提出了 **地表真实感环境光遮蔽（Ground Truth Ambient Occlusion - GTAO）**。GTAO 在数学上严格求解了半球切面与视线余弦投影的闭式解析积分，成为现代 3A 游戏引擎（如 Unreal Engine 5、Decima、Frostbite）的标准默认屏幕空间 AO 算法。

半球切面与视角投影数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

GTAO 的核心思想是：将三维半球积分分解为围绕视线向量 $\mathbf{V}$ 旋转的若干个二维空间切面（Slices），并在每个切面上精确求解由两个相对半轴（Left / Right）地平线仰角界定的半圆余弦加权积分。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                GTAO 对称双向地平线切面与余弦积分闭式模型                |
   +-------------------------------------------------------------------------+

                                 法线 N   视线 V
                                   ^      ^
                                   |     /  视角夹角 \gamma
                                   |    /
                                   |   /
              左地平线角 h_1       |  /          右地平线角 h_2
                     \             | /             /
                      \            |/             /
                       \           x (着色点 P)  /
                        \         / \           /
                         \       /   \         /
                          \     /     \       /
                           \   /       \     /
                 +----------\-+---------+---/----------+
                 | 左侧场景几何 | 局部表面 | 右侧场景几何 |
                 +--------------+----------+--------------+

设当前切面与视线方向构成的平面内，表面投影法线为 $\mathbf{n}_{	ext{proj}}$，其与视线 $\mathbf{V}$ 的夹角为 $\gamma$。
在切面左侧（Negative Direction）与右侧（Positive Direction）分别步进，求出左右两侧的最大地平线角 $h_1 \in [-\frac{\pi}{2}, \frac{\pi}{2}]$ 与 $h_2 \in [-\frac{\pi}{2}, \frac{\pi}{2}]$。

GTAO 闭式解析解积分公式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据 Jimenez 论文的微积分推导，在夹角为 $\gamma$ 的单一切面内，两地平线角界定的余弦加权可见性积分具备严格的**闭式解析解（Closed-form Analytic Solution）**：

.. math::

   I_{	ext{slice}}(h_1, h_2, \gamma) = \frac{1}{4} \left( -\cos(2h_1 - \gamma) + \cos(\gamma) + 2h_1 \sin(\gamma) \right) + \frac{1}{4} \left( -\cos(2h_2 - \gamma) + \cos(\gamma) + 2h_2 \sin(\gamma) \right)

对 $M$ 个均匀分布的切面方向求和平均，即获得精确匹配地表真值的环境光可见性 $A$：

.. math::

   A_{	ext{GTAO}} = \frac{1}{M} \sum_{m=0}^{M-1} I_{	ext{slice}}(h_{m,1}, h_{m,2}, \gamma_m)

空间步进与时间性抖动 (Temporal Jittering)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了在极低采样数下实现无噪波收敛，现代 GTAO 结合了时域特征：
- 采用 **低差异序列（Low Discrepancy Sequence，如 Weyl 序列或 Roberts $R_2$ 序列）** 对每帧的旋转角 $	heta$ 与步进初始偏移（Jitter）进行时域抖动；
- 在单帧仅需 **2 个切面方向（4 条射线步进）、每方向 3 个步进采样**（总计仅 12 次采样），结合后置 TAA 时域重投影，即可输出完全媲美离线烘焙质量的平滑纯净环境光遮蔽图。

------------------------------------------------------------------------
26.5 弯曲法线 (Bent Normals) 与 PBR 间接光照整合
------------------------------------------------------------------------

传统环境光遮蔽输出的是一个一维标量 $	ext{AO} \in [0, 1]$。在 PBR 管线着色时，通常简单地将其与漫反射 IBL（基于几何法线 $\mathbf{N}$ 采样的辐照度图 Irradiance Map）相乘：

.. math::

   L_{	ext{indirect\_naive}} = 	ext{DiffuseAlbedo} 	imes 	ext{SampleIBL}(\mathbf{N}) 	imes (1.0 - 	ext{AO})

传统标量 AO 的物理硬伤：漏光与失真
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当物体处于一侧强遮挡（如垂直墙根或悬崖底部）环境时，真实能够射入光线的开阔方向早已不再是几何法线 $\mathbf{N}$，而是显著偏向未被遮挡的开阔空间方向。若仍按原始法线 $\mathbf{N}$ 采样 IBL，会错误地将正上方或被遮挡侧的高亮环境光纳入计算，产生严重的**间接光漏光（Light Leaking）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                传统法线 vs 弯曲法线 (Bent Normal) IBL 采样差异          |
   +-------------------------------------------------------------------------+

                [ 传统法线 N 采样: 发生严重漏光 ]
                         天空强光区 (天空穹顶)
                         +-----------------+
                         |  L_sky (高亮)   |
                         +-----------------+
                               ^
                              /  \
                             /    \
            高耸建筑物      /      \
            (严重遮挡)     /        \
             +----+       /          \
             |    |      / 原始几何   \
             |    |     /  法线 N      \
             |    |    /  (指向强光区)  \
             |    |   /                  \
             |    |  /                    \
             +----+ x ---------------------+
                    着色点 (错误采样天空强光 -> 局部漏光泛白!)

                [ 弯曲法线 N_bent 采样: 物理正确 ]
                         天空强光区 (天空穹顶)
                         +-----------------+
                         |  L_sky (高亮)   |
                         +-----------------+
                                     ^
                                    /
            高耸建筑物             /  弯曲法线 N_bent
            (严重遮挡)            /  (指向实际开阔无遮挡方向)
             +----+              /
             |    |             /  正确采样来自开阔侧的反射光
             |    |            /
             |    |           /
             |    |          /
             |    |         /
             +----+ x -----+---------------+
                    着色点 (物理正确阴影过渡与方向性光照)

弯曲法线数学定义与 GTAO 联合输出
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**弯曲法线（Bent Normal）$\mathbf{N}_{	ext{bent}}$ 定义为：上半球空间中所有未被遮挡光线方向的加权平均向量（即可见立体角区域的质心方向）：**

.. math::

   \mathbf{N}_{	ext{bent}} = 	ext{normalize}\left( \int_{\Omega^+} V(\mathbf{x}, \omega_i) \omega_i (\mathbf{n} \cdot \omega_i) d\omega_i \right)

在 GTAO 求解各切面地平线角 $h_1, h_2$ 的同时，可以以近乎零的额外算力开销，直接解析累加各切面未遮挡区域的平均角分量：

.. math::

   	heta_{	ext{mid}} = \frac{h_1 + h_2}{2}, \quad \mathbf{n}_{	ext{slice}} = \mathbf{V} \cos(	heta_{	ext{mid}}) + \mathbf{T} \sin(	heta_{	ext{mid}})

.. math::

   \mathbf{N}_{	ext{bent}} = 	ext{normalize}\left( \sum_{m=0}^{M-1} \mathbf{n}_{m,	ext{slice}} \cdot I_{	ext{slice}}(h_{m,1}, h_{m,2}) \right)

PBR 镜面反射视锥遮挡 (Specular Occlusion)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

除了修正漫反射 IBL，弯曲法线 $\mathbf{N}_{	ext{bent}}$ 与标量 AO 还可用于推导高光反射的**镜面遮蔽因子（Specular Occlusion - SO）**。根据 Sébastien Lagarde 的推导模型：

.. math::

   	ext{SO} = 	ext{saturate}\left( \frac{(\mathbf{N}_{	ext{bent}} \cdot \mathbf{R}) - (1.0 - 	ext{AO})}{1.0 - 	ext{roughness}} \right)

其中 $\mathbf{R}$ 为视线反射方向向量。当表面反射视锥被几何体深度阻挡时，高光反射会被物理剔除，彻底消除了金属材质在拐角处的虚假刺眼反光。

------------------------------------------------------------------------
26.6 双边深度法线感知空间降噪 (Bilateral Filtering)
------------------------------------------------------------------------

为了实现实时极致性能，屏幕空间 AO 生成 pass 通常在**半分辨率（Half-Resolution）**下运行，并采用时空随机抖动采样。原始 AO 缓冲区包含显著的高频随机噪声，必须经过**边缘感知跨界双边滤波（Cross-Bilateral Filter）**方可合成至主光照缓冲区。

联合双边滤波核函数
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于中心像素 $p$ 与邻域滤波采样像素 $q$（滤波窗口通常为 $5 	imes 5$ 或两遍可分离 $9 	imes 9$）：

.. math::

   W(p, q) = G_{	ext{spatial}}(\|p - q\|) \cdot G_{	ext{depth}}(z_p, z_q) \cdot G_{	ext{normal}}(\mathbf{N}_p, \mathbf{N}_q)

.. math::

   G_{	ext{spatial}}(d) = \exp\left( -\frac{d^2}{2\sigma_s^2} \right), \quad G_{	ext{depth}}(z_p, z_q) = \exp\left( -\frac{|z_p - z_q|}{\sigma_z \cdot |
abla z_p| + \epsilon} \right)

.. math::

   G_{	ext{normal}}(\mathbf{N}_p, \mathbf{N}_q) = \max(0, \mathbf{N}_p \cdot \mathbf{N}_q)^{\sigma_n}

**边缘保护机理**：
1. **深度权重 $G_{	ext{depth}}$**：当邻域像素 $q$ 跨越了几何物体边缘时，$|z_p - z_q|$ 急剧增大，权重归零，避免前景与背景之间的错误模糊（Halo Bleeding）；
2. **法线权重 $G_{	ext{normal}}$**：当邻域像素位于不同朝向的平截面上时（如立方体两相邻面，$\mathbf{N}_p \cdot \mathbf{N}_q \approx 0$），权重归零，确保几何硬边缘的阴影转折依然刀锋般锐利。

------------------------------------------------------------------------
26.7 工业级 GTAO + Bent Normal Compute Shader (HLSL) 完整实现
------------------------------------------------------------------------

以下是符合 DirectX 12 / Vulkan 工业标准的 GTAO 生成与弯曲法线输出 Compute Shader 源码实现：

.. code-block:: hlsl

   // HLSL: 工业级地表真实感环境光遮蔽 (GTAO) + 弯曲法线 (Bent Normal) 生成 Shader
   // 特性: 2 切面 3 步进低开销架构 + 闭式余弦解析解 + 时域抖动 + 物理距离衰减

   #define NUM_SLICES 2
   #define NUM_STEPS  3
   #define PI         3.14159265359f
   #define HALF_PI    1.57079632679f

   struct GTAOConstants {
       float4x4 ProjMatrix;
       float4x4 InvProjMatrix;
       float4   ScreenSize;      // xy: ViewportSize, zw: RcpViewportSize
       float4   CameraParams;    // x: Near, y: Far, z: RadiusMultiplier, w: FalloffRange
       float    AORadius;        // 物理采样半径 (米, 如 1.5m)
       float    TemporalAngle;   // 时域旋转偏移 (来自 R2 序列)
       float    TemporalJitter;  // 时域步进偏移
       uint     FrameIndex;
   };

   ConstantBuffer<GTAOConstants> g_GTAOCB       : register(b0);
   Texture2D<float>              g_DepthTexture  : register(t0);
   Texture2D<float3>             g_NormalTexture : register(t1);
   SamplerState                  g_PointSampler  : register(s0);

   RWTexture2D<float>            g_OutAO         : register(u0);
   RWTexture2D<float4>           g_OutBentNormal : register(u1);

   // 屏幕 UV 与硬件深度重建观察空间三维坐标
   float3 ReconstructViewPosition(float2 uv, float depth) {
       float4 clipPos = float4(uv.x * 2.0f - 1.0f, (1.0f - uv.y) * 2.0f - 1.0f, depth, 1.0f);
       float4 viewPos = mul(g_GTAOCB.InvProjMatrix, clipPos);
       return viewPos.xyz / viewPos.w;
   }

   // 闭式切面余弦可见性积分公式
   float IntegrateArc(float h1, float h2, float gamma) {
       float cosG = cos(gamma);
       float sinG = sin(gamma);
       return 0.25f * (-cos(2.0f * h1 - gamma) + cosG + 2.0f * h1 * sinG) +
              0.25f * (-cos(2.0f * h2 - gamma) + cosG + 2.0f * h2 * sinG);
   }

   [numthreads(8, 8, 1)]
   void CSMain(uint3 dispatchThreadID : SV_DispatchThreadID) {
       uint2 pixelCoord = dispatchThreadID.xy;
       if (pixelCoord.x >= (uint)g_GTAOCB.ScreenSize.x || pixelCoord.y >= (uint)g_GTAOCB.ScreenSize.y)
           return;

       float2 uv = (float2(pixelCoord) + 0.5f) * g_GTAOCB.ScreenSize.zw;
       float  depth = g_DepthTexture.SampleLevel(g_PointSampler, uv, 0);

       // 过滤天空盒无效深度 (逆 Z 下深度为 0.0)
       if (depth <= 1e-6f) {
           g_OutAO[pixelCoord] = 1.0f;
           g_OutBentNormal[pixelCoord] = float4(0.0f, 0.0f, 1.0f, 1.0f);
           return;
       }

       float3 viewPos = ReconstructViewPosition(uv, depth);
       float3 viewNorm = normalize(g_NormalTexture.SampleLevel(g_PointSampler, uv, 0).xyz);
       float3 viewDir = normalize(-viewPos);

       // 屏幕空间像素采样半径投影: R_pixel = (R_world * Fx) / Depth
       float projScale = g_GTAOCB.ProjMatrix[0][0] * 0.5f * g_GTAOCB.ScreenSize.x;
       float pixelRadius = (g_GTAOCB.AORadius * projScale) / max(viewPos.z, 0.1f);
       pixelRadius = clamp(pixelRadius, 4.0f, 128.0f);

       float totalVisibility = 0.0f;
       float3 bentNormalAccum = float3(0.0f, 0.0f, 0.0f);

       // 遍历切面方向
       [unroll]
       for (int sliceIdx = 0; sliceIdx < NUM_SLICES; ++sliceIdx) {
           float phi = (float(sliceIdx) + g_GTAOCB.TemporalAngle) * (PI / float(NUM_SLICES));
           float2 sliceDir = float2(cos(phi), sin(phi));

           // 构建切面空间正交基
           float3 slicePlaneNorm = normalize(cross(float3(sliceDir.x, sliceDir.y, 0.0f), viewDir));
           float3 tangent = cross(viewDir, slicePlaneNorm);
           float3 projNormal = viewNorm - slicePlaneNorm * dot(viewNorm, slicePlaneNorm);
           float  projNormLen = length(projNormal);

           if (projNormLen < 1e-4f) continue;
           projNormal /= projNormLen;

           // 计算投影法线与视线的夹角 gamma
           float gamma = acos(clamp(dot(projNormal, viewDir), -1.0f, 1.0f));
           if (dot(projNormal, tangent) < 0.0f) gamma = -gamma;

           // 初始化左右地平线角
           float h1 = -HALF_PI;
           float h2 = -HALF_PI;

           // 双向步进寻找地平线最大仰角
           [unroll]
           for (int stepIdx = 0; stepIdx < NUM_STEPS; ++stepIdx) {
               // 步长二次方非线性分布
               float stepScale = pow((float(stepIdx) + g_GTAOCB.TemporalJitter) / float(NUM_STEPS), 1.5f);
               float2 sampleOffset = sliceDir * (stepScale * pixelRadius);

               // 1. 正向采样点 (Side 1)
               float2 uv1 = uv + sampleOffset * g_GTAOCB.ScreenSize.zw;
               float  depth1 = g_DepthTexture.SampleLevel(g_PointSampler, uv1, 0);
               float3 pos1 = ReconstructViewPosition(uv1, depth1);
               float3 delta1 = pos1 - viewPos;
               float  distSq1 = dot(delta1, delta1);

               if (distSq1 < g_GTAOCB.AORadius * g_GTAOCB.AORadius) {
                   float cosAngle1 = dot(normalize(delta1), viewDir);
                   float angle1 = acos(clamp(cosAngle1, -1.0f, 1.0f));
                   h1 = max(h1, angle1);
               }

               // 2. 负向采样点 (Side 2)
               float2 uv2 = uv - sampleOffset * g_GTAOCB.ScreenSize.zw;
               float  depth2 = g_DepthTexture.SampleLevel(g_PointSampler, uv2, 0);
               float3 pos2 = ReconstructViewPosition(uv2, depth2);
               float3 delta2 = pos2 - viewPos;
               float  distSq2 = dot(delta2, delta2);

               if (distSq2 < g_GTAOCB.AORadius * g_GTAOCB.AORadius) {
                   float cosAngle2 = dot(normalize(delta2), viewDir);
                   float angle2 = -acos(clamp(cosAngle2, -1.0f, 1.0f));
                   h2 = max(h2, angle2);
               }
           }

           // 钳位地平线角在法线切平面上方
           h1 = clamp(h1, gamma - HALF_PI, gamma + HALF_PI);
           h2 = clamp(h2, gamma - HALF_PI, gamma + HALF_PI);

           // 闭式积分累加
           float visibility = IntegrateArc(h1, h2, gamma);
           totalVisibility += visibility;

           // 累加局部弯曲法线方向
           float midAngle = (h1 + h2) * 0.5f;
           float3 sliceBent = viewDir * cos(midAngle) + tangent * sin(midAngle);
           bentNormalAccum += sliceBent * visibility;
       }

       float finalVisibility = totalVisibility / float(NUM_SLICES);
       float finalAO = saturate(1.0f - finalVisibility);

       float3 finalBentNormal = normalize(bentNormalAccum);

       g_OutAO[pixelCoord] = finalAO;
       g_OutBentNormal[pixelCoord] = float4(finalBentNormal * 0.5f + 0.5f, 1.0f);
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了实时屏幕空间环境光遮蔽（SSAO）的演进脉络与微架构体系：
1. **物理本质**：推导了渲染方程中环境光项解耦为几何可接近度积分 $A(\mathbf{x})$ 的数学物理过程；
2. **经典 SSAO**：剖析了 2007 年 Crytek 原始半球离散深度比较模型，指出了其自遮挡、暗晕与对比度发虚的物理根源；
3. **地平线基准 HBAO**：深入剖析了沿切面扫描最大地平线仰角 $h_{\max}$ 的算法微架构，实现了平坦表面零自遮挡与阴影锐化；
4. **地表真实感 GTAO**：详细推导了 Jiménez 闭式余弦解析积分方程，阐明了其在极低采样数下达成地面真实感质量的核心机制；
5. **弯曲法线 (Bent Normals)**：从可见立体角质心出发定义弯曲法线，彻底消除了 PBR 漫反射 IBL 的局部漏光与高光虚假反光；
6. **工程实现**：交付了涵盖低差异抖动、双向步进与闭式求值的工业级 HLSL Compute Shader 完整实现。

至此，**第六模块第一章（Chapter 26）完工落盘（全书已完成 26/45 节）**。

在下一章中，我们将进一步探索屏幕空间光线技术的另一大核心支柱——**屏幕空间反射 (SSR - Screen Space Reflections)**。我们将深入剖析 **分层 Z 缓冲光线步进 (Hi-Z Raymarching)、双重求交回溯、物理厚度假设边缘衰减与基于 TAA 的时域滤波重投影架构**，敬请期待！
