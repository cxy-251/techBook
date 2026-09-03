========================================================================
Chapter 34: 运动模糊与体积光：速度缓冲区 (Velocity Buffer)、散射相位函数与 Raymarching
========================================================================

.. note:: 前置背景与认知承接
   在前一章（Chapter 33）中，我们系统剖析了时间性抗锯齿（Temporal Anti-Aliasing - TAA）的数学原理与工程实现。TAA 通过在相机透视矩阵中注入亚像素低差异抖动，并借助二维速度缓冲区（Velocity Buffer）与历史帧重投影机制，成功在时间维度上分摊了高频空间采样开销，消除了光栅化走样与镜面高光闪烁。

   然而，单纯消除锯齿仅解决了图像在静态与匀速低动态下的空间重构问题。在人眼与光学摄影机的真实物理感光过程中，由于快门开启时间（Shutter Time）的存在，传感器在曝光窗口内对光子通量进行连续的时间积分。当场景中存在高速运动的物体或相机发生剧烈旋转时，时间切片的离散渲染会导致两个极为严重的视觉缺陷：
   
   1. **时域断裂与频闪感（Temporal Stuttering / Strobing）**：以 60 FPS 或甚至 120 FPS 渲染的高速移动物体，在视网膜上表现为若干离散分离的虚影切片，完全丢失了物理世界中的连续运动轨迹；
   2. **介质光子交互的扁平化**：光线在穿过充满微尘、水汽、烟雾等参与介质（Participating Media）的大气空间时，光子被介质微粒吸收与多重前向/后向散射，形成具有空间纵深感的体积光（Volumetric Light / God Rays）与大气透视。若仅在不透明几何表面执行二维光照计算，整个三维世界将失去空气感与光子在大气中漫布的厚重真实感。

   本章将系统解构现代实时渲染管线中两项至关重要的时空连续性拟真技术：**基于速度缓冲区的相机/物体后处理运动模糊（Motion Blur）**，以及**基于辐射传输方程（RTE）、散射相位函数与 3D 视锥体素网格（Froxel Grid）的体积光与大气雾（Volumetric Fog）渲染体系**。

------------------------------------------------------------------------
34.1 物理快门光学模型与时域连续积分
------------------------------------------------------------------------

光学快门开角与曝光时间
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在电影摄影机中，曝光时间由机械旋转圆盘快门（Rotary Shutter）的旋转开角（Shutter Angle）与拍摄帧率（Frame Rate）决定：

.. math::

   T_{	ext{exposure}} = \frac{	heta_{	ext{shutter}}}{360^\circ 	imes 	ext{FPS}}

其中：
- $	heta_{	ext{shutter}}$：快门开角（度）。标准电影摄影通常采用 $180^\circ$ 开角（半开角规则），对应曝光时间恰好等于帧间隔的一半（例如 60 FPS 下曝光时间为 $1/120$ 秒）；
- $T_{	ext{exposure}}$：传感器感光单元对光子流进行物理积分的时间窗口长度。

在曝光时间 $T_{	ext{exposure}} = [t_0, t_1]$ 范围内，感光传感器单元接收到的总辐射曝辐量（Radiant Exposure）$H(\mathbf{p})$ 为辐射照度 $E(\mathbf{p}, t)$ 在时间轴上的连续积分：

.. math::

   H(\mathbf{p}) = \int_{t_0}^{t_1} E(\mathbf{p}, t) \, dt = \int_{-T_{	ext{exposure}}/2}^{T_{	ext{exposure}}/2} E(\mathbf{p}, t_0 + 	au) \, d	au

在离散光栅化图形渲染管线中，每一帧计算仅代表时间瞬间 $t_{	ext{current}}$ 的瞬时 Dirac 脉冲抽样：$E_{	ext{rendered}}(\mathbf{p}) = E(\mathbf{p}, t_{	ext{current}})$。若直接呈现这些瞬时抽样，高速运动的几何边缘在时间序列上呈现为剧烈的能量跳变。运动模糊的本质目标，就是利用有限的离散着色数据与速度向量场，在后处理阶段近似重构出该时间连续积分。

.. list-table:: 运动模糊实现架构与物理特性对比
   :widths: 20 20 25 35
   :header-rows: 1
   :class: tight-table

   * - 方案类别
     - 计算阶段
     - 显存与计算开销
     - 物理保真度与典型局限
   * - **时域分布式路径追踪 (Stochastic RT)**
     - 几何光线遍历
     - 极高 (单像素发射数十条时间抖动光线)
     - 绝对精确物理积分；除离线渲染与高端光线追踪外无法用于实时 3A 游戏
   * - **几何挤出体积 (Geometric Extrusion)**
     - 几何/网格着色器
     - 中等至高 (顶点与图元数翻倍)
     - 沿运动方向拉伸多边形网格并绘制半透明衰减；无法处理相机旋转与内部着色变化
   * - **屏幕空间速度卷积 (Screen-Space Post-Processing)**
     - 计算着色器 (Compute)
     - 低至中等 (单 Pass 速度图重构 + 模糊卷积)
     - 工业级标准；基于 Tile-Max 算法与深度加权，性能极佳，但在跨深度遮挡与复杂半透明区域存在重构瑕疵

