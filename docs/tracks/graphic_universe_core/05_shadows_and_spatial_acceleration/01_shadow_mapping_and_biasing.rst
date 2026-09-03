========================================================================
Chapter 21: 阴影映射核心原理与瑕疵消除：Shadow Map、自阴影粉刺与斜率偏差
========================================================================

.. note:: 前置背景与认知承接
   前一章系统解构了基于物理的渲染（PBR）工业级材质表示标准——Disney Principled BRDF 架构哲学、次表面散射（BSSRDF）从偶极子扩散到屏幕空间 SSSS 的演进，以及各向异性、清漆层与织物光泽的多层复合材质体系。在完成了光照计算中反射率与微表面分布的建模后，光照积分方程中另一个决定真实感的关键物理项是**几何可见性因子（Visibility Factor, $V(\mathbf{x}, \mathbf{l}) \in \{0, 1\}$）**——即空间中两点之间是否存在遮挡物形成阴影。阴影不仅提供了场景物体的空间接触感与遮蔽层次，更是人眼大脑感知 3D 深度与空间尺度的核心视觉线索。本章将系统解构两阶段阴影映射（Two-Pass Shadow Mapping）的数学几何流转、光栅化离散采样引发的自阴影粉刺（Shadow Acne）与 Peter Panning 悬浮现象的物理根源、常量偏差的几何缺陷、斜率比例深度偏差（Slope-Scaled Depth Bias）与硬件光栅化器实现，以及基于法线偏移（Normal Offset Bias）的工业级无瑕疵硬阴影构建方案。

------------------------------------------------------------------------
21.1 实时阴影的物理本质与两阶段阴影映射 (Two-Pass Shadow Mapping)
------------------------------------------------------------------------

在辐射传输理论中，点 $\mathbf{x}$ 处接收到的直接光照辐射度必须受到光线可见性函数 $V(\mathbf{x}, \mathbf{l})$ 的调制：

.. math::

   L_o(\mathbf{x}, \omega_o) = L_e(\mathbf{x}, \omega_o) + \int_{\Omega} f_r(\mathbf{x}, \omega_i, \omega_o) \cdot L_i(\mathbf{x}, \omega_i) \cdot V(\mathbf{x}, \omega_i) \cdot (\mathbf{n} \cdot \omega_i) \, d\omega_i

其中 $V(\mathbf{x}, \omega_i)$ 是一个二值函数：若从表面点 $\mathbf{x}$ 沿入射方向 $\omega_i$ 能够无遮挡直达光源，则 $V = 1$；若中途与任何不透明几何体相交，则 $V = 0$（处于本影区）。

两阶段阴影映射 (Shadow Mapping) 架构数据流
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1978 年，Lance Williams 提出了基于深度缓冲区的阴影映射算法（Shadow Mapping）。该算法将可见性测试问题转化为**从光源视点观察场景的可见深度比较**，通过两个完全解耦的渲染通道（Render Passes）实现：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     两阶段阴影映射 (Two-Pass Shadow Mapping) 流水线     |
   +-------------------------------------------------------------------------+

   [ Pass 1: 光源深度通道 (Shadow Pass / Depth-Only Pass) ]
   * 视点: 放置于光源位置 (定向光采用正交投影, 点光源/聚光灯采用透视投影)
   * 变换: 顶点经 M_light_view 与 M_light_proj 变换至光源裁剪空间
   * 输出: 仅写入深度附件 (Depth Attachment), 强制禁用颜色写入 (Color Write Disabled)
   * 产物: 场景在光源视点下的最近表面物理深度纹理 —— **Shadow Map (D_light)**
        |
        v (将 Shadow Map 绑定至主摄像机着色器资源槽位)
        |
   [ Pass 2: 主摄像机着色通道 (Camera Shading Pass) ]
   * 视点: 主摄像机观察视角 (Camera View)
   * 计算: 针对主视口中的每一个待着色片段 (Fragment):
        1. 提取当前片段的世界坐标 P_ws;
        2. 将 P_ws 投影至光源裁剪空间: P_light_clip = M_light_proj * M_light_view * P_ws;
        3. 执行透视除法与 UV 归一化: 得到光源屏幕坐标 (u_light, v_light) 及深度 z_current;
        4. 采样 Shadow Map: 读取光源记录的最近深度 z_shadow = Sample(D_light, u_light, v_light);
        5. 深度比较判定:
             if (z_current <= z_shadow) -> V = 1.0 (未被遮挡, 正常着色)
             else                       -> V = 0.0 (被前排遮挡物遮蔽, 仅计算环境光)

