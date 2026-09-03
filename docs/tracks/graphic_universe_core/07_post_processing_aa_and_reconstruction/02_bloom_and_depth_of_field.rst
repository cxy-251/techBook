========================================================================
Chapter 32: 泛光与景深模拟：物理 Bloom (Dual-Kawase 降采样)、Circle of Confusion 景深
========================================================================

.. note:: 前置背景与认知承接
   在前一章（Chapter 31）中，我们系统建立了从场景参照（Scene-Referred）无限浮点辐射度空间到显示参照（Display-Referred）有界输出的色彩与亮度转译体系，确立了物理曝光控制与 ACES / Filmic 色调映射算子的数学本质。然而，真实世界中的光学成像系统（无论是人类眼球还是摄影机镜头）并非理想针孔模型（Pinhole Model），不可避免地存在透镜介质散射、孔径衍射以及有限景深带来的离焦模糊。

   如果渲染流水线直接对高光执行色调映射并输出锐利边缘，画面会呈现出冰冷的人工计算机生成感（CGI Look）。为了还原真实光学系统的物理质感与视觉感知，后处理流水线必须在 **色调映射压缩之前** 介入两项关键的光学拟真阶段：
   
   1. **物理泛光 (Bloom)**：模拟强光穿过眼球角膜、晶状体或相机复合透镜组时的微观杂质散射与衍射现象，使超过显示器白点的超亮光源能量向周围像素扩散，形成柔和光晕；
   2. **景深 (Depth of Field - DoF)**：基于几何光学中的薄透镜成像方程，计算透镜孔径对非对焦平面物体造成的离焦弥散圆（Circle of Confusion - CoC），并在屏幕空间重建真实的圆形、六边形或多边形光学散景（Bokeh）。

   本章将系统解构 **物理泛光提取与 Dual-Kawase / 13-Tap 降采样滤波金字塔微架构、薄透镜成像模型与 CoC 精确解析推导、前后景分离散景滤波与近景遮挡防渗漏算法，以及面向现代 GPU 显存带宽优化的 Compute Shader 完整实战**。

------------------------------------------------------------------------
32.1 物理泛光 (Bloom) 的光学机理与高光提取阈值曲线
------------------------------------------------------------------------

物理 Bloom 的本质是光学系统中的 **透镜内散射 (Intraocular / Lens Scattering)** 与 **孔径衍射 (Aperture Diffraction)**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     物理泛光与景深在后处理流水线中的拓扑定位            |
   +-------------------------------------------------------------------------+

      [ 场景 HDR 渲染目标 (Scene-Referred Linear, RGBA16F) ]
                    |
                    +-----------------------+
                    |                       |
                    v                       v
      [ 物理 Bloom 提取 Pass ]     [ 景深 CoC 计算与 Tile-Max 预处理 ]
      (Soft-Knee 阈值过滤)         (Thin-Lens 几何光学推导)
                    |                       |
                    v                       v
      [ Dual-Kawase 降采样金字塔 ]  [ 前后景分离散景模糊 (Bokeh Blur) ]
      (1/2 -> 1/4 -> ... -> 1/64)  (Half-Res Poisson / Separable Bokeh)
                    |                       |
                    v                       v
      [ 升采样 Tent 滤波逐级累加 ]  [ 深度感知边缘重构与 Alpha 合成 ]
                    |                       |
                    +-----------+-----------+
                                | (光晕能量注入 + 景深模糊图像)
                                v
      [ 自动曝光补偿与色调映射 (ACES / Filmic Tone Mapping) ]
                                |
                                v
      [ Display-Referred SDR/HDR Swapchain Present ]

为什么 Bloom 必须在 Tone Mapping 之前执行？
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **能量线性守恒**：在 HDR 场景参照空间中，高光物体（如灯丝、太阳、金属强高光）的辐射亮度可以达到 $10.0 \sim 1000.0$，其向周围散射的光子能量与光源真实强度成正比。若在 Tone Mapping 将高光压缩至 $[0, 1]$ 之后再执行 Bloom，原本强度相差百倍的高光将产生完全相同的模糊光晕，彻底丧失物理真实感；
2. **色调与色相保真**：在 HDR 线性空间执行模糊能够保证多色光晕在空间混合时遵循物理光学叠加（Additive Blending），避免在非线性 Gamma 空间模糊引发的暗边缘与色相扭曲。