------------------------------------------------------------------------
34.2 速度缓冲区 (Velocity Buffer) 与 Tile-Max 速度重构架构
------------------------------------------------------------------------

运动矢量的多维解耦与物理合成
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
速度缓冲区（Motion Vector / Velocity Buffer）是运动模糊与时间性抗锯齿共用的核心几何数据结构。对于屏幕空间任意像素 $\mathbf{p} = (x, y)$，其运动矢量 $\mathbf{v}(\mathbf{p}) = (\Delta u, \Delta v)$ 记录了该像素所对应的三维物理表面点从当前帧时间戳 $t$ 移动至上一帧时间戳 $t-1$ 的屏幕坐标位移（以像素或 UV 为单位）：

.. math::

   \mathbf{v}(\mathbf{p}) = \mathbf{p}(t) - \mathbf{p}(t-1)

在实际引擎架构中，运动矢量必须由两个相互独立的物理源合成：

1. **相机自身运动产生的背景速度场（Camera Motion）**：
   当相机在世界空间发生平移与旋转时，即使静态场景物体保持绝对静止，其在屏幕投影空间的位置依然发生剧烈变化。利用静态几何的当前帧深度 $z_{	ext{depth}}$ 与逆视锥投影矩阵，可纯解析计算出相机速度：

   .. math::

      \mathbf{P}_{	ext{world}} = \mathbf{M}_{	ext{view-proj, current}}^{-1} \cdot \mathbf{P}_{	ext{clip, current}}

   .. math::

      \mathbf{P}_{	ext{clip, previous}} = \mathbf{M}_{	ext{view-proj, previous}} \cdot \mathbf{P}_{	ext{world}}

   .. math::

      \mathbf{v}_{	ext{camera}} = 	ext{Project}(\mathbf{P}_{	ext{clip, current}}) - 	ext{Project}(\mathbf{P}_{	ext{clip, previous}})

2. **动态物体与骨骼刚体自位移速度场（Object Motion）**：
   对于角色骨骼蒙皮网格（Skinned Meshes）或具有局部物理线速度/角速度的刚体，其世界空间坐标本身随时间变化：$\mathbf{X}_{	ext{world}}(t) 
e \mathbf{X}_{	ext{world}}(t-1)$。
   顶点着色器必须同时输入两套骨骼变换矩阵（Current Transform 与 Previous Transform），计算出顶点在两帧的独立位置，并在像素着色器中将相减得到的有效二维速度写出至速度缓冲区（格式通常为 `R16G16_FLOAT` 或带符号定点数 `R16G16_SNORM`）。

屏幕空间后处理运动模糊的核心冲突：遮挡与分离 (Disocclusion)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在屏幕空间直接对像素执行沿速度矢量的简单均值模糊卷积（Box Blur）会导致致命的图像破损。其根本原因在于屏幕空间速度场存在**深度不连续性（Depth Discontinuity）**：

- **前景移动穿过静止背景（Foreground on Background）**：前景物体的像素速度极大，背景像素速度为零。高速运动的前景像素应该将自身色彩向后拉伸并覆盖在背景上（模糊外溢）；但背景像素**绝对不能**将静止的背景色彩反向涂抹到前景物体上方；
- **背景高速运动被静止前景遮挡（Background behind Foreground）**：当背景快速掠过前景边缘时，背景产生的运动模糊应当在静止前景物体轮廓处被物理截断（Hard Cut-Off），绝不能渗透到前景几何内部（Background Bleeding）。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                屏幕空间运动模糊深度交互与边界遮挡问题                   |
   +-------------------------------------------------------------------------+

      [ 场景视线剖面 ]
                               +-------------------+
                               | 高速前景物体      |
                               | (速度 V_fg 极大)  |
                               +-------------------+
                                        | (向右高速运动)
                                        v
      [ 静态背景 ] =========================================================
                                     ^
                                     |
      [ 像素着色冲突点 ]            (前景边缘跨越点)
      - 若盲目采样周边速度：静止背景点误采样前景 V_fg，导致静止背景被错误撕扯！
      - 必须引入：Tile-Max 速度分块粗筛与深度感知双边权重加权。

McGuire Tile-Max 与 Neighbor-Max 分层重构算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了以极高算力效率解决速度不连续导致的采样污染，Morgan McGuire 等人提出了工业界广泛采用的 **Tile-Max / Neighbor-Max 速度分级重构算法**（在 Unreal Engine 与 Frostbite 中被深度优化）：