光源空间坐标投影变换数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设片段的世界坐标为齐次向量 $\mathbf{P}_{	ext{ws}} = [x_w, y_w, z_w, 1]^T$。光源的视图矩阵为 $\mathbf{V}_{	ext{light}}$，投影矩阵为 $\mathbf{P}_{	ext{light}}$。

1. **光源裁剪空间坐标计算**：

.. math::

   \mathbf{P}_{	ext{clip}} = \mathbf{P}_{	ext{light}} \cdot \mathbf{V}_{	ext{light}} \cdot \mathbf{P}_{	ext{ws}} = \begin{bmatrix} x_c \ y_c \ z_c \ w_c \end{bmatrix}

2. **透视除法（Perspective Division）** 得到标准化设备坐标（NDC）：

.. math::

   \mathbf{P}_{	ext{ndc}} = \begin{bmatrix} x_{	ext{ndc}} \ y_{	ext{ndc}} \ z_{	ext{ndc}} \end{bmatrix} = \begin{bmatrix} x_c / w_c \ y_c / w_c \ z_c / w_c \end{bmatrix}

3. **视口与深度范围重映射（NDC 到 纹理坐标 UV 及深度 $[0, 1]$）**：
   在 Direct3D 12、Vulkan 与 Metal 中，NDC 空间的坐标范围为 $x, y \in [-1, 1], z \in [0, 1]$，而纹理采样坐标需要 $u, v \in [0, 1]$ 且 $Y$ 轴翻转。通过引入尺度平移变换矩阵 $\mathbf{T}_{	ext{bias}}$：

.. math::

   \mathbf{T}_{	ext{bias}} = \begin{bmatrix} 0.5 & 0 & 0 & 0.5 \ 0 & -0.5 & 0 & 0.5 \ 0 & 0 & 1 & 0 \ 0 & 0 & 0 & 1 \end{bmatrix}, \quad
   \begin{bmatrix} u_{	ext{shadow}} \ v_{	ext{shadow}} \ z_{	ext{current}} \ 1 \end{bmatrix} = \mathbf{T}_{	ext{bias}} \cdot \mathbf{P}_{	ext{ndc}}

最终，片段在光源空间的比较深度即为 $z_{	ext{current}}$，采样的纹理坐标即为 $(u_{	ext{shadow}}, v_{	ext{shadow}})$。

------------------------------------------------------------------------
21.2 采样离散化与自阴影粉刺 (Shadow Acne) 的物理根源
------------------------------------------------------------------------

在理论连续数学模型下，$z_{	ext{current}} \le z_{	ext{shadow}}$ 的判定是完美的。但在数字计算机与 GPU 硬件实现中，Shadow Map 是由**有限分辨率的离散像素网格（Texels）**构成的二维数组。这种离散化采样带来了实时图形学中最著名的走样瑕疵——**自阴影粉刺（Shadow Acne，又称阴影斑马纹）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |              离散深度阶梯与连续倾斜几何表面引发的 Shadow Acne           |
   +-------------------------------------------------------------------------+

   光线方向 L
      \   \   \   \
       \   \   \   \
        v   v   v   v
   ==================== [ Shadow Map 离散记录的深度: 水平阶梯常量 z_shadow ]
        |   |   |   |
      +---+---+---+---+
      | z0| z1| z2| z3|  (每个 Texel 内部深度值恒定为中心点采样值)
      +---+---+---+---+
        |   |   |   |
   ......\...\...\...\......................................................
          \   \   \   \   连续倾斜几何多边形表面 (Continuous Surface)
           \   \   \   \
            \   \   \   \
             +---+---+---+
             |黑 |亮 |黑 |  <-- 致命后果:
             +---+---+---+      前半段像素: z_current > z_shadow -> 错误判定为阴影(黑)!
                                后半段像素: z_current <= z_shadow -> 判定为照亮(亮)!
                                整个平整表面布满明暗交替的条纹与噪点 (Shadow Acne)!

