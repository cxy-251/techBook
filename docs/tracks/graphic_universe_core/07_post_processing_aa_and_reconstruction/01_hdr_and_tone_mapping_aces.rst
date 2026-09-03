========================================================================
Chapter 31: 高动态范围 (HDR) 与色调映射：ACES 色彩管线、Reinhard 与曝光自适应
========================================================================

.. note:: 前置背景与认知承接
   在前六个模块中，我们系统推导了从 GPU 硬件架构、空间几何拓扑、光栅化/着色器微结构、基于物理的渲染（PBR）、实时阴影加速结构，到硬件光线追踪与 ReSTIR 路径追踪的完整底层渲染流水线。在这一阶段，几何着色与全局光照计算输出的辐射亮度值（Radiance）均处于无物理上限的 **场景参照线性空间 (Scene-Referred Linear Space)** 中。

   在真实物理世界中，烛光的表面辐射亮度约为 $10 \, \mathrm{cd/m^2}$，室内漫反射物体约为 $10^2 \sim 10^3 \, \mathrm{cd/m^2}$，而直射日光与高光镜面反射可高达 $10^5 \sim 10^9 \, \mathrm{cd/m^2}$，动态范围跨越 $6 \sim 8$ 个数量级。然而，人类视觉系统（HVS）以及传统的标准动态范围显示器（SDR sRGB，峰值亮度通常被钳制在 $80 \sim 300 \, \mathrm{nits}$，动态范围仅约 $100:1$）或现代超高清 HDR 显示器（HDR10 / DisplayHDR 1000，峰值亮度 $1000 \sim 4000 \, \mathrm{nits}$），均无法直接原样重现场景线性的无限动态范围。

   若简单地对超出 $[0, 1]$ 范围的高光信号执行硬件饱和截断（Clamp），会导致高光区域出现大面积死白、边缘色相漂移（Hue Shift）与高频细节彻底丢失。本章将系统剖析 **从场景参照到显示参照的色彩空间变换、自动曝光控制（基于 Compute Shader 256-bin 对数亮度直方图）、经典与电影级色调映射算子（Reinhard、Hable Filmic）、影视工业标准 ACES (Academy Color Encoding System) 色彩管线微架构与实时拟合算法，以及面向 Windows Advanced Color / HDR10 显示设备的色彩与亮度编码适配**。

------------------------------------------------------------------------
31.1 场景参照线性空间 (Scene-Referred) 与显示参照空间 (Display-Referred)
------------------------------------------------------------------------

在现代物理渲染管线中，核心色彩数据流经历了一次关键的范式转换：从物理线性的场景真实光度量，转换为适配特定人类感知与显示面板的非线性电信号。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             现代渲染管线从场景参照到显示参照的端到端色彩流转            |
   +-------------------------------------------------------------------------+

      [ PBR / GI / 路径追踪 ] (Scene-Referred Linear, RGBA16F / RGBA32F)
                 | (数值范围: [0.0, +inf), 无物理上限)
                 v
      [ 物理相机曝光缩放 (Exposure Scale / EV100) ]
                 |
                 +------> [ 物理 Bloom 提取 (提取高亮未压缩特征) ]
                 |                     |
                 v                     v
      [ 色调映射算子 (Tone Mapping Operator: ACES / Filmic / Reinhard) ]
                 | (非线性动态范围压缩, 映射至设备基准白点)
                 v
      [ 色彩分级与色域映射 (Color Grading / 3D LUT in ACEScg / Rec.709) ]
                 |
                 +<----- [ Bloom 能量加权合成 (经过统一 Shoulder 约束) ]
                 |
                 v
      [ 显示传递函数与色彩编码 (Display Encoding: sRGB OETF / HDR10 PQ ST2084) ]
                 | (数值范围: [0.0, 1.0] for SDR 或绝对 nits for HDR)
                 v
      [ Swapchain Present (8-bit UNORM / 10-bit HDR10 / 16-bit scRGB) ]

场景参照 (Scene-Referred) 的物理特征
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **绝对线性可加性**：在 Scene-Referred 空间中，光照计算满足物理能量守恒与辐射度叠加原理。若光源辐射通量翻倍，物体表面的反射辐射亮度严格翻倍；两次光照反弹的贡献可以直接代数相加；
2. **浮点动态范围**：渲染目标（Render Target）必须采用至少 16 位浮点精度格式（如 `DXGI_FORMAT_R16G16B16A16_FLOAT` 或 `VK_FORMAT_R16G16B16A16_SFLOAT`），以避免在暗部产生量化条带（Banding）并在高光区容纳大于 $1000.0$ 的数值；
3. **中灰校准锚点 (Middle Gray)**：行业普遍将 $18\%$ 反射率的理想朗伯漫反射表面作为曝光参考基准（Middle Gray = $0.18$）。