软阈值高光提取曲线 (Soft-Knee Thresholding)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传统的硬阈值提取（Hard Thresholding）：

.. math::

   \mathbf{C}_{	ext{bloom}} = \max(0, \, \mathbf{C}_{	ext{in}} - T_{	ext{threshold}})

*缺陷*：当像素亮度在阈值 $T$ 附近微弱波动时，提取出的能量会出现从 $0$ 到非零的阶跃突变，在相机移动或物体运动时引发极其严重的屏幕边缘阶梯伪影与闪烁（Temporal Fireflies）。

现代工业标准（如 Unreal Engine 5 / Unity HDRP）采用 **软膝形二次过渡阈值曲线 (Soft-Knee Quadratic Curve)**：

.. math::

   	ext{Knee}(x, T, k) = \begin{cases}
   0, & x \le T - k \
   \frac{(x - T + k)^2}{4k}, & T - k < x \le T + k \
   x - T, & x > T + k
   \end{cases}

其中：
- $T$ 为基准提取阈值（Threshold，例如 $1.0$）；
- $k$ 为软过渡带宽（Soft Knee Width，例如 $0.5$），在区间 $[T-k, T+k]$ 内引入二阶连续可导曲线，实现亮度的平滑渐进释放；
- 输入标量亮度 $L = 	ext{dot}(\mathbf{C}_{	ext{in}}, (0.2126, 0.7152, 0.0722))$，提取系数为 $w = \frac{\max(	ext{Knee}(L, T, k), \, 0)}{L + \epsilon}$，最终提取颜色为 $\mathbf{C}_{	ext{bloom}} = \mathbf{C}_{	ext{in}} \cdot w$。

------------------------------------------------------------------------
32.2 泛光滤波金字塔：从大半径高斯到 Dual-Kawase 降采样与升采样
------------------------------------------------------------------------

传统全分辨率大半径高斯模糊的性能瓶颈
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了模拟弥漫全屏的柔和辉光，Bloom 模糊半径通常需要覆盖屏幕尺寸的 $5\% \sim 20\%$（在 4K 分辨率下相当于 $200 \sim 800$ 像素的核半径）：
- **直接二维高斯卷积**：复杂度为 $O(R^2)$，单像素需要采样数万次，在实时渲染中完全不可行；
- **可分离横纵两向高斯卷积**：复杂度降为 $O(2R)$，但对于 $R = 200$，每个像素仍需执行 400 次纹理采样。在 4K 分辨率（830 万像素）下，单帧需要读写显存数十 GB，导致 GPU 显存总线彻底被纹理寻址带宽打穿。

降采样金字塔架构 (Mipmap Blur Pyramid)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代渲染管线采用 **层次化降采样与升采样金字塔 (Downsample-Upsample Chain)** 架构：
将图像逐级降采样为全分辨率的 $1/2, 1/4, 1/8, 1/16, 1/32, 1/64$（通常 5~7 级 Mipmap），在低分辨率下执行极小半径（如 $3 	imes 3$ 或 $5 	imes 5$）采样即可等效获得超大物理半径的屏幕模糊范围。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             Dual-Kawase / 13-Tap 泛光滤波金字塔数据流架构                |
   +-------------------------------------------------------------------------+

      [ HDR 场景图 (1080p, 1920x1080) ]
                    |
                    | (Pass 0: Soft-Knee 提取 + 13-Tap 降采样)
                    v
      [ Mip 1: 960x540 ] ------------+
            |                        |
            | (13-Tap 降采样)        | (加权累加 Upsample)
            v                        |
      [ Mip 2: 480x270 ] --------+   |
            |                    |   |
            | (13-Tap 降采样)    | (Tent 升采样)
            v                    |   |
      [ Mip 3: 240x135 ] ----+   |   |
            |                |   |   |
            | (13-Tap 降采样)| (Tent 升采样)
            v                |   |   |
      [ Mip 4: 120x67  ] -+  |   |   |
            |             |  |   |   |
            | (降采样)    |  |   |   |
            v             |  |   |   |
      [ Mip 5: 60x33   ]  |  |   |   |
            |             |  |   |   |
            v             v  v   v   v
      [ 最底层模糊基底 ] ---> 逐级 Tent 升采样并加权累加 (Additive Merge)
                                     |
                                     v
                        [ 最终高质量无噪点 Bloom 纹理 ]