Acne 严重程度与法线倾角的数学因果关系
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设多边形表面的单位法线为 $\mathbf{n}$，光源入射方向单位向量为 $\mathbf{l}$，二者夹角为 $	heta$（即 $\mathbf{n} \cdot \mathbf{l} = \cos	heta$）。
当光线垂直照射表面时（$	heta = 0, \cos	heta = 1$），多边形平面与 Shadow Map 的投影平面平行，单个 Texel 跨越的几何深度变化率 $\frac{\partial z}{\partial x} \approx 0$，Acne 极弱。

当光线以大掠射角照射表面时（$	heta 	o \frac{\pi}{2}, \cos	heta 	o 0$），几何表面相对于光源视线发生极度倾斜。单个 Shadow Map 纹素在空间多边形上覆盖的深度跨度（Depth Span, $\Delta z$）急剧放大：

.. math::

   \Delta z = 	ext{TexelSize}_{	ext{world}} \cdot 	an	heta = 	ext{TexelSize}_{	ext{world}} \cdot \frac{\sin	heta}{\cos	heta} = 	ext{TexelSize}_{	ext{world}} \cdot \sqrt{\frac{1 - (\mathbf{n} \cdot \mathbf{l})^2}{(\mathbf{n} \cdot \mathbf{l})^2}}

由于单个 Texel 只能存储单一深度标量，倾斜表面在单个 Texel 覆盖区域内，深度差可能高达数十个深度量化单位，导致大面积像素深度严重超过记录值，产生大面积剧烈的黑斑粉刺。

------------------------------------------------------------------------
21.3 常量深度偏差 (Constant Bias) 与 Peter Panning 悬浮现象
------------------------------------------------------------------------

为了消除自阴影粉刺，最直观的工程修正是在深度比较时引入一个人为的向下偏移容限——**常量深度偏差（Constant Depth Bias, $b_{	ext{const}}$）**：

.. math::

   V(\mathbf{x}) = \begin{cases} 1.0, & 	ext{if } (z_{	ext{current}} - b_{	ext{const}}) \le z_{	ext{shadow}} \ 0.0, & 	ext{otherwise} \end{cases}

常量偏差的致命困境：Acne 与 Peter Panning 的两难博弈
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

常量偏差试图用单一固定数值去对抗全场景不同朝向、不同倾角的多边形深度误差，这在几何上必然引发两难崩溃：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |              常量 Bias 引起的 Peter Panning (物体脱地悬浮) 瑕疵         |
   +-------------------------------------------------------------------------+

   [ 场景 1: Bias 设置过小 (b = 0.0005) ]
   * 平坦受光面正常;
   * 大倾角掠射面 (Sloped Surfaces): 深度误差 Delta_z > b，**依然爆发严重 Shadow Acne**!

   [ 场景 2: 强行增大 Bias 以掩盖大倾角 Acne (b = 0.01) ]
   * 掠射面的粉刺被压制;
   * 物体根部与地面接触面 (Contact Region):
     由于人为将比较深度拔高了 0.01，本应处于遮挡状态的接触点被错误判定为未遮挡!
     -> **阴影被硬生生向后推移数米，与物体脚跟完全脱节分离 (Peter Panning)**!
     -> 视觉心理学感知: 沉重的石头、建筑物瞬间如同悬浮漂在空中 (Floatation Artifact)!

.. list-table:: 常量深度偏差取值与视觉瑕疵对照
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 偏差取值策略
     - 平坦受光面表现
     - 掠射大倾角表面表现
     - 物体接触面根部表现
   * - **零偏差 ($b = 0$)**
     - 轻微浮点与网格噪点
     - **极重度 Acne 斑马纹爆发**
     - 阴影紧贴根部，接触良好
   * - **小常量偏差 ($b = 0.001$)**
     - 干净清晰
     - **中重度 Acne 残留**
     - 接触处基本真实
   * - **大常量偏差 ($b = 0.02$)**
     - 干净
     - Acne 彻底消失
     - **严重 Peter Panning 悬浮，阴影脱离地面**

------------------------------------------------------------------------
21.4 斜率比例深度偏差 (Slope-Scaled Depth Bias) 与自适应微架构
------------------------------------------------------------------------

为了彻底打破常量偏差的两难困境，现代图形学引入了根据表面几何倾斜程度动态调整偏差的机制——**斜率比例深度偏差（Slope-Scaled Depth Bias）**。