显示参照 (Display-Referred) 的感知约束
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **有限动态范围**：显示信号受限于物理发光面板的最低黑位（Black Level，如 LCD 的 $0.1 \, \mathrm{nits}$ 或 OLED 的 $0.0005 \, \mathrm{nits}$）与最高峰值亮度（Peak Brightness，如 $100 \sim 1000 \, \mathrm{nits}$）；
2. **感知均匀非线性编码**：人类视觉对亮度的感知呈对数响应（Weber-Fechner 定律与 Stevens 幂律）。为了在有限位宽（如 8-bit 或 10-bit）下最大化分配暗部精度，必须应用非线性光电转换函数（OETF，如 sRGB Gamma 2.2 或 HDR10 ST.2084 PQ 曲线）；
3. **不可逆性**：一旦经过 Tone Mapping 压缩与显示编码，图像失去了物理线性的能量比例关系，无法再进行准确的 PBR 漫反射计算或光照物理合成。

.. list-table:: Scene-Referred 与 Display-Referred 空间核心属性对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 属性维度
     - Scene-Referred 场景参照空间
     - Display-Referred 显示参照空间
   * - **物理本质**
     - 真实物理辐射亮度 (Radiance / $\mathrm{W \cdot sr^{-1} \cdot m^{-2}}$)
     - 目标显示器驱动电信号 (Normalized Code Value)
   * - **数值范围**
     - $[0.0, +\infty)$ 连续无上限浮点数
     - $[0.0, 1.0]$（归一化 SDR）或固定 nits 编码
   * - **数学性质**
     - 严格满足光辐射能量线性叠加
     - 感知非线性（Gamma / PQ 曲线变换后）
   * - **显存格式**
     - `RGBA16F` / `RGBA32F` / `R11G11B10F`
     - `RGBA8_UNORM_SRGB` / `R10G10B10A2_UNORM`
   * - **适用管线阶段**
     - PBR 着色、阴影、全局光照、体积雾、SSR
     - UI 合成、抗锯齿尾部、Swapchain 显示输出

------------------------------------------------------------------------
31.2 摄影曝光控制与基于 Compute Shader 直方图的自动曝光
------------------------------------------------------------------------

色调映射的第一步是通过 **曝光 (Exposure)** 将场景中关注的主体亮度对齐至色调映射曲线的线性响应区间（通常将目标中灰映射至显示空间的 $0.18$ 附近）。