.. code-block:: text

   [ 全分辨率 Velocity Buffer ] (例如 1920x1080)
                |
                v  (降采样阶段: 以 20x20 像素为 Tile 统计最大模长速度)
   [ Tile-Max 速度纹理 ] (尺寸 96x54)
                |
                v  (空间膨胀阶段: 提取 3x3 Tile 邻域内最大速度)
   [ Neighbor-Max 速度纹理 ] (尺寸 96x54)
                |
                v  (全分辨率运动模糊主 Pass: 依据 Neighbor-Max 动态决定搜索范围)
   [ 最终运动模糊输出 ]

1. **Tile-Max 阶段（速度降采样）**：
   将屏幕划分为固定尺寸的矩形图块（Tile，典型尺寸为 $k 	imes k = 20 	imes 20$ 像素，对应屏幕允许的最大模糊半径）。在计算着色器中，以 Tile 为单位遍历内部所有像素，找出其中**模长最大（速度最快）**的二维运动矢量写出至低分辨率 Tile 纹理：

   .. math::

      \mathbf{V}_{	ext{TileMax}}(T) = \arg\max_{\mathbf{p} \in T} \|\mathbf{v}(\mathbf{p})\|

2. **Neighbor-Max 阶段（邻域最大速度膨胀）**：
   高速前景物体的运动可能跨越相邻 Tile。因此，对低分辨率 Tile-Max 纹理执行一次 $3 	imes 3$ 的邻域最大值池化膨胀滤波（Max-Pooling），生成 `Neighbor-Max` 纹理：

   .. math::

      \mathbf{V}_{	ext{NeighborMax}}(T) = \arg\max_{N \in 	ext{Neighbor}_{3	imes 3}(T)} \|\mathbf{V}_{	ext{TileMax}}(N)\|

   `Neighbor-Max` 纹理提供了一个严格的物理保证：对于当前 Tile 内的任意像素，周围任何可能在时域曝光窗口内移动并覆盖到当前位置的外部物体，其最大速度绝对不会超过该 Tile 的 `Neighbor-Max`。

3. **模糊主 Pass 的自适应采样与深度分类**：
   在全分辨率运动模糊计算着色器中，读取当前像素所在位置的 `Neighbor-Max` 速度 $\mathbf{V}_{	ext{max}}$：
   - 若 $\|\mathbf{V}_{	ext{max}}\| < 0.5$ 像素，说明该区域及其周边完全静止，**立即执行早期跳出（Early-Out）**，直接拷贝原像素颜色，节约巨额显存带宽；
   - 若速度大于阈值，则沿该最大速度方向在曝光窗口内进行等距交错采样，并引入基于深度的前后遮挡加权函数。

------------------------------------------------------------------------
34.3 沿速度矢量线积分采样与权重滤波
------------------------------------------------------------------------

交错抖动线采样 (Jittered Line Integration)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
设当前像素为 $\mathbf{X}$，其局部速度为 $\mathbf{v}_X$，邻域最大速度为 $\mathbf{v}_{	ext{max}}$。采样线积分沿主导运动矢量方向对称展开。
为了使用较少采样点（如 $N = 8 \sim 16$ 步）消除规则步长带来的条带走样（Banding Artifacts），必须在采样偏移中注入基于屏幕空间蓝噪声（Blue Noise）或浮动交错哈希函数的微小抖动偏移：

.. math::

   \mathbf{S}_i = \mathbf{X} + \left( \frac{i + 	ext{jitter} - N/2}{N} \right) \cdot \mathbf{v}_{	ext{sampling}}, \quad i \in [0, N-1]

其中 $	ext{jitter} \in [-0.5, 0.5]$ 来自高频蓝噪声纹理。

深度双边加权函数 (Depth-Aware Weighting Function)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
对于每个采样点 $\mathbf{S}_i$，读取其对应的场景颜色 $C(\mathbf{S}_i)$、深度值 $Z(\mathbf{S}_i)$ 以及该采样点自身的局部运动矢量 $\mathbf{v}_{S_i}$。
中心像素与采样样本点之间的相互遮挡关系由以下三类物理准则判定：

1. **同层或背景模糊权重（Background / Same-Depth Layer）**：
   当采样点 $\mathbf{S}_i$ 与中心像素 $\mathbf{X}$ 处于同一深度层，或者 $\mathbf{S}_i$ 位于背景且其自身速度矢量与采样方向一致时，赋予完全权重；
2. **前景覆盖权重（Foreground Layer Blur Over Background）**：
   当采样点 $\mathbf{S}_i$ 的深度比中心像素更靠近相机（$Z(\mathbf{S}_i) < Z(\mathbf{X})$），且采样点自身的运动速度足以跨越两者之间的空间距离时，前景物体在运动中覆盖了背景，赋予高权重；
3. **前景硬边界剔除（Background Bleed Suppression）**：
   当采样点 $\mathbf{S}_i$ 处于背景深度（$Z(\mathbf{S}_i) > Z(\mathbf{X})$），但其运动速度微弱，无法追上前景物体时，该采样点的颜色**严禁**融入中心像素，权重直接归零。