斜率比例深度偏差的数学模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据前文推导，表面深度误差正比于切向斜率 $	an	heta = \frac{\sqrt{1 - (\mathbf{n}\cdot\mathbf{l})^2}}{\mathbf{n}\cdot\mathbf{l}}$。自适应总深度偏差 $b_{	ext{total}}$ 表达为**基础常量偏差**与**斜率放大项**的线性加权：

.. math::

   b_{	ext{total}} = b_{	ext{const}} + b_{	ext{slope}} \cdot 	ext{SlopeFactor}

其中斜率因子 $	ext{SlopeFactor}$ 定义为表面在屏幕或光源空间的偏导数斜率模长：

.. math::

   	ext{SlopeFactor} = \max\left( \left| \frac{\partial z}{\partial x} \right|, \left| \frac{\partial z}{\partial y} \right| \right) = 	an	heta = \frac{\sqrt{1 - (\mathbf{n} \cdot \mathbf{l})^2}}{\max(\mathbf{n} \cdot \mathbf{l}, \epsilon)}

- **垂直受光面（$\mathbf{n} \cdot \mathbf{l} 	o 1$）**：$	ext{SlopeFactor} 	o 0$，$b_{	ext{total}} \approx b_{	ext{const}}$（维持极小的微小偏差，严格杜绝 Peter Panning）；
- **大掠射角倾斜面（$\mathbf{n} \cdot \mathbf{l} 	o 0$）**：$	ext{SlopeFactor}$ 自动自适应激增，提供数倍乃至数十倍的深度缓冲容限，将大倾角 Acne 彻底抚平。

GPU 硬件光栅化器级别的 Slope-Scaled Bias 支持
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 Pass 1（生成 Shadow Map）阶段，现代 GPU 硬件光栅化器（Hardware Rasterizer）内置了硬件级的深度偏差电路，允许在片段写入深度缓冲前，由光栅化器自动计算三角形图元的平面方程偏导数并注入 Bias：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |              Direct3D 12 与 Vulkan 硬件光栅化器深度偏差配置             |
   +-------------------------------------------------------------------------+

   [ Direct3D 12: D3D12_RASTERIZER_DESC ]
   D3D12_RASTERIZER_DESC rasterizerDesc = {};
   rasterizerDesc.DepthBias = 100;                 // 常量偏差 (乘以当前深度格式最小可表示精度)
   rasterizerDesc.DepthBiasClamp = 0.0f;           // 最大偏差夹紧上限 (防止无限膨胀)
   rasterizerDesc.SlopeScaledDepthBias = 1.5f;     // 斜率比例系数 (硬件自动乘以 MaxSlope)

   [ Vulkan: VkPipelineRasterizationStateCreateInfo ]
   VkPipelineRasterizationStateCreateInfo rasterState = {};
   rasterState.depthBiasEnable = VK_TRUE;
   rasterState.depthBiasConstantFactor = 1.25f;    // 对应常量项
   rasterState.depthBiasClamp = 0.0f;
   rasterState.depthBiasSlopeFactor = 1.75f;       // 对应斜率项

硬件光栅化器在三角形装配时，通过顶点属性求解出平面方程 $z = Ax + By + C$，直接获得 $\frac{\partial z}{\partial x} = A, \frac{\partial z}{\partial y} = B$，在片段光栅化写入时执行：

.. math::

   z_{	ext{written}} = z_{	ext{interpolated}} + 	ext{depthBiasConstantFactor} \cdot r + 	ext{depthBiasSlopeFactor} \cdot \max(|A|, |B|)

其中 $r$ 为该深度缓冲区格式（如 `D32_FLOAT` 或 `D24_UNORM`）在当前范围内的最小可分辨精度（ULP - Unit in the Last Place）。

------------------------------------------------------------------------
21.5 法线偏移偏差 (Normal Offset Bias) 与背面渲染策略
------------------------------------------------------------------------

虽然斜率比例偏差显著缓解了 Acne，但在极度锐利的曲率边缘（如圆柱体掠射边缘），单纯沿深度轴向的偏移依然可能在接触阴影处产生轻微撕裂。为此，工业界发展出了两项极其关键的几何级解决方案：