13-Tap 抗闪烁降采样滤波核 (Jimenez 13-Tap Downsample)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在逐级降采样过程中，简单的 $2 	imes 2$ 盒状均值滤波（Box Filter）会导致高频亮斑在跳级时产生严重的摩尔纹与时域闪烁（Subpixel Aliasing）。

Call of Duty 与 Unreal Engine 广泛采用 Jorge Jimenez (2014) 提出的 **13-Tap 降采样滤波核**。该算法巧妙利用 GPU 纹理采样器的硬件双线性插值特性（Bilinear Hardware Interpolation），仅需执行 13 次纹理采样即可覆盖 $4 	imes 4$ 像素区域，并赋予中心与角落平滑权重：

.. code-block:: text

   采样点拓扑分布 (覆盖 4x4 像素窗口):

       A       B       C
           D       E       (D, E, F, G 位于四个 2x2 象限的子中心)
       F       G       H
           I       J
       K       L       M

- **中心大盒 (4 个采样点 D, E, I, J)**：每个点权重为 $0.5 	imes 0.25 = 0.125$（总权重 $0.5$）；
- **角落与十字 9 个采样点 (A, B, C, F, G, H, K, L, M)**：十字中心 $G$ 权重为 $0.125$，其余 8 个外围点各占 $0.03125$（总权重 $0.5$）；
- **抗 Firefly 局部加权平均**：在降采样着色器中，对采样的颜色根据亮度倒数执行 Karis 加权（$w_i = \frac{1}{1 + 	ext{Luma}(C_i)}$），彻底消除单像素高亮孤立噪点对降采样金字塔的污染。

Dual-Kawase 升采样与 Tent 滤波
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

升采样过程并非简单的双线性放大，否则会产生明显的方块块状瑕疵（Blocky Artifacts）。

采用 **9-Tap Tent 滤波核** 将低一级分辨率的平滑光晕按双线性插值采样 9 个偏移点，并与高一级分辨率的原有纹理进行加权相加（Additive Blend / Lerp）：

.. math::

   \mathbf{C}_{	ext{up}} = \frac{4}{16} \mathbf{C}_{	ext{center}} + \frac{2}{16} \sum \mathbf{C}_{	ext{axis}} + \frac{1}{16} \sum \mathbf{C}_{	ext{diagonal}}

.. list-table:: 各种泛光模糊算法显存带宽与图像质量对比
   :widths: 22 26 26 26
   :header-rows: 1
   :class: tight-table

   * - 模糊算法
     - 每像素纹理采样数
     - 显存带宽消耗 (4K)
     - 光晕质量与平滑度
   * - **全分辨率 2D 高斯**
     - $O(R^2)$ (>10000 次)
     - 极高 (>50 GB/frame，不可用)
     - 完美数学平滑
   * - **可分离横纵高斯**
     - $O(2R)$ (100~400 次)
     - 高 (10~25 GB/frame)
     - 轴向对齐，大半径时开销陡增
   * - **标准 Mipmap Box 降采样**
     - 4 次 (逐级 $2 	imes 2$)
     - 极低 (<0.5 GB/frame)
     - 严重块状伪影与高频闪烁
   * - **Dual-Kawase / 13-Tap 金字塔**
     - 13 次 (Down) + 9 次 (Up)
     - 低 (~1.2 GB/frame)
     - 极平滑电影级光晕，时域极其稳定

------------------------------------------------------------------------
32.3 景深 (Depth of Field) 光学物理基础与薄透镜模型
------------------------------------------------------------------------

针孔相机模型具有无限景深，所有距离的几何图元在投影后均绝对锐利。真实光学相机由具有物理孔径（Aperture）的凸透镜组构成，非对焦点处的光线会在传感器感光底片上发散成一个有限区域的光斑，该光斑被称为 **弥散圆 (Circle of Confusion - CoC)**。