定义归一化深度软比较函数：

.. math::

   f_{	ext{depth}}(\mathbf{X}, \mathbf{S}) = 	ext{saturate}\left( \frac{Z(\mathbf{S}) - Z(\mathbf{X})}{\epsilon_z} \right)

定义速度对齐衰减函数：

.. math::

   f_{	ext{velocity}}(\mathbf{S}, \mathbf{X}, \mathbf{d}) = 	ext{saturate}\left( 1.0 - \frac{\|\mathbf{S} - \mathbf{X}\| - \|\mathbf{v}_S\|}{\|\mathbf{v}_S\| + 1e-4} \right)

综合权重 $w(\mathbf{S}_i)$ 为空间距离高斯衰减、深度遮挡因子与速度投影权重的乘积。最终颜色由归一化线积分求和导出：

.. math::

   \mathbf{C}_{	ext{blur}}(\mathbf{X}) = \frac{\sum_{i=0}^{N-1} w(\mathbf{S}_i) \cdot C(\mathbf{S}_i)}{\sum_{i=0}^{N-1} w(\mathbf{S}_i)}

------------------------------------------------------------------------
34.4 参与介质与辐射传输方程 (RTE)
------------------------------------------------------------------------

光线在参与介质中的微观物理交互
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当光束穿过包含微小颗粒（如空气分子、悬浮水滴、尘埃微粒、烟气）的空间介质时，光子不再是在真空中沿直线无损传播，而是与介质微观颗粒发生碰撞交互。辐射度量学将这些交互严格抽象为四种基本物理过程：

.. list-table:: 参与介质四大基础辐射过程微观特性
   :widths: 20 20 30 30
   :header-rows: 1
   :class: tight-table

   * - 辐射物理过程
     - 系数符号与量纲
     - 微观物理机理
     - 对视线辐射亮度的影响
   * - **吸收 (Absorption)**
     - $\sigma_a(\mathbf{x}) \ [	ext{m}^{-1}]$
     - 光子能量转化为介质热能或分子内能
     - 能量损耗：视线光强随传播距离指数衰减
   * - **外散射 (Out-Scattering)**
     - $\sigma_s(\mathbf{x}) \ [	ext{m}^{-1}]$
     - 沿当前视线传播的光子碰撞微粒偏折向其他立体角方向
     - 能量损耗：与吸收共同构成总消光（Extinction）
   * - **发射 (Emission)**
     - $L_e(\mathbf{x}, \vec{\omega}) \ [	ext{W}\cdot	ext{sr}^{-1}\cdot	ext{m}^{-3}]$
     - 介质自身发光（如火焰、高温等离子体、荧光物质）
     - 能量增益：向视线方向直接注入新生光辐射
   * - **内散射 (In-Scattering)**
     - $L_i(\mathbf{x}, \vec{\omega}) \ [	ext{W}\cdot	ext{sr}^{-1}\cdot	ext{m}^{-3}]$
     - 外部光源或环境光碰撞介质后偏折汇入当前视线方向
     - 能量增益：形成明亮可见的体积光柱（God Rays）

.. math::

   \sigma_t(\mathbf{x}) = \sigma_a(\mathbf{x}) + \sigma_s(\mathbf{x}) \quad (	ext{消光系数 Extinction Coefficient})

微粒散射反照率（Scattering Albedo）定义为散射截面占总消光截面的比例：

.. math::

   \alpha(\mathbf{x}) = \frac{\sigma_s(\mathbf{x})}{\sigma_t(\mathbf{x})} \in [0, 1]

比尔-朗伯定律 (Beer-Lambert Law) 与透射率
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在无内散射与自发射的纯消光介质中，光束从位置 $\mathbf{x}_0$ 沿方向 $\vec{\omega}$ 传播至距离 $s$ 处的透射率（Transmittance）$T(s)$ 由一阶常微分方程积分给出：

.. math::

   \frac{dL(s)}{ds} = -\sigma_t(s) \cdot L(s) \quad \Longrightarrow \quad T(s) = \exp\left( -\int_{0}^{s} \sigma_t(\mathbf{x}_0 + t\vec{\omega}) \, dt \right)

在均匀各向同性介质中，透射率退化为简单指数衰减：$T(s) = e^{-\sigma_t s}$。透射率具有严格的相乘可传递性：$T(0 	o s_2) = T(0 	o s_1) \cdot T(s_1 	o s_2)$。

辐射传输方程 (Radiative Transfer Equation - RTE)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
将上述四种微观过程综合，沿光线视线方向 $\vec{\omega}$ 的微分辐射传输方程为：

.. math::

   (\vec{\omega} \cdot 
abla) L(\mathbf{x}, \vec{\omega}) = L_e(\mathbf{x}, \vec{\omega}) + \sigma_s(\mathbf{x}) \int_{4\pi} p(\mathbf{x}, \vec{\omega}', \vec{\omega}) L(\mathbf{x}, \vec{\omega}') \, d\omega' - \sigma_t(\mathbf{x}) L(\mathbf{x}, \vec{\omega})