法线偏移偏差 (Normal Offset Bias) 几何原理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由 Nicholas Halle 提出的**法线偏移偏差（Normal Offset Bias）** 改变了思路：**与其在着色深度 $z$ 上做减法，不如将片段的采样坐标沿表面法线方向向外微移一小段物理距离**！

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                 法线偏移偏差 (Normal Offset Bias) 几何向量推导          |
   +-------------------------------------------------------------------------+

   光线入射方向 L
        \   \   \
         \   \   \
          v   v   v
                 / 法线方向 N
                /
               /
        [ 原始世界坐标 P_ws ] -------> 沿法线偏移向量 offset = N * (TexelWorldSize * sin_theta)
               \                         |
                \                        v
                 \---------------- [ 偏移后的采样坐标 P_biased ]
                                         |
                                         +---> 使用 P_biased 投影变换计算光源空间 UV 进行采样!
                                         * 物理奇效:
                                           1. 采样点被物理抬离了表面网格微观阶梯，彻底根除 Acne!
                                           2. 在接触面 (Contact Point) 处法线方向与光线反向，
                                              投影至深度轴的位移天然衰减为 0，**完全不产生 Peter Panning**!

法线偏移量数学计算公式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. math::

   \mathbf{P}_{	ext{biased}} = \mathbf{P}_{	ext{ws}} + \mathbf{n} \cdot \delta_{	ext{normal}} \cdot 	ext{TexelWorldSize} \cdot \sqrt{1 - (\mathbf{n} \cdot \mathbf{l})^2}

其中 $	ext{TexelWorldSize} = \frac{2 \cdot 	ext{FrustumSize}}{	ext{ShadowMapResolution}}$ 为单个阴影纹素在世界空间覆盖的物理米数，$\delta_{	ext{normal}}$ 为调节系数（通常取 $1.0 \sim 2.0$）。该公式在垂直受光面（$\sin	heta = 0$）偏移量自动降为 0，在掠射大角面（$\sin	heta 	o 1$）提供恰好覆盖一个 Texel 几何宽度的法线支撑位移。

背面阴影投射策略 (Rendering Back Faces for Shadows) 与局限性
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

另一种经典思路是在 Pass 1（绘制 Shadow Map）时，将光栅化器的剔除模式由背面剔除（Cull Back）改为**正面剔除（Cull Front）**——即 Shadow Map 中只记录物体的背面深度。

.. list-table:: 阴影通道正面剔除与背面剔除策略全景对比
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 阴影投射剔除策略
     - Acne 抑制原理
     - Peter Panning 表现
     - 致命缺陷与适用边界
   * - **常规背面剔除 (Cull Back)**
     - 记录正面最近深度；依赖 Bias 压制 Acne
     - 若 Bias 不当易发生悬浮
     - 适用所有网格（含双面、单面叶片与薄壳）
   * - **正面剔除 (Cull Front - 渲染背面)**
     - 记录背面深度，正面自然远小于背面深度，**正面 Acne 天然清零**
     - 极佳，几乎无悬浮感
     - **仅对完全封闭的水密实体（Watertight Meshes）有效**；对于薄墙、单面多边形（树叶、草地、头发）会导致阴影彻底漏光穿透！

------------------------------------------------------------------------
21.6 工业级 HLSL 阴影采样与自适应偏差完整实现
------------------------------------------------------------------------

以下给出工业级渲染管线中结合了 **Normal Offset Bias**、**Slope-Scaled Depth Bias** 与硬件级比较采样器（`SamplerComparisonState`）的完整 HLSL 实现：