薄透镜高斯成像公式 (Thin-Lens Equation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

根据经典几何光学，凸透镜满足高斯薄透镜公式：

.. math::

   \frac{1}{f} = \frac{1}{S_o} + \frac{1}{S_i}

其中：
- $f$：透镜焦距（Focal Length，如 $50 \, \mathrm{mm} = 0.05 \, \mathrm{m}$）；
- $S_o$：物方对焦距离（Focus Distance / Object Distance，即清晰对焦平面的深度）；
- $S_i$：像方底片距离（Sensor Distance / Image Distance）。

由此推导出传感器底片与透镜的物理距离为：

.. math::

   S_i = \frac{f \cdot S_o}{S_o - f}

弥散圆 (Circle of Confusion - CoC) 直径严格解析推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当场景中某个物体的实际物距为 $z$（$z 
e S_o$）时，经透镜折射后的真实聚焦点像距为 $z_i = \frac{f \cdot z}{z - f}$。

定义物理有效孔径直径 $A = \frac{f}{N}$（其中 $N$ 为镜头光圈系数 F-number，如 $f/1.4, f/2.8$）。

根据相似三角形几何比例关系，光锥在感光底片平面（位于 $S_i$ 处）所截出的弥散圆物理直径 $c$（单位：米）为：

.. math::

   \frac{c}{A} = \frac{|z_i - S_i|}{z_i} = \left| 1 - \frac{S_i}{z_i} \right|

将 $S_i$ 与 $z_i$ 代入化简，得到以物距 $z$ 为变量的弥散圆物理直径公式：

.. math::

   c(z) = A \cdot \frac{|z - S_o|}{z} \cdot \frac{f}{S_o - f} = \frac{f^2}{N(S_o - f)} \cdot \frac{|z - S_o|}{z}

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     薄透镜弥散圆 (CoC) 几何光学成像原理                 |
   +-------------------------------------------------------------------------+

      物方空间 (Object Space)                 透镜 (Lens)      像方空间 (Image Space)
                                              孔径 A = f/N
         清晰对焦点 P_focus (物距 S_o) ----------+            +--- 像平面 (底片 S_i)
                                                 | \        / |
         近景离焦物点 P_near  (物距 z_near) -----|---\----/---|-- 后焦点像距 z_i
                                                 |     \/     |
         远景离焦物点 P_far   (物距 z_far) ------|-----/\-----|-- 前焦点像距 z_i
                                                 |    /  \    |
                                                 +---+----+---+
                                                     |    |   |
                                                     |    +---+--- 弥散圆直径 c(z)
                                                     |<--f--->|

像素空间弥散圆 (Pixel CoC) 与符号约定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

渲染管线最终需要的是以 **屏幕像素 (Pixels)** 为单位的有符号弥散圆半径 $	ext{CoC}_{	ext{px}}$：

1. **物理单位向像素单位转换**：
   设虚拟相机感光底片高度为 $H_{	ext{sensor}}$（标准 35mm 全画幅胶片为 $0.024 \, \mathrm{m}$），渲染目标垂直分辨率为 $H_{	ext{screen}}$ 像素：

.. math::

   	ext{CoC}_{	ext{pixels}}(z) = c(z) 	imes \frac{H_{	ext{screen}}}{H_{	ext{sensor}}}

2. **有符号 CoC 规则（分离前后景）**：
   - **近景前景 (Near Field, $z < S_o$)**：$	ext{CoC} < 0$，物体位于透镜与对焦平面之间，模糊光斑将向外扩展并覆盖在背景之上；
   - **完全对焦区 (In-Focus, $z = S_o$)**：$	ext{CoC} = 0$，像素绝对锐利清晰；
   - **远景背景 (Far Field, $z > S_o$)**：$	ext{CoC} > 0$，物体位于对焦平面之后，模糊光斑被清晰前景所遮挡。

------------------------------------------------------------------------
32.4 实时景深着色流水线与散景 (Bokeh) 微架构
------------------------------------------------------------------------

景深渲染的工业级难点：深度不连续与边缘渗漏 (Color Bleeding)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若直接在屏幕空间执行简单的模糊卷积，会引发严重的渲染物理瑕疵：
- **背景向前景渗漏 (Background Bleeding into Sharp Foreground)**：当远处模糊背景与近处清晰边缘相邻时，简单的模糊卷积核会将背景的模糊颜色错误地涂抹到锐利的前景物体上；
- **前景遮挡边缘硬截断 (Hard Edge on Blurry Foreground)**：近处大弥散圆前景物体的虚化边缘应当半透明“外溢”羽化在清晰背景之上，若不分离计算，前景虚化会被背景硬性切断。

工业级 4-Pass 分离景深流水线架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代商业 3A 引擎（如 Frostbite / Unreal Engine / CryEngine）采用 **前后景解耦的分离散景滤波架构**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                工业级四阶段前后景解耦景深 (DoF) 渲染管线                |
   +-------------------------------------------------------------------------+

      [ 场景颜色 (RGBA16F) ] + [ 线性深度图 (R32F) ]
                    |
                    v
      [ Pass 1: CoC 计算与降采样预分类 (CS_ComputeCoCAndPrefilter) ]
      (计算每像素有符号 CoC，分离输出 Near CoC 与 Far CoC，半分辨率降采样)
                    |
                    v
      [ Pass 2: Tile-Max CoC 粗粒度分类 (CS_TileMaxCoC) ]
      (计算 16x16 像素块的最大 Near/Far CoC，用于 Early-Exit 与核尺寸动态约束)
                    |
                    v
      [ Pass 3: 散景模糊卷积 (CS_BokehConvolution) ]
      (半分辨率执行: 利用 Poisson Disk / 菱形分离卷积模拟圆形/六边形光学散景)
                    |
                    +-----------------------+
                    | (前景 Near Blur 层)   | (背景 Far Blur 层)
                    v                       v
      [ Pass 4: 边缘感知重构与 Alpha 混合合成 (CS_DoFComposite) ]
      (基于深度感知权重重构全分辨率边缘，将全清晰原图、Far层与Near层正确遮挡合成)
                    |
                    v
      [ 输出最终具有物理散景的景深图像 ]

散景孔径形状模拟 (Bokeh Aperture Shape)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

真实镜头由若干片光圈叶片（Aperture Blades）咬合而成：
- **圆形孔径（理想透镜）**：采样点分布采用均匀 Poisson Disk 或同心圆盘采样；
- **多边形孔径（5~9 边形光圈）**：将采样偏移约束在正多边形边界内，并在高光处形成多边形光斑；
- **色差与边缘亮环 (Optical Aberrations & Cat-Eye Effect)**：在 CoC 边缘强化高光权重（模拟镜片球面像差造成的边缘锐化），并根据视场角引入椭圆径向变形（猫眼散景）。

.. list-table:: 景深核心管线阶段与数据格式规范
   :widths: 25 25 25 25
   :header-rows: 1
   :class: tight-table

   * - 阶段 Pass 名称
     - 输入资源
     - 输出资源与格式
     - 核心算法与微架构
   * - **Pass 1: CoC 生成**
     - Scene Depth (R32F)
     - CoC Texture (R16F / RG16F)
     - 薄透镜公式，分离有符号 Near/Far CoC
   * - **Pass 2: Tile-Max 预处理**
     - CoC Texture (半分辨率)
     - TileMax Buffer (RG8_UNORM)
     - $16 	imes 16$ 局部极大值，驱动动态分支跳过清晰区
   * - **Pass 3: 散景卷积**
     - HDR Color + CoC (Half-Res)
     - Near/Far Blur (RGBA16F)
     - 22~64 Tap 散景核加权 Gather，深度防渗漏权重
   * - **Pass 4: 图像重构合成**
     - Full-Res Color + Blur Textures
     - Final DoF Color (RGBA16F)
     - 双边上采样（Bilateral Upsampling），Alpha 遮挡混合

------------------------------------------------------------------------
32.5 工业级 HLSL / Compute Shader 泛光与景深完整实现
------------------------------------------------------------------------

以下是符合 DirectX 12 / Vulkan 工业规范的完整 HLSL 6.5+ 源码，包含 **基于 13-Tap 降采样与 9-Tap Tent 升采样的 Dual-Kawase 物理 Bloom** 以及 **基于薄透镜模型的前后景解耦散景景深着色器**：

.. code-block:: hlsl

   // =========================================================================
   // File: PostProcess_Bloom_DepthOfField.hlsl
   // Standard: HLSL 6.5+ (DX12 / Vulkan via DXC)
   // Architecture: Physical Dual-Kawase Bloom + Thin-Lens Bokeh Depth of Field
   // =========================================================================

   struct PostProcessConstants {
       float2 RenderTargetSize;
       float2 RcpRenderTargetSize;
       
       // Bloom 参数
       float  BloomThreshold;       // 提取阈值 (如 1.0)
       float  BloomSoftKnee;        // 软过渡宽度 (如 0.5)
       float  BloomIntensity;       // 泛光合成强度
       float  BloomScatter;         // 升采样发散系数 (0.0 ~ 1.0)
       
       // Depth of Field 薄透镜光学参数
       float  FocalLength;          // 焦距 f (米, 如 0.050)
       float  FNumber;              // 光圈系数 N (如 1.4, 2.8)
       float  FocusDistance;        // 对焦物距 S_o (米, 如 3.0)
       float  SensorHeight;         // 感光底片高度 (米, 如 0.024)
       float  MaxCoCRadiusPixels;   // 最大弥散圆限制 (像素, 如 32.0)
       float  DoFIntensity;         // 景深混合权重
   };

   ConstantBuffer<PostProcessConstants> g_CB : register(b0);

   Texture2D<float4>   g_HDRSceneTexture     : register(t0);
   Texture2D<float>    g_CameraDepthTexture  : register(t1); // 线性物理深度 (米)
   Texture2D<float2>   g_CoCTexture          : register(t2); // x: NearCoC, y: FarCoC
   Texture2D<float4>   g_LowResBlurTexture   : register(t3); // 升采样或散景中间纹理
   SamplerState        g_LinearClampSampler  : register(s0);

   RWTexture2D<float4> g_RWOutputColor       : register(u0);
   RWTexture2D<float2> g_RWOutputCoC         : register(u1);

   // =========================================================================
   // 模块 1: 物理 Bloom (13-Tap Downsample & 9-Tap Tent Upsample)
   // =========================================================================

   // 软膝形高光提取函数
   float3 ApplySoftKneeBloomThreshold(float3 color, float threshold, float knee) {
       float luma = dot(color, float3(0.2126f, 0.7152f, 0.0722f));
       float soft = luma - threshold + knee;
       soft = clamp(soft, 0.0f, 2.0f * knee);
       soft = (soft * soft) / (4.0f * knee + 0.00001f);
       float weight = max(soft, luma - threshold) / max(luma, 0.00001f);
       return color * saturate(weight);
   }

   // 13-Tap 降采样 Compute Shader
   [numthreads(8, 8, 1)]
   void CS_Bloom_Downsample13Tap(uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       uint2 outCoord = dispatchThreadID.xy;
       if (outCoord.x >= (uint)g_CB.RenderTargetSize.x || 
           outCoord.y >= (uint)g_CB.RenderTargetSize.y) return;

       float2 texelSize = g_CB.RcpRenderTargetSize;
       float2 uv = (float2(outCoord) + 0.5f) * texelSize;

       // 采样 13 个关键点
       float3 A = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2(-2, -2) * texelSize, 0).rgb;
       float3 B = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( 0, -2) * texelSize, 0).rgb;
       float3 C = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( 2, -2) * texelSize, 0).rgb;

       float3 D = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2(-1, -1) * texelSize, 0).rgb;
       float3 E = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( 1, -1) * texelSize, 0).rgb;

       float3 F = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2(-2,  0) * texelSize, 0).rgb;
       float3 G = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv, 0).rgb;
       float3 H = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( 2,  0) * texelSize, 0).rgb;

       float3 I = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2(-1,  1) * texelSize, 0).rgb;
       float3 J = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( 1,  1) * texelSize, 0).rgb;

       float3 K = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2(-2,  2) * texelSize, 0).rgb;
       float3 L = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( 0,  2) * texelSize, 0).rgb;
       float3 M = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( 2,  2) * texelSize, 0).rgb;

       // 加权平均计算 (中心大盒占 0.5，十字及角落占 0.5)
       float3 group1 = (D + E + I + J) * 0.125f;
       float3 group2 = (A + C + K + M) * 0.03125f;
       float3 group3 = (B + F + H + L) * 0.0625f;
       float3 group4 = G * 0.125f;

       float3 downsampledColor = group1 + group2 + group3 + group4;

       // 若为第一级 Mipmap，执行软阈值高光提取
       #ifdef FIRST_DOWNSAMPLE_PASS
           downsampledColor = ApplySoftKneeBloomThreshold(downsampledColor, g_CB.BloomThreshold, g_CB.BloomSoftKnee);
       #endif

       g_RWOutputColor[outCoord] = float4(downsampledColor, 1.0f);
   }

   // 9-Tap Tent 升采样累加 Compute Shader
   [numthreads(8, 8, 1)]
   void CS_Bloom_UpsampleTent(uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       uint2 outCoord = dispatchThreadID.xy;
       if (outCoord.x >= (uint)g_CB.RenderTargetSize.x || 
           outCoord.y >= (uint)g_CB.RenderTargetSize.y) return;

       float2 texelSize = g_CB.RcpRenderTargetSize;
       float2 uv = (float2(outCoord) + 0.5f) * texelSize;

       float d = g_CB.BloomScatter; // 发散半径步长

       // 9-Tap 3x3 帐篷滤波采样
       float3 c0 = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2(-d, -d) * texelSize, 0).rgb * 1.0f;
       float3 c1 = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( 0, -d) * texelSize, 0).rgb * 2.0f;
       float3 c2 = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( d, -d) * texelSize, 0).rgb * 1.0f;

       float3 c3 = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2(-d,  0) * texelSize, 0).rgb * 2.0f;
       float3 c4 = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv, 0).rgb * 4.0f;
       float3 c5 = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( d,  0) * texelSize, 0).rgb * 2.0f;

       float3 c6 = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2(-d,  d) * texelSize, 0).rgb * 1.0f;
       float3 c7 = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( 0,  d) * texelSize, 0).rgb * 2.0f;
       float3 c8 = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, uv + float2( d,  d) * texelSize, 0).rgb * 1.0f;

       float3 upsampledBlur = (c0 + c1 + c2 + c3 + c4 + c5 + c6 + c7 + c8) * (1.0f / 16.0f);

       // 与当前层级原有图像进行加权累加 (Additive Blend)
       float3 highResColor = g_LowResBlurTexture.Load(int3(outCoord, 0)).rgb;
       g_RWOutputColor[outCoord] = float4(highResColor + upsampledBlur, 1.0f);
   }

   // =========================================================================
   // 模块 2: 薄透镜景深 (Depth of Field & Bokeh Blur)
   // =========================================================================

   // Pass 1: 计算物理弥散圆 (CoC)
   [numthreads(8, 8, 1)]
   void CS_DoF_CalculateCoC(uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       uint2 pixelCoord = dispatchThreadID.xy;
       if (pixelCoord.x >= (uint)g_CB.RenderTargetSize.x || 
           pixelCoord.y >= (uint)g_CB.RenderTargetSize.y) return;

       float z = g_CameraDepthTexture.Load(int3(pixelCoord, 0)); // 物理线性深度 (米)
       
       if (z <= 0.0001f) {
           g_RWOutputCoC[pixelCoord] = float2(0, 0);
           return;
       }

       float f = g_CB.FocalLength;
       float N = g_CB.FNumber;
       float S_o = g_CB.FocusDistance;
       float A = f / N; // 光圈有效孔径 (米)

       // 薄透镜解析 CoC 公式计算 (米)
       float cocMeter = A * ((z - S_o) / z) * (f / max(S_o - f, 0.001f));

       // 转换至屏幕像素半径
       float cocPixels = cocMeter * (g_CB.RenderTargetSize.y / g_CB.SensorHeight);
       cocPixels = clamp(cocPixels, -g_CB.MaxCoCRadiusPixels, g_CB.MaxCoCRadiusPixels);

       // 分离 Near CoC 与 Far CoC
       float nearCoC = saturate(-cocPixels / g_CB.MaxCoCRadiusPixels); // [0, 1] 归一化
       float farCoC  = saturate( cocPixels / g_CB.MaxCoCRadiusPixels); // [0, 1] 归一化

       g_RWOutputCoC[pixelCoord] = float2(nearCoC, farCoC);
   }

   // Pass 2: 散景模糊卷积与前后景深度加权合成
   static const float2 k_PoissonDisk[16] = {
       float2(-0.326f, -0.406f), float2(-0.840f, -0.074f),
       float2(-0.696f,  0.457f), float2(-0.203f,  0.621f),
       float2( 0.962f, -0.195f), float2( 0.473f, -0.480f),
       float2( 0.519f,  0.767f), float2( 0.185f, -0.893f),
       float2( 0.507f,  0.064f), float2( 0.896f,  0.412f),
       float2(-0.322f, -0.933f), float2(-0.792f, -0.598f),
       float2(-0.012f,  0.276f), float2( 0.156f,  0.448f),
       float2( 0.371f, -0.155f), float2(-0.528f,  0.125f)
   };

   [numthreads(8, 8, 1)]
   void CS_DoF_BokehBlurAndComposite(uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       uint2 pixelCoord = dispatchThreadID.xy;
       if (pixelCoord.x >= (uint)g_CB.RenderTargetSize.x || 
           pixelCoord.y >= (uint)g_CB.RenderTargetSize.y) return;

       float2 uv = (float2(pixelCoord) + 0.5f) * g_CB.RcpRenderTargetSize;
       float3 centerColor = g_HDRSceneTexture.Load(int3(pixelCoord, 0)).rgb;
       float2 centerCoC   = g_CoCTexture.Load(int3(pixelCoord, 0)); // x: near, y: far

       float centerRadius = max(centerCoC.x, centerCoC.y) * g_CB.MaxCoCRadiusPixels;

       // 若完全对焦清晰且无前景羽化，直接输出原色 (Early-Exit 优化)
       if (centerRadius < 0.5f) {
           g_RWOutputColor[pixelCoord] = float4(centerColor, 1.0f);
           return;
       }

       float3 accumColor = centerColor;
       float  totalWeight = 1.0f;

       [unroll]
       for (uint i = 0; i < 16; ++i) {
           float2 offsetUV = uv + k_PoissonDisk[i] * (centerRadius * g_CB.RcpRenderTargetSize);
           float3 sampleColor = g_HDRSceneTexture.SampleLevel(g_LinearClampSampler, offsetUV, 0).rgb;
           float2 sampleCoC   = g_CoCTexture.SampleLevel(g_LinearClampSampler, offsetUV, 0);

           // 深度感知权重: 防止远景背景渗漏至锐利前景
           float sampleRadius = max(sampleCoC.x, sampleCoC.y) * g_CB.MaxCoCRadiusPixels;
           float weight = saturate((sampleRadius - length(k_PoissonDisk[i] * centerRadius) + 1.0f) / 2.0f);

           accumColor  += sampleColor * weight;
           totalWeight += weight;
       }

       float3 finalBlurColor = accumColor / max(totalWeight, 0.0001f);
       float  blendFactor = saturate(centerRadius / 2.0f) * g_CB.DoFIntensity;

       float3 compositeResult = lerp(centerColor, finalBlurColor, blendFactor);
       g_RWOutputColor[pixelCoord] = float4(compositeResult, 1.0f);
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统剖析了实时后处理管线中两项最关键的光学拟真技术——物理泛光 (Bloom) 与景深 (Depth of Field) 散景微架构：
1. **泛光光学成因与提取曲线**：明确了 Bloom 在 Scene-Referred 线性无界空间执行的物理必要性，推导了二次软膝形（Soft-Knee）阈值曲线消除边缘突变与时域闪烁的机理；
2. **Dual-Kawase 与 13-Tap 滤波金字塔**：对比了传统大半径高斯模糊的显存带宽瓶颈，解构了 13-Tap 降采样与 9-Tap Tent 升采样累加金字塔极高画质与低带宽（仅 ~1.2 GB/s）的核心优势；
3. **薄透镜几何光学与 CoC 推导**：严格推导了高斯成像方程与有符号屏幕像素弥散圆 $	ext{CoC}_{	ext{pixels}}(z)$ 的数学闭环，确立了 Near CoC 与 Far CoC 的物理非对称性；
4. **前后景分离散景着色架构**：剖析了深度不连续导致的背景渗漏难题，建立了 Tile-Max 预分块、Poisson Disk 散景卷积与双边边缘感知合成流水线。

在下一章（Chapter 33）中，我们将深入探讨现代实时图形学中最核心的抗锯齿与时域重构支柱—— **时间性抗锯齿 (Temporal Anti-Aliasing - TAA)**。我们将系统推导 **亚像素相机抖动序列 (Halton / Sobol Jitter)、运动矢量速度缓冲区 (Velocity Buffer)、历史帧几何重投影、双调和与 AABB 色彩空间裁剪 (Color Clamping) 以及抗鬼影 (Ghosting) 与暗部闪烁抑制微架构**，敬请期待！