物理相机曝光模型 (EV100 Formulation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在真实摄影光学中，传感器接收到的曝光量由光圈值（Aperture $N$）、快门时间（Shutter Speed $t$ 秒）与感光度（ISO $S$）共同决定。定义标准感光度 ISO 100 下的曝光值（Exposure Value - $\mathrm{EV}_{100}$）：

.. math::

   \mathrm{EV}_{100} = \log_2 \left( \frac{N^2}{t} \right) - \log_2 \left( \frac{S}{100} \right)

根据物理测光标准（ISO 12232），场景中灰亮度 $L_{	ext{avg}}$（单位：$\mathrm{cd/m^2}$）与标称曝光缩放因子 $K_{	ext{exposure}}$ 的解析转换公式为：

.. math::

   K_{	ext{exposure}} = \frac{1.0}{1.2 	imes 2^{\mathrm{EV}_{100}}}

将场景线性颜色 $\mathbf{C}_{	ext{linear}}$ 乘以 $K_{	ext{exposure}}$，即可完成场景信号向标准化曝光空间的线性缩放：

.. math::

   \mathbf{C}_{	ext{exposed}} = \mathbf{C}_{	ext{linear}} \cdot K_{	ext{exposure}} \cdot 2^{	ext{ExposureCompensation}}

基于 256-Bin 对数亮度直方图的自动曝光 (Histogram-Based Auto Exposure)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

传统的单帧平均亮度求法（Mipmap 链逐级下采样降至 $1 	imes 1$）存在致命缺陷：画面中若出现极小面积的极亮太阳或火花，会导致平均值剧烈飙升，迫使画面整体暗部严重欠曝压死；反之，大面积暗夜背景会导致高光彻底过曝。

现代工业标准（如 Unreal Engine 5 / Frostbite）采用基于 GPU Compute Shader 的 **256-Bin 对数亮度直方图 (Logarithmic Luminance Histogram)** 统计算法：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |          基于 Compute Shader 256-Bin 对数直方图自动曝光流水线           |
   +-------------------------------------------------------------------------+

      [ 输入场景 HDR 图像 (RGBA16F, 1920x1080) ]
                          |
                          v
      [ Pass 1: 并行构建直方图 (CS_BuildHistogram) ]
      (每个线程组处理 16x16 像素, 使用 groupShared uint s_Hist[256] 局部原子累加)
                          |
                          v (组内同步并原子合并至全局直方图 StructuredBuffer<uint>)
      [ 全局对数直方图 (256 个 Bins, 覆盖 [-10.0, +10.0] 对数亮度区间) ]
                          |
                          v
      [ Pass 2: 百分位截断与自适应曝光评估 (CS_AverageHistogram) ]
      (剔除最低 10% 极端暗部与最高 5% 极端高光噪点, 计算加权平均对数亮度)
                          |
                          v
      [ 时间平滑滤波 (Temporal Adaptation) ]
      (使用非对称指数平滑: 模拟人眼暗适应慢 / 亮适应快的瞳孔反应时延)
                          |
                          v
      [ 输出当前帧最优曝光乘数 (1x1 Buffer, 驱动 Tone Mapping 着色器) ]

1. **亮度转换与 Bin 映射**：
   使用标准感知亮度公式计算标量亮度 $L = 0.2126R + 0.7152G + 0.0722B$。将其映射至对数区间 $[	ext{MinLogLuma}, 	ext{MaxLogLuma}]$（如 $[-8.0, +8.0]$ 对应约 $2^{-8} \sim 2^8 \, \mathrm{nits}$）：

.. math::

   b = \operatorname{clamp}\left( \left\lfloor \frac{\log_2(L + \epsilon) - 	ext{MinLogLuma}}{	ext{MaxLogLuma} - 	ext{MinLogLuma}} 	imes 256 \right\rfloor, \, 0, \, 255 \right)

2. **双端百分位截断加权均值 (Percentile Clamping)**：
   在汇总 Pass 中，单线程遍历直方图并计算累积分布函数（CDF）。设定低端截断阈值 $P_{	ext{low}} = 0.10$（剔除 10% 最暗黑背景）与高端截断阈值 $P_{	ext{high}} = 0.95$（剔除 5% 极端高光），仅对区间 $[P_{	ext{low}}, P_{	ext{high}}]$ 内的有效像素求加权对数均值 $L_{	ext{target}}$；
3. **人眼时域动态适应模型 (Eye Adaptation)**：
   人眼从暗处走向亮处（亮适应）仅需 $0.1 \sim 0.3 \, \mathrm{s}$，而从亮处进入暗室（暗适应）需要数秒（视紫红质再生过程）。采用时间步长 $\Delta t$ 的非对称指数平滑：

.. math::

   L_{	ext{adapted}}(t) = L_{	ext{adapted}}(t-1) + (L_{	ext{target}} - L_{	ext{adapted}}(t-1)) \cdot \left(1.0 - e^{-\Delta t \cdot 	au}\right)

其中 $	au = 	au_{	ext{light}}$（当 $L_{	ext{target}} > L_{	ext{adapted}}$）或 $	au = 	au_{	ext{dark}}$（当 $L_{	ext{target}} < L_{	ext{adapted}}$）。

------------------------------------------------------------------------
31.3 核心色调映射算子 (Tone Mapping Operators) 数学推导
------------------------------------------------------------------------

色调映射算子（Tone Mapping Operator - TMO）负责将曝光后的无限正数输入映射至有界的显示设备区间 $[0, 1]$。一个优秀的 S 曲线（Sigmoid Curve）必须具备三段解耦结构：
- **暗部足部 (Toe)**：平滑沉入黑位，提供深邃对比度而不直接截断暗部细节；
- **中间调线性段 (Midtone / Linear)**：保持高对比度与保真度，斜率通常接近 $1.0$；
- **高光肩部 (Shoulder)**：渐进式高光滚降（Roll-off），平滑渐进收敛至白点。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       标准色调映射 S 曲线解剖结构                       |
   +-------------------------------------------------------------------------+

     输出亮度 L_out (Display-Referred)
      1.0 +-----------------------------------------------+-- 饱和白点 (White Point)
          |                                        ..---''|
          |                                 .---'''       | <-- 高光肩部 (Shoulder)
          |                              .-'              |     (渐进压缩高光)
          |                            .'                 |
          |                          ./                   | <-- 中间调线性区 (Midtone)
          |                        ./                     |     (保持场景反差)
          |                      ./                       |
          |                   .-'                         | <-- 暗部足部 (Toe)
          |            ..---''                            |     (平滑收拢黑位)
      0.0 +-----------+-----------------------------------+
         0.0         0.18 (中灰锚点)                     L_white   输入亮度 L_in (Exposed HDR)

Reinhard 算子族
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **经典 Reinhard (2002)**：
   最经典的代数有理分式形式，保证输出严格收敛于 $1.0$ 且单调递增：

.. math::

   f_{	ext{Reinhard}}(x) = \frac{x}{1.0 + x}

*特点与缺陷*：无参数可调，高光从 $x > 0.5$ 处即开始强烈压缩，导致中间调反差严重被压平，画面整体发灰。

2. **扩展白点保留型 Reinhard (Extended Reinhard with White Point)**：
   引入可配置参数 $w$（令 $x \ge w$ 的亮度严格映射为 $1.0$）：

.. math::

   f_{	ext{ReinhardExt}}(x) = \frac{x \cdot \left(1.0 + \frac{x}{w^2}\right)}{1.0 + x}

当 $w 	o \infty$ 时退化为经典 Reinhard；当指定有限白点 $w$（如 $w = 4.0$）时，能够在高光区保留更多锐利反差。

Hable Filmic S 曲线 (Uncharted 2 Operator)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

游戏《神秘海域 2》首席渲染工程师 John Hable 提出的 6 参数经验 S 曲线公式，成为游戏工业界最广泛应用的电影级色调映射基线之一：

.. math::

   f_{	ext{Hable}}(x) = \frac{x(A x + C B) + D E}{x(A x + B) + D F} - \frac{E}{F}

各物理参数含义与标准预设如下：
- $A = 0.15$：肩部强度（Shoulder Strength）；
- $B = 0.50$：线性区强度（Linear Strength）；
- $C = 0.10$：线性区角度（Linear Angle）；
- $D = 0.20$：足部强度（Toe Strength）；
- $E = 0.02$：足部起始分量（Toe Numerator）；
- $F = 0.30$：足部截止分量（Toe Denominator）；
- 白点归一化：输入线性白点 $W = 11.2$，最终输出为 $F(x) / F(W)$。

逐通道处理 (Per-Channel) vs 亮度处理 (Luminance-Based) 的色相漂移悖论
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在实现色调映射着色器时，必须面对色彩科学中的核心权衡：

1. **逐通道映射 (Per-Channel Tone Mapping)**：直接对 $\mathbf{C} = (R, G, B)$ 三个分量独立执行标量曲线 $f(R), f(G), f(B)$。
   *物理现象*：当极亮的高饱和黄色（如 $R = 20.0, G = 10.0, B = 0.1$）进入曲线时，$R$ 和 $G$ 均被压缩至接近 $1.0$，导致输出颜色退化为白色 $(1.0, 1.0, 0.1)$，即 **高光脱色（Desaturation towards White）**。虽然这符合真实胶片或人眼视网膜在强光下的感光细胞饱和生理现象，但在某些次高光区会引起明显的色相偏转（Hue Shift）；
2. **基于亮度映射 (Luminance-Based Tone Mapping)**：先求标量亮度 $L = 	ext{dot}(\mathbf{C}, \mathbf{w})$，计算缩放系数 $s = \frac{f(L)}{L}$，再统一缩放 RGB：$\mathbf{C}_{	ext{out}} = \mathbf{C} \cdot s$。
   *物理现象*：严格保持了 RGB 之间的原始比例（色相绝对不变）。但当亮度极高时，极高的色彩分量经过缩放后依然具有极高饱和度，无法形成自然的白色高光核心，且极易超出目标色域边界引发硬件溢出。

.. list-table:: 常见色调映射算子特性对比矩阵
   :widths: 20 20 20 20 20
   :header-rows: 1
   :class: tight-table

   * - 算子名称
     - 计算复杂度
     - 画面反差倾向
     - 高光处理特性
     - 典型应用场景
   * - **Linear Clamp**
     - 极低 (单条指令)
     - 无压缩，硬性截断
     - 高光死白边缘锯齿
     - 仅用于管线调试与基准测试
   * - **Classic Reinhard**
     - 低 (1 次加法 1 次除法)
     - 较平，中间调发灰
     - 无限渐进收敛于 1.0
     - 性能受限平台、简单仿真
   * - **White-Preserving Reinhard**
     - 低 (2 乘 2 加 1 除)
     - 适中，高光受白点控制
     - 白点处达到绝对 1.0
     - 移动端渲染、通用 HDR 映射
   * - **Hable Filmic (Uncharted 2)**
     - 中等 (多项式代数运算)
     - 强电影感，足部与肩部清晰
     - 胶片式平滑高光滚降
     - 3A 游戏主机与 PC 渲染
   * - **ACES Fitted (Hill / Narkowicz)**
     - 中等 (矩阵变换 + 多项式)
     - 自然胶片响应，暗部紧实
     - 高光自然脱色与超宽色域压缩
     - 现代工业级渲染标配

------------------------------------------------------------------------
31.4 ACES 工业色彩管线与实时 Fitted 曲线微架构
------------------------------------------------------------------------

电影艺术与科学学院（AMPAS）制定的 **ACES (Academy Color Encoding System)** 是影视工业与现代顶级实时图形引擎（如 UE5 / Unity HDRP / Frostbite）的标准色彩管理体系。

ACES 体系色彩空间全景拓扑
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ACES 规范定义了多套针对不同生命周期的色彩空间标准：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       ACES 工业色彩体系转换拓扑                         |
   +-------------------------------------------------------------------------+

      [ 物理场景摄像机 / 光线追踪引擎 ]
                      |
                      | (输入设备转换 IDT / 颜色空间转换)
                      v
      [ ACES2065-1 (AP0 色域) ] : 超宽全色域，覆盖全可见光谱，用于母版封存与离线归档
                      |
                      | (线性变换矩阵: AP0 -> AP1)
                      v
      [ ACEScg (AP1 色域) ]     : 线性色彩空间，专为 3D 渲染、合成与 Shader 计算设计
                      |
                      | (艺术调色 LMT: Look Modification Transform)
                      v
      [ Reference Rendering Transform (RRT) ] : 核心美学变换 (S 曲线压缩 + 色调色调保持)
                      |
                      v
      [ Output Device Transform (ODT) ]       : 显示设备适配 (针对特定 SDR/HDR 显示器)
                      |
                      +------------+------------+
                      |                         |
                      v                         v
         [ Rec.709 / sRGB ODT ]       [ HDR10 Rec.2020 PQ ODT ]
         (传统 SDR 100 nits 显示器)    (现代 HDR 1000 nits 显示器)

- **AP0 原色系 (ACES2065-1)**：其三原色涵盖了 CIE 1931 全部可见光谱范围，甚至包含虚拟虚数原色，专用于无损档案保存；
- **AP1 原色系 (ACEScg / ACEScc)**：裁剪了 AP0 中的无意义虚原色，原色顶点更贴近真实物理发光体，消除了在计算交叉乘积与光照积分时的负值能量异常，是 3D 渲染计算的标准工作色域。

实时 ACES Fitted 近似拟合原理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

完整的 ACES RRT + ODT 变换涉及复杂的 3D 查找表（3D LUT）与高维非线性插值，在单通道实时后处理中开销较高。Krzysztof Narkowicz (2015) 与 Stephen Hill (2016) 分别推导了针对 sRGB / Rec.709 输出的精准有理多项式拟合公式。

Stephen Hill 基于 ACES 1.0 的双矩阵拟合方案是当今游戏工业最广泛采纳的工业实现：

1. **输入色彩空间变换（sRGB 线性空间 $	o$ ACES 线性空间）**：

.. math::

   \mathbf{C}_{	ext{ACES}} = \mathbf{M}_{	ext{sRGB\_to\_ACES}} \cdot \mathbf{C}_{	ext{in}}

其中变换矩阵 $\mathbf{M}_{	ext{sRGB\_to\_ACES}}$ 为：

.. math::

   \mathbf{M}_{	ext{sRGB\_to\_ACES}} = \begin{bmatrix}
   0.59719 & 0.35458 & 0.04823 \
   0.07600 & 0.90834 & 0.01566 \
   0.02840 & 0.13383 & 0.83777
   \end{bmatrix}

2. **RRT + ODT 联合 S 曲线多项式评估（针对各通道独立求值）**：

.. math::

   f_{	ext{ACES}}(v) = \frac{v \cdot (v + 0.0245786) - 0.000090537}{v \cdot (0.983729 \cdot v + 0.4329510) + 0.238081}

3. **输出色彩空间变换（ACES $	o$ sRGB 线性空间）**：

.. math::

   \mathbf{C}_{	ext{out}} = \mathbf{M}_{	ext{ACES\_to\_sRGB}} \cdot f_{	ext{ACES}}(\mathbf{C}_{	ext{ACES}})

其中逆变换矩阵 $\mathbf{M}_{	ext{ACES\_to\_sRGB}}$ 为：

.. math::

   \mathbf{M}_{	ext{ACES\_to\_sRGB}} = \begin{bmatrix}
    1.60475 & -0.53108 & -0.07367 \
   -0.10208 &  1.10813 & -0.00605 \
   -0.00327 & -0.07276 &  1.07602
   \end{bmatrix}

4. **饱和度防死白与极值截断**：最后执行 `saturate()` 确保输出严格落入 $[0.0, 1.0]$。

这一拟合公式不仅实现了平滑的高光压缩，而且通过输入输出矩阵的交叉混色，完美复刻了 ACES 标志性的“高光亮部向黄色/暖白色自然滚降”与“暗部对比度强化”的经典胶片观感。

------------------------------------------------------------------------
31.5 现代 HDR 显示输出适配与 Swapchain 管线配置
------------------------------------------------------------------------

当目标显示环境升级为原生硬件 HDR 显示器（如通过 HDMI 2.1 或 DisplayPort 1.4 连接的 OLED/Mini-LED 面板）时，渲染管线不能再使用将高光压扁到 1.0 的 SDR 曲线，而必须直接向系统呈现高动态范围的绝对亮度信号。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                 Windows / Vulkan HDR 原生输出管线架构                   |
   +-------------------------------------------------------------------------+

      [ 场景渲染线性 HDR (RGBA16F) ]
                    |
                    v
      [ HDR 专用色调映射 (HDR Display Mapping) ]
      (根据显示设备元数据 Peak Luminance 如 1000 nits, 仅将 >1000 nits 的超亮信号平滑压缩)
                    |
                    +--------------------------------+
                    |                                |
                    v (scRGB 路径: FP16)             v (HDR10 PQ 路径: R10G10B10A2)
      [ 线性比例缩放: 1.0 = 80 nits ]    [ Rec.2020 色域转换 + ST.2084 PQ 非线性编码 ]
                    |                                |
                    v                                v
      [ Swapchain: R16G16B16A16_FLOAT ] [ Swapchain: R10G10B10A2_UNORM ]
      [ ColorSpace: EXT_swapchain_colorspace [ ColorSpace: HDR10_ST2084_EXT ]
                    |                                |
                    +----------------+---------------+
                                     |
                                     v
                        [ 物理 HDR 显示面板解码点亮 ]

HDR 输出的两条主流工业路径
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **FP16 scRGB 线性路径 (Windows Advanced Color 标准)**：
   - **格式与色空间**：`DXGI_FORMAT_R16G16B16A16_FLOAT` + `DXGI_COLOR_SPACE_RGB_FULL_G10_NONE_P709`；
   - **物理定义**：保持 Rec.709 线性色域，数值 $(1.0, 1.0, 1.0)$ 严格定义为 **D65 标准参考白点（80 nits）**。因此，要输出 $1000 \, \mathrm{nits}$ 的峰值高光，着色器输出的数值直接为 $1000.0 / 80.0 = 12.5$；
   - **工程优势**：着色器无需处理非线性 PQ 编码，所有 UI 与 3D 场景合成均在线性加法空间完成，由 Windows DWM 桌面合成器统一接管向物理面板的转译。

2. **HDR10 (ST.2084 PQ + Rec.2020) 路径 (主机与跨平台标准)**：
   - **格式与色空间**：`DXGI_FORMAT_R10G10B10A2_UNORM` / `VK_FORMAT_A2R10G10B10_UNORM_PACK32` + `DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020` / `VK_COLOR_SPACE_HDR10_ST2084_EXT`；
   - **物理定义**：采用 ITU-R BT.2100 规范定义的 **感知量化传递函数 (Perceptual Quantizer - PQ / SMPTE ST 2084)**，绝对编码范围为 $0 \sim 10,000 \, \mathrm{nits}$；
   - **ST.2084 PQ 编码数学公式**（输入归一化物理亮度 $Y = L / 10000.0 \in [0, 1]$）：

.. math::

   N = \left( \frac{c_1 + c_2 Y^{m_1}}{1.0 + c_3 Y^{m_1}} \right)^{m_2}

其中标准常数为：$m_1 = \frac{2610}{16384} \approx 0.15930176$，$m_2 = \frac{2523}{4096} 	imes 128 \approx 78.84375$，$c_1 = \frac{3424}{4096} \approx 0.8359375$，$c_2 = \frac{2413}{4096} 	imes 32 \approx 18.8515625$，$c_3 = \frac{2392}{4096} 	imes 32 \approx 18.6875$。

UI 合成与纸白亮度 (Paper White)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 HDR 渲染管线中，若将传统 SDR UI 元素（如白色文字 $(1.0, 1.0, 1.0)$）直接输出到 HDR10 信号中，在 $1000 \, \mathrm{nits}$ 面板上会导致 UI 犹如刺眼探照灯，引起用户剧烈视觉疲劳。

工业标准引入 **纸白亮度 (Paper White Luminance，通常设为 $200 \sim 250 \, \mathrm{nits}$)** 参数：
- 场景 3D 渲染画面允许冲上物理极限（$1000 \sim 4000 \, \mathrm{nits}$）；
- 静态 2D UI 的白色峰值被严格钳制在 Paper White 对应的量化级别（如 scRGB 下输出 $200.0 / 80.0 = 2.5$），确保 UI 清晰可辨而不刺眼。

------------------------------------------------------------------------
31.6 工业级 HLSL / Compute Shader 自动曝光与色调映射完整实现
------------------------------------------------------------------------

以下是符合 DirectX 12 / Vulkan 工业规范的完整 HLSL 6.5+ 源码，包含 **256-Bin 对数亮度直方图自动曝光 Compute Shader** 与 **集成 ACES Fitted / HDR10 适配的后处理色调映射着色器**：

.. code-block:: hlsl

   // =========================================================================
   // File: PostProcess_AutoExposure_ToneMapping.hlsl
   // Standard: HLSL 6.5+ (DX12 / Vulkan via DXC)
   // Architecture: 256-Bin Log Histogram Auto-Exposure + ACES Fitted Tone Mapping
   // =========================================================================

   #define HISTOGRAM_BINS 256
   #define THREADS_X 16
   #define THREADS_Y 16

   struct ToneMappingConstants {
       float2 RenderTargetSize;
       float2 RcpRenderTargetSize;
       
       float  MinLogLuminance;   // 默认: -8.0
       float  MaxLogLuminance;   // 默认: +8.0
       float  LogLuminanceRange; // Max - Min
       float  RcpLogLuminanceRange;
       
       float  ExposureCompensationStops; // 曝光补偿 (EV stops)
       float  DeltaTime;                 // 帧时间 (秒)
       float  AdaptationSpeedUp;         // 亮适应速率 (如 2.5)
       float  AdaptationSpeedDown;       // 暗适应速率 (如 1.0)
       
       float  PaperWhiteNits;    // HDR UI 纸白亮度 (如 200.0)
       float  MaxDisplayNits;    // 显示器最大峰值亮度 (如 1000.0)
       uint   DisplayMode;       // 0: SDR sRGB, 1: HDR scRGB, 2: HDR10 ST2084
       uint   ToneMapperType;    // 0: ACES Fitted, 1: Hable Filmic, 2: Reinhard
   };

   ConstantBuffer<ToneMappingConstants> g_CB : register(b0);

   Texture2D<float4>   g_HDRSceneTexture     : register(t0);
   Texture2D<float>    g_AdaptedLuminanceTex : register(t1); // 1x1 R32F
   SamplerState        g_LinearClampSampler  : register(s0);

   RWStructuredBuffer<uint> g_RWHistogramBuffer   : register(u0);
   RWTexture2D<float>       g_RWAdaptedLuminance  : register(u1); // 1x1 R32F
   RWTexture2D<float4>      g_RWOutputDisplay     : register(u2);

   // -------------------------------------------------------------------------
   // 工具函数: 颜色空间与亮度计算
   // -------------------------------------------------------------------------
   float CalculateLuminance(float3 linearRGB) {
       return dot(linearRGB, float3(0.2126f, 0.7152f, 0.0722f));
   }

   uint FloatLuminanceToHistogramBin(float luma) {
       if (luma < 0.0001f) return 0;
       float logLuma = log2(luma);
       float norm = saturate((logLuma - g_CB.MinLogLuminance) * g_CB.RcpLogLuminanceRange);
       return (uint)(norm * 254.0f + 1.0f);
   }

   float HistogramBinToFloatLuminance(float binIndex) {
       if (binIndex <= 0.5f) return 0.0f;
       float norm = (binIndex - 1.0f) / 254.0f;
       return exp2(norm * g_CB.LogLuminanceRange + g_CB.MinLogLuminance);
   }

   // -------------------------------------------------------------------------
   // Pass 1: Compute Shader 构建 256-Bin 对数亮度直方图
   // -------------------------------------------------------------------------
   groupshared uint s_GroupHistogram[HISTOGRAM_BINS];

   [numthreads(THREADS_X, THREADS_Y, 1)]
   void CS_BuildHistogram(uint3 groupID : SV_GroupID,
                          uint3 groupThreadID : SV_GroupThreadID,
                          uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       uint localIndex = groupThreadID.y * THREADS_X + groupThreadID.x;
       if (localIndex < HISTOGRAM_BINS) {
           s_GroupHistogram[localIndex] = 0;
       }
       GroupMemoryBarrierWithGroupSync();

       if (dispatchThreadID.x < (uint)g_CB.RenderTargetSize.x && 
           dispatchThreadID.y < (uint)g_CB.RenderTargetSize.y) 
       {
           float3 color = g_HDRSceneTexture.Load(int3(dispatchThreadID.xy, 0)).rgb;
           float  luma  = CalculateLuminance(color);
           uint   bin   = FloatLuminanceToHistogramBin(luma);
           InterlockedAdd(s_GroupHistogram[bin], 1);
       }
       GroupMemoryBarrierWithGroupSync();

       if (localIndex < HISTOGRAM_BINS) {
           InterlockedAdd(g_RWHistogramBuffer[localIndex], s_GroupHistogram[localIndex]);
       }
   }

   // -------------------------------------------------------------------------
   // Pass 2: 汇总直方图、百分位截断与时域曝光平滑适应
   // -------------------------------------------------------------------------
   [numthreads(HISTOGRAM_BINS, 1, 1)]
   void CS_AdaptExposure(uint threadIndex : SV_GroupIndex)
   {
       // 单线程组执行 256 个 bin 的加权求和
       groupshared float s_BinCounts[HISTOGRAM_BINS];
       s_BinCounts[threadIndex] = (float)g_RWHistogramBuffer[threadIndex];
       g_RWHistogramBuffer[threadIndex] = 0; // 重置全局直方图供下一帧使用
       GroupMemoryBarrierWithGroupSync();

       if (threadIndex == 0) {
           float totalPixels = 0.0f;
           for (uint i = 0; i < HISTOGRAM_BINS; ++i) {
               totalPixels += s_BinCounts[i];
           }

           // 百分位截断: 剔除暗部 10% 与高光 5% 噪点
           float minPixels = totalPixels * 0.10f;
           float maxPixels = totalPixels * 0.95f;

           float weightedLumaSum = 0.0f;
           float validPixels = 0.0f;
           float accumulated = 0.0f;

           for (uint j = 0; j < HISTOGRAM_BINS; ++j) {
               float count = s_BinCounts[j];
               float prevAcc = accumulated;
               accumulated += count;

               // 计算落入有效百分位区间内的权重分量
               float validCount = count;
               if (accumulated <= minPixels || prevAcc >= maxPixels) {
                   validCount = 0.0f;
               } else {
                   if (prevAcc < minPixels) validCount -= (minPixels - prevAcc);
                   if (accumulated > maxPixels) validCount -= (accumulated - maxPixels);
               }

               if (validCount > 0.0f) {
                   float binLuma = HistogramBinToFloatLuminance((float)j);
                   weightedLumaSum += binLuma * validCount;
                   validPixels += validCount;
               }
           }

           float targetLuma = (validPixels > 0.001f) ? (weightedLumaSum / validPixels) : 1.0f;
           targetLuma = max(targetLuma, 0.0001f);

           // 读取上一帧平滑亮度
           float lastLuma = g_AdaptedLuminanceTex.Load(int3(0, 0, 0));
           float adaptSpeed = (targetLuma > lastLuma) ? g_CB.AdaptationSpeedUp : g_CB.AdaptationSpeedDown;
           float adaptedLuma = lastLuma + (targetLuma - lastLuma) * (1.0f - exp(-g_CB.DeltaTime * adaptSpeed));

           g_RWAdaptedLuminance[uint2(0, 0)] = max(adaptedLuma, 0.0001f);
       }
   }

   // -------------------------------------------------------------------------
   // Stephen Hill ACES Fitted 算法实现
   // -------------------------------------------------------------------------
   float3 RRTAndODTFit(float3 v) {
       float3 a = v * (v + 0.0245786f) - 0.000090537f;
       float3 b = v * (0.983729f * v + 0.4329510f) + 0.238081f;
       return a / b;
   }

   float3 ACESFittedToneMapping(float3 linearColor) {
       // sRGB to ACEScg 矩阵
       const float3x3 sRGB_to_ACES = float3x3(
           0.59719f, 0.35458f, 0.04823f,
           0.07600f, 0.90834f, 0.01566f,
           0.02840f, 0.13383f, 0.83777f
       );

       // ACEScg to sRGB 矩阵
       const float3x3 ACES_to_sRGB = float3x3(
            1.60475f, -0.53108f, -0.07367f,
           -0.10208f,  1.10813f, -0.00605f,
           -0.00327f, -0.07276f,  1.07602f
       );

       float3 aces = mul(sRGB_to_ACES, linearColor);
       float3 oces = RRTAndODTFit(aces);
       float3 rgb  = mul(ACES_to_sRGB, oces);
       return saturate(rgb);
   }

   // -------------------------------------------------------------------------
   // ST.2084 (PQ) 编码函数
   // -------------------------------------------------------------------------
   float3 LinearToST2084(float3 linearNits) {
       float3 Y = saturate(linearNits / 10000.0f);
       float  m1 = 2610.0f / 16384.0f;
       float  m2 = (2523.0f / 4096.0f) * 128.0f;
       float  c1 = 3424.0f / 4096.0f;
       float  c2 = (2413.0f / 4096.0f) * 32.0f;
       float  c3 = (2392.0f / 4096.0f) * 32.0f;

       float3 Y_m1 = pow(Y, m1);
       float3 num  = c1 + c2 * Y_m1;
       float3 den  = 1.0f + c3 * Y_m1;
       return pow(num / den, m2);
   }

   // -------------------------------------------------------------------------
   // Pass 3: 全屏色调映射与显示编码 Pixel / Compute Shader
   // -------------------------------------------------------------------------
   [numthreads(16, 16, 1)]
   void CS_ToneMappingMain(uint3 dispatchThreadID : SV_DispatchThreadID)
   {
       uint2 pixelCoord = dispatchThreadID.xy;
       if (pixelCoord.x >= (uint)g_CB.RenderTargetSize.x || 
           pixelCoord.y >= (uint)g_CB.RenderTargetSize.y) return;

       float3 sceneLinear = g_HDRSceneTexture.Load(int3(pixelCoord, 0)).rgb;
       float  adaptedLuma = g_AdaptedLuminanceTex.Load(int3(0, 0, 0));

       // 计算基于中灰校准的曝光系数
       float middleGray = 0.18f;
       float exposureScale = (middleGray / max(adaptedLuma, 0.0001f)) * exp2(g_CB.ExposureCompensationStops);
       float3 exposedColor = sceneLinear * exposureScale;

       float3 finalColor = float3(0, 0, 0);

       if (g_CB.DisplayMode == 0) // SDR sRGB 路径
       {
           if (g_CB.ToneMapperType == 0) {
               finalColor = ACESFittedToneMapping(exposedColor);
           } else {
               // White-Preserving Reinhard (白点 = 4.0)
               float w2 = 16.0f;
               finalColor = (exposedColor * (1.0f + exposedColor / w2)) / (1.0f + exposedColor);
           }
           // 硬件 Swapchain 会自动执行 sRGB OETF，着色器输出线性 Display-Referred
       }
       else if (g_CB.DisplayMode == 1) // HDR scRGB 路径 (FP16 线性, 80 nits = 1.0)
       {
           // 仅对超过显示器峰值的高光实施软肩部压缩
           float maxLinearVal = g_CB.MaxDisplayNits / 80.0f;
           finalColor = exposedColor * (g_CB.PaperWhiteNits / 80.0f);
           // 渐进式肩部压缩
           finalColor = (finalColor * (1.0f + finalColor / (maxLinearVal * maxLinearVal))) / (1.0f + finalColor);
       }
       else // HDR10 (ST2084 PQ + Rec.2020) 路径
       {
           float3 linearNits = exposedColor * g_CB.PaperWhiteNits;
           finalColor = LinearToST2084(linearNits);
       }

       g_RWOutputDisplay[pixelCoord] = float4(finalColor, 1.0f);
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了现代实时渲染管线中从高动态范围场景信号到显示设备的色彩与亮度转译体系：
1. **色彩空间范式转换**：严格确立了 Scene-Referred 线性无界空间与 Display-Referred 有限感知空间的物理边界与职责分工；
2. **物理曝光与直方图自适应**：从摄影 $\mathrm{EV}_{100}$ 参数模型出发，推导了基于 Compute Shader 256-bin 对数亮度直方图的抗噪点自动曝光与非对称人眼时域适应算法；
3. **色调映射算子全景**：数学推导了 Reinhard 扩展型、John Hable Filmic S 曲线，剖析了逐通道脱色与亮度保持映射在色相保真度上的本质权衡；
4. **ACES 工业色彩标准**：深入解构了 AP0 / AP1 色域体系、RRT + ODT 变换流，并推导了 Stephen Hill 工业级高精度双矩阵有理多项式拟合方案；
5. **现代 HDR 输出架构**：详尽对比了 Windows scRGB FP16（80 nits 线性基准）与 HDR10 ST.2084 PQ 非线性编码的 Swapchain 配置与 UI 纸白（Paper White）隔离保护机制。

在下一章（Chapter 32）中，我们将深入剖析 **物理泛光 (Bloom) 与景深 (Depth of Field) 模拟**。我们将详细推导 **Dual-Kawase 降采样金字塔滤波、高光光晕能量扩散物理模型，以及基于弥散圆 (Circle of Confusion - CoC) 的薄透镜相机几何光学与散景 (Bokeh) 实时计算微架构**，敬请期待！