.. code-block:: hlsl

   // HLSL: 工业级 Shadow Map 采样与自适应偏差复合解算器
   // 特性: Normal Offset Bias + Slope-Scaled Depth Bias + Hardware PCF 比较采样

   Texture2D<float> g_ShadowMap : register(t0);
   SamplerComparisonState g_ShadowSamplerComp : register(s0); // 硬件级 LESS_EQUAL 比较采样器

   cbuffer ShadowData : register(b1) {
       float4x4 g_LightViewProj;          // 光源视图投影矩阵
       float4   g_ShadowMapResolution;    // (width, height, 1/width, 1/height)
       float    g_LightFrustumWorldWidth; // 光源视锥体世界空间宽度 (米)
       float    g_ConstantBias;           // 基础常量偏差 (如 0.0005)
       float    g_SlopeScaledBias;        // 斜率比例系数 (如 1.5)
       float    g_NormalOffsetFactor;     // 法线偏移系数 (如 1.2)
   };

   // 核心阴影计算函数: 输入片段世界坐标与法线，输出遮挡因子 [0.0 = 全黑阴影, 1.0 = 完全照亮]
   float CalculateShadowFactor(float3 positionWS, float3 normalWS, float3 lightDirWS) {
       float NdotL = dot(normalWS, lightDirWS);
       
       // 1. 若表面完全背对光源 (N·L <= 0)，直接判定为处于本影区 (0.0)，规避无效采样开销
       if (NdotL <= 0.0f) {
           return 0.0f;
       }

       // 2. 计算法线偏移偏差 (Normal Offset Bias)
       // 计算单 Texel 在世界空间中的物理米数
       float texelSizeWorld = g_LightFrustumWorldWidth * g_ShadowMapResolution.z;
       // sin(theta) = sqrt(1 - cos^2(theta))
       float sinTheta = sqrt(saturate(1.0f - NdotL * NdotL));
       float normalOffsetDist = g_NormalOffsetFactor * texelSizeWorld * sinTheta;
       
       // 得到沿法线微移后的几何世界坐标
       float3 biasedPositionWS = positionWS + normalWS * normalOffsetDist;

       // 3. 将微移后的世界坐标投影至光源裁剪空间
       float4 lightClipPos = mul(g_LightViewProj, float4(biasedPositionWS, 1.0f));
       
       // 4. 透视除法得到 NDC 坐标 [-1, 1]
       float3 lightNDC = lightClipPos.xyz / lightClipPos.w;

       // 5. 坐标重映射至纹理 UV [0, 1] 与比较深度 (针对 D3D/Vulkan [0, 1] 深度规范)
       float2 shadowUV = float2(lightNDC.x * 0.5f + 0.5f, -lightNDC.y * 0.5f + 0.5f);
       float currentDepth = lightNDC.z;

       // 视锥体越界边界检测: 若超出光源视锥体范围，视作未被阴影覆盖
       if (shadowUV.x < 0.0f || shadowUV.x > 1.0f || 
           shadowUV.y < 0.0f || shadowUV.y > 1.0f || 
           currentDepth > 1.0f) {
           return 1.0f;
       }

       // 6. 计算斜率比例深度偏差 (Slope-Scaled Depth Bias)
       // tan(theta) = sin(theta) / cos(theta)
       float slopeFactor = sinTheta / max(NdotL, 0.001f);
       float totalDepthBias = g_ConstantBias + g_SlopeScaledBias * slopeFactor * g_ShadowMapResolution.z;

       // 应用深度偏差: 将待比较深度人为稍微减小
       float biasedCompareDepth = currentDepth - totalDepthBias;

       // 7. 调用 GPU 硬件级比较采样器执行单次采样或 PCF 硬件过滤
       // SampleCmpLevelZero 在硬件级别自动完成 (D_texel <= biasedCompareDepth) 的比较判定，
       // 并利用双线性插值单元输出平滑的 0.0 ~ 1.0 覆盖率!
       float shadowFactor = g_ShadowMap.SampleCmpLevelZero(
           g_ShadowSamplerComp,
           shadowUV,
           biasedCompareDepth
       );

       return shadowFactor;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从辐射传输可见性项出发，深入推导了两阶段阴影映射（Two-Pass Shadow Mapping）的数学变换与数据流拓扑，揭示了离散网格采样导致自阴影粉刺（Shadow Acne）的几何成因，剖析了常量偏差引发 Peter Panning 物体悬浮的两难困境，系统建立了斜率比例深度偏差（Slope-Scaled Bias）与硬件光栅化器集成模型，并给出了基于法线偏移偏差（Normal Offset Bias）的工业级无瑕疵硬阴影求解闭环。

然而，标准 Shadow Map 采用单一正交/透视投影矩阵覆盖整个场景。在开放世界大场景中，相机近处的微小地表与数公里外的远景山脉共用同一张贴图，导致**近景阴影边缘严重马赛克锯齿化（透视走样 Perspective Aliasing）**。下一章我们将进入大型渲染管线的核心骨干技术——**级联阴影贴图 (CSM - Cascaded Shadow Maps)：视锥体对数分割、视口像素稳定对齐与级联边界平滑过渡**，深入解构现代引擎如何将视锥体剖分为多个层级以实现近景毫米级锐利、远景全覆盖的工业级阴影系统。