其中 $p(\mathbf{x}, \vec{\omega}', \vec{\omega})$ 为**散射相位函数（Phase Function）**，描述入射光方向 $\vec{\omega}'$ 碰撞微粒后偏折至出射方向 $\vec{\omega}$ 的立体角概率密度分布。

沿视线光线 $\mathbf{x}(t) = \mathbf{x}_0 + t\vec{\omega}$ 从近截面 $t=0$ 到不透明物体表面 $t=D$ 进行积分，得到体积着色积分形式：

.. math::

   L(\mathbf{x}_0, \vec{\omega}) = T(D) \cdot L_{	ext{surface}}(\mathbf{x}_0 + D\vec{\omega}, \vec{\omega}) + \int_{0}^{D} T(t) \cdot \sigma_s(t) \cdot L_{	ext{in-scatter}}(t, \vec{\omega}) \, dt

该公式清晰揭示了屏幕最终颜色的两部分物理构成：
1. **被介质透射率消减后的不透明表面背景辐射**：$T(D) \cdot L_{	ext{surface}}$；
2. **从相机到物体表面整个视线路径上沿程累加的内散射光子积分**：$\int_0^D T(t) \cdot \sigma_s(t) \cdot L_{	ext{in-scatter}} \, dt$。

------------------------------------------------------------------------
34.5 散射相位函数 (Phase Functions) 微架构解析
------------------------------------------------------------------------

相位函数的能量守恒约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
相位函数 $p(\cos	heta)$（其中 $	heta$ 为入射光线方向 $\vec{\omega}'$ 与出射视线反方向 $-\vec{\omega}$ 之间的夹角）具有球面积分能量守恒约束：

.. math::

   \int_{4\pi} p(\vec{\omega}', \vec{\omega}) \, d\omega = \int_{0}^{2\pi} \int_{0}^{\pi} p(\cos	heta) \sin	heta \, d	heta \, d\phi = 1

当微粒均匀向四周各方向等概率散射时，退化为各向同性相位函数（Isotropic Phase Function）：

.. math::

   p_{	ext{iso}}(\cos	heta) = \frac{1}{4\pi}

瑞利散射 (Rayleigh Scattering)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当介质颗粒的特征物理半径 $r$ 远小于入射光波长 $\lambda$ 时（$r \ll \lambda$，例如地球大气层中的氮气、氧气分子，其尺度约为几纳米，而可见光波长为 $400 \sim 700	ext{ nm}$），发生**瑞利散射**。
瑞利散射强度与光波长四次方成反比（$I \propto 1/\lambda^4$），这也是晴朗天空呈现蔚蓝色、日落呈现猩红色的根本物理原因。

瑞利散射相位函数对前后方向对称：

.. math::

   p_{	ext{Rayleigh}}(\cos	heta) = \frac{3}{16\pi} (1 + \cos^2	heta)

米氏散射与 Henyey-Greenstein (HG) 相位函数
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当介质微粒尺度与光波长相当或大于波长时（$r \gtrsim \lambda$，如雾滴、烟雾尘埃、云层微滴，尺度约为几微米至几十微米），发生**米氏散射（Mie Scattering）**。米氏散射对波长不敏感，且呈现出极其强烈的**前向散射特性（Forward Scattering）**。当观察者直视光源边缘时，介质散射光强骤增数十倍，形成刺眼的光晕。

严格的米氏散射级数求解过于繁琐，工业实时图形学全面采用 **Henyey-Greenstein (HG) 经验近似相位函数**：

.. math::

   p_{	ext{HG}}(\cos	heta, g) = \frac{1}{4\pi} \frac{1 - g^2}{(1 + g^2 - 2g\cos	heta)^{3/2}}

参数 $g \in (-1, 1)$ 为不对称因子（Asymmetry Parameter）：
- $g = 0$：退化为各向同性散射；
- $g > 0$：强烈前向散射（Typical Fog/Haze 通常取 $g \in [0.6, 0.85]$）；
- $g < 0$：后向散射。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Henyey-Greenstein (HG) 相位函数极坐标强度分布            |
   +-------------------------------------------------------------------------+

              入射光方向 -----> [ 微粒 ]
                                  |
                                  |   /---\  (g = 0 各向同性: 完美圆形)
                                  |  /     \
                                  | |       |
                                  |  \     /
                                  |   \---/
                                  |
                                  |    +---------+
                                  |    |          \
                                  |====|           ) (g = 0.7 强烈前向散射叶瓣)
                                  |    |          /
                                  |    +---------+

双瓣 HG 相位函数 (Double-Lobe HG Phase Function)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
真实大气云雾中往往同时包含前向衍射亮晕与小比例的后向回光。为了获得更高拟真度，现代 3A 引擎（如《地平线：零之曙光》Decima 引擎、Frostbite）常采用双瓣加权 HG 相位函数：

.. math::

   p_{	ext{DualHG}}(\cos	heta) = k \cdot p_{	ext{HG}}(\cos	heta, g_1) + (1 - k) \cdot p_{	ext{HG}}(\cos	heta, g_2)

其中 $g_1 > 0$ 控制强烈前向散射叶瓣，$g_2 < 0$ 控制微弱后向反射，$k \in [0.8, 0.95]$ 为前向主导权重。

------------------------------------------------------------------------
34.6 3D 视锥体网格 (Froxel Grid) 体积光管线架构
------------------------------------------------------------------------

经典光线步进 (Raymarching) 及其性能瓶颈
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
早期实现体积光的方法是在全屏像素着色器中，从近平面沿每个像素的视线光线发射一条射线，以固定或抖动步长向深度方向进行步进（Raymarching）：
在每一个步进点采样点对直接光源阴影贴图（Shadow Map）执行深度相交测试，计算内散射量并累加。

*像素级 Raymarching 的致命缺陷*：
- 若全屏 $1920 	imes 1080$ 像素每个像素步进 64 次，单帧需执行超过 **1.32 亿次** 复杂阴影图采样与相位函数计算！
- 显存带宽与 TMU 纹理采样单元彻底饱和，且步长过大时沿几何表面边缘出现严重的木纹走样（Slicing Artifacts）。

Froxel (Frustum Voxel) 视锥体素化微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了将体积光照计算复杂度与屏幕分辨率及几何密度彻底解耦，现代图形架构引入了 **Froxel Grid（视锥体素网格）** 体系：
将相机视锥体沿屏幕横向（X）、纵向（Y）以及相机深度轴（Z）离散化为一个三维对数体素网格。典型分辨率配置为：

.. math::

   N_X 	imes N_Y 	imes N_Z = 160 	imes 90 	imes 64 = 921,600 	ext{ 体素}

相比全屏数千万次步进，仅需对不到 100 万个体素单元执行离散光照求解，计算量降低了整整两个数量级！

对数非线性深度剖分 (Logarithmic Depth Slicing)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
人眼对近处空气微粒的体积层次细节敏感，而远处大景深体素即使尺度放大也难以察觉。因此，Z 轴方向绝对不能采用线性等分，而必须采用**对数指数递增分布**：

设视锥体近平面为 $n$，远平面为 $f$，体素深度切片总数为 $N_Z$。第 $k \in [0, N_Z - 1]$ 个体素切片的边界深度 $z_k$ 定义为：

.. math::

   z_k = n \cdot \left( \frac{f}{n} \right)^{\frac{k}{N_Z}}

逆映射：给定世界空间线性深度 $z_{	ext{view}}$，其对应的 Froxel 深度索引 $k$ 为：

.. math::

   k = \left\lfloor N_Z \cdot \frac{\ln(z_{	ext{view}} / n)}{\ln(f / n)} \right\rfloor

.. code-block:: text

   +-------------------------------------------------------------------------+
   |              Froxel Grid 视锥体素网格五阶段工业渲染流水线               |
   +-------------------------------------------------------------------------+

      [ 阶段 1: 物理参数注入 ]
      (Compute Shader: 将局部雾体、高度指数雾、粒子消光系数写入 3D Texture A)
                |
                v
      [ 阶段 2: 阴影与直接光照散射累加 ]
      (Compute Shader: 采样 Shadow Map、计算 HG 相位函数，写出 In-Scattering 3D Texture B)
                |
                v
      [ 阶段 3: 时域时空滤波 (Temporal Reprojection & Filtering) ]
      (Compute Shader: 结合前一帧 Froxel 历史数据进行 EMA 滤波，压制高频下采样噪波)
                |
                v
      [ 阶段 4: 前向视线积分累加 (Front-to-Back Volume Integration) ]
      (Compute Shader: 沿 Z 轴切片依次扫描，累积比尔-朗伯透射率与散射光，输出终极 3D LUT)
                |
                v
      [ 阶段 5: 全屏后处理合成 (Composite Pass) ]
      (Pixel/Compute Shader: 读取场景深度重构坐标，三线性插值采样 3D LUT，融合至 HDR 画面)

------------------------------------------------------------------------
34.7 工业级 HLSL / Compute Shader 完整工程实现
------------------------------------------------------------------------

以下是符合 DirectX 12 / Vulkan 规范的完整 Froxel 视锥体素光照散射与前向切片体积分计算着色器（HLSL 6.5+）。代码完整实现了 **对数坐标变换、点光源/方向光阴影散射、HG 相位函数、以及沿 Z 轴的数值积分扫描**：

.. code-block:: hlsl

   // =========================================================================
   // File: VolumetricFog_FroxelLighting.hlsl
   // Standard: HLSL 6.5+ (DX12 / Vulkan via DXC)
   // Architecture: High-Performance Froxel-Based Volumetric Lighting & Integration
   // =========================================================================

   struct FroxelGlobalConstants {
       float4x4 InvViewProj;
       float4x4 PrevViewProj;
       
       float3   SunDirection;          // 单位方向 (指向光源)
       float    SunIntensity;          // 太阳辐射照度
       float3   SunColor;
       float    MieAsymmetryG;         // Henyey-Greenstein g 参数 (例如 0.7)
       
       float3   FroxelGridResolution;  // float3(160, 90, 64)
       float    NearPlane;
       
       float3   RcpFroxelResolution;   // 1.0 / FroxelGridResolution
       float    FarPlane;
       
       float    DensityScale;          // 全局介质浓度乘子
       float    GlobalExtinction;      // 全局消光系数 sigma_t
       float    TemporalFeedback;      // 时域累积因子 (例如 0.9)
       float    Padding;
   };

   ConstantBuffer<FroxelGlobalConstants> g_FroxelCB : register(b0);

   Texture3D<float4>   g_PrevFroxelLightHistory : register(t0); // 前一帧散射光 3D 纹理
   Texture2D<float>    g_DirectionalShadowMap   : register(t1); // 方向光阴影贴图
   SamplerState        g_LinearClampSampler     : register(s0);
   SamplerComparisonState g_ShadowSampler       : register(s1);

   RWTexture3D<float4> g_RWInScatteringTexture  : register(u0); // 本阶段写出: RGB=散射光, A=消光

   // =========================================================================
   // 坐标系统转换辅助函数
   // =========================================================================
   float FroxelSliceToLinearDepth(float sliceZ, float N_z, float n, float f) {
       // 对数深度还原: z = n * (f / n) ^ (slice / N_z)
       return n * pow(max(f / n, 1e-4f), sliceZ / N_z);
   }

   float3 FroxelCoordToWorldPos(uint3 froxelID) {
       float2 uv = (float2(froxelID.xy) + 0.5f) * g_FroxelCB.RcpFroxelResolution.xy;
       float linearDepth = FroxelSliceToLinearDepth(float(froxelID.z) + 0.5f, 
                                                   g_FroxelCB.FroxelGridResolution.z, 
                                                   g_FroxelCB.NearPlane, 
                                                   g_FroxelCB.FarPlane);

       // 还原为 NDC 坐标 (逆 Z 规范)
       float2 ndcXY = uv * float2(2.0f, -2.0f) + float2(-1.0f, 1.0f);
       
       // 投影重构世界空间视线射线
       float4 clipPos = float4(ndcXY, 1.0f, 1.0f);
       float4 viewRay = mul(g_FroxelCB.InvViewProj, clipPos);
       viewRay /= viewRay.w;

       // 根据线性深度缩放世界空间位置
       return viewRay.xyz * (linearDepth / g_FroxelCB.FarPlane);
   }

   // Henyey-Greenstein 相位函数
   float EvaluateHenyeyGreenstein(float cosTheta, float g) {
       float g2 = g * g;
       float denom = 1.0f + g2 - 2.0f * g * cosTheta;
       return (1.0f / (4.0f * 3.14159265f)) * ((1.0f - g2) / max(pow(denom, 1.5f), 1e-5f));
   }

   // =========================================================================
   // Pass 1: Froxel 直接光散射与消光注入 (8x8x1 线程组)
   // =========================================================================
   [numthreads(8, 8, 1)]
   void CS_FroxelDirectLightInjection(uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       uint3 froxelID = dispatchThreadID;
       if (any(froxelID >= (uint3)g_FroxelCB.FroxelGridResolution)) return;

       float3 worldPos = FroxelCoordToWorldPos(froxelID);

       // 基础高度指数雾浓度模型: rho(h) = rho_0 * exp(-h / H)
       float height = worldPos.y;
       float fogDensity = g_FroxelCB.DensityScale * exp(-max(height, 0.0f) * 0.05f);
       
       float sigma_s = fogDensity * 0.8f;                     // 散射系数
       float sigma_t = fogDensity * g_FroxelCB.GlobalExtinction; // 消光系数

       // 计算视线方向与太阳光夹角余弦
       float3 viewDir = normalize(worldPos); // 相机在原点
       float cosTheta = dot(viewDir, -g_FroxelCB.SunDirection);

       // 计算 HG 相位函数
       float phase = EvaluateHenyeyGreenstein(cosTheta, g_FroxelCB.MieAsymmetryG);

       // 阴影贴图能见度采样 (Visibility)
       // 此处为简化演示，假定投影变换与深度比较已封装
       float shadowFactor = 1.0f; // 实际引擎中执行带有 PCF 滤波的阴影贴图采样

       // 内散射光注入: InScatter = Li * sigma_s * Phase * Shadow
       float3 inScattering = g_FroxelCB.SunColor * (g_FroxelCB.SunIntensity * shadowFactor * sigma_s * phase);

       // 写出到 3D 累加纹理 (RGB: 散射能量, A: 消光系数)
       g_RWInScatteringTexture[froxelID] = float4(inScattering, sigma_t);
   }

   // =========================================================================
   // Pass 2: 沿视线方向前向体积分扫描 (Front-to-Back Volume Integration)
   // 每个线程处理屏幕 (X, Y) 对应的一条完整 Z 轴光线列 (16x16 线程覆盖全屏幕)
   // =========================================================================
   RWTexture3D<float4> g_RWIntegratedVolumeLUT : register(u1); // 最终合成 LUT: RGB=累积光, A=透射率

   [numthreads(16, 16, 1)]
   void CS_FroxelFrontToBackIntegration(uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       uint2 rayXY = dispatchThreadID.xy;
       if (rayXY.x >= (uint)g_FroxelCB.FroxelGridResolution.x || 
           rayXY.y >= (uint)g_FroxelCB.FroxelGridResolution.y) return;

       float3 accumulatedScattering = float3(0.0f, 0.0f, 0.0f);
       float  accumulatedTransmittance = 1.0f;

       float prevZ = g_FroxelCB.NearPlane;
       uint  numSlicesZ = (uint)g_FroxelCB.FroxelGridResolution.z;

       // 沿对数 Z 轴切片从前向后递推积分
       for (uint z = 0; z < numSlicesZ; ++z) {
           uint3 cellCoord = uint3(rayXY, z);
           float4 inScatterAndExtinction = g_RWInScatteringTexture[cellCoord];

           float3 sliceScattering = inScatterAndExtinction.rgb;
           float  sliceExtinction = inScatterAndExtinction.a;

           // 计算当前切片沿光线轴向的几何厚度 Delta D
           float currZ = FroxelSliceToLinearDepth(float(z + 1), float(numSlicesZ), 
                                                 g_FroxelCB.NearPlane, g_FroxelCB.FarPlane);
           float stepLength = max(currZ - prevZ, 0.001f);
           prevZ = currZ;

           // 比尔-朗伯定律计算切片透射率
           float sliceTransmittance = exp(-sliceExtinction * stepLength);

           // 梯形或能量守恒积分切片散射增量:
           // S_integrated = InScatter * (1 - Transmittance) / Extinction
           float3 sliceScatteringIntegrated = (sliceExtinction > 1e-5f) ?
               (sliceScattering * (1.0f - sliceTransmittance) / sliceExtinction) :
               (sliceScattering * stepLength);

           // 累积到总前向能量中
           accumulatedScattering += sliceScatteringIntegrated * accumulatedTransmittance;
           accumulatedTransmittance *= sliceTransmittance;

           // 将当前体素深度上的前向体积分结果写入 3D LUT
           // RGB: 视线到当前深度累加的雾气光强; A: 视线到当前深度的剩余透射率 T
           g_RWIntegratedVolumeLUT[cellCoord] = float4(accumulatedScattering, accumulatedTransmittance);
       }
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了实时渲染后处理与环境大气模拟中的两项核心支柱——时空连续运动模糊与体积光散射体系：
1. **物理快门光学模型**：推导了电影级快门开角方程，阐明了时域离散光栅化抽样导致频闪与阶跃走样的物理成因，确立了运动模糊作为时域时间积分恢复算子的数学地位；
2. **速度缓冲区与 Tile-Max 架构**：深入解析了相机全局背景位移与动态蒙皮角色自位移的双轨运动矢量编码，详尽推导了 McGuire Tile-Max / Neighbor-Max 空间速度分块膨胀算法，彻底解决了前景模糊外溢与背景边界色彩渗漏的经典冲突；
3. **参与介质与辐射传输理论**：建立了吸收、外散射、发射与内散射四大基础物理过程方程，严格推导了比尔-朗伯指数衰减定律以及微积分形式的辐射传输方程（RTE）；
4. **微观散射相位函数**：推导了球面积分能量守恒约束，对比了波长四次方反比的瑞利散射与雾霾水汽前向主导的米氏散射，详解了单瓣与双瓣 Henyey-Greenstein（HG）不对称参数化叶瓣函数的几何实现；
5. **3D Froxel 体积光架构**：剖析了传统全屏 Raymarching 的算力雪崩瓶颈，构建了对数非线性深度剖分的 3D 视锥体素网格（Froxel Grid），给出了直接光散射注入与前向递推体积分扫描的工业级 Compute Shader 完整实现。

在下一章（Chapter 35）中，我们将迎来第七模块的收官之作——**超分辨率与神经图像重构 (Super Resolution: DLSS, FSR 2/3 and XeSS)**。我们将深入剖析现代 3A 引擎如何在 1080p 极低开销下重构出超清 4K 画质，全面解构时间性特征重投影、空间双边插值、卷积神经网络与光流加速引擎（OFA）的底层微架构，敬请期待！
