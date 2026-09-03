========================================================================
Chapter 23: 软阴影过滤技术：PCF、PCSS 与指数阴影贴图 (ESM/VSM)
========================================================================

.. note:: 前置背景与认知承接
   在前两章中，我们系统剖析了两阶段阴影映射（Two-Pass Shadow Mapping）的数学管线、斜率比例深度偏差（Slope-Scaled Bias）与法线偏移偏差消除 Acne 的机理，并通过级联阴影贴图（CSM）有效解决了开放大场景下的视锥体透视走样（Perspective Aliasing）矛盾。然而，传统 Shadow Map 本质上建立在**理想点光源（Point Light）或理想平行光（Directional Light）**的假设之上，无论贴图分辨率多高，生成的阴影边缘均为非黑即白的锐利硬边（Hard Shadows）。

   在真实的物理光学世界中，所有发光源均具有非零的几何物理尺寸（面积光/体积光，如太阳视直径约为 $0.53^\circ$）。几何体投射出的阴影由中心全遮挡的**本影区（Umbra）**与边缘部分遮挡的**半影区（Penumbra）**构成，且半影宽度严格遵循物距-像距相似三角形几何律，呈现出随遮挡距离增加而逐渐模糊扩散的**接触硬化（Contact Hardening）**现象。本章将系统解构软阴影的光学物理本质，推导百分比临近滤波（Percentage-Closer Filtering - PCF）、基于物理的接触硬化软阴影（PCSS）三阶段搜寻算法，以及允许阴影贴图直接进行空间预滤波卷积的统计阴影模型（Variance Shadow Maps - VSM 与 Exponential Shadow Maps - ESM/EVSM），并交付工业级 HLSL 着色器实现。

------------------------------------------------------------------------
23.1 面积光源与半影 (Penumbra) 的光学几何物理本质
------------------------------------------------------------------------

在面积光源照射下，阴影区域的可见性并非二值判定，而是光源表面积在受遮挡过程中的积分覆盖率：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                面积光源、遮挡物与接收面之间的光学半影几何投射           |
   +-------------------------------------------------------------------------+

              面积光源 (Area Light) [宽度 W_light]
            |-----------------------------|
            \                             /
             \                           /
              \                         /
               \      遮挡物 (Blocker) /
                \    |---------------|/
                 \   |  [深度 d_b]   |
                  \  |               |\
                   \ |               | \
                    \|               |  \
                     +---------------+   \
                    /                 \   \
                   /                   \   \
                  /     本影 (Umbra)    \   \
                 /   [完全遮挡, 强黑]    \   \
                /                         \   \  半影 (Penumbra)
               /                           \   \ [部分遮挡, 渐变过渡]
              /                             \   \
   =====================================================================
   接收面 (Receiver) [深度 d_r]

半影尺寸 (Penumbra Width) 的相似三角形严格数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设面积光源在光源观察空间具有物理宽度 $W_{	ext{light}}$，遮挡物到光源的垂直距离为 $d_{	ext{blocker}}$，着色点（接收面）到光源的垂直距离为 $d_{	ext{receiver}}$。

根据相似三角形几何光学原理：

.. math::

   \frac{W_{	ext{penumbra}}}{W_{	ext{light}}} = \frac{d_{	ext{receiver}} - d_{	ext{blocker}}}{d_{	ext{blocker}}}

导出着色点处半影区域的物理宽度 $W_{	ext{penumbra}}$：

.. math::

   W_{	ext{penumbra}} = \left( \frac{d_{	ext{receiver}} - d_{	ext{blocker}}}{d_{	ext{blocker}}} \right) \cdot W_{	ext{light}}

从公式可推导两大关键物理性质：
1. **接触硬化（Contact Hardening）**：当接收面紧贴遮挡物时（$d_{	ext{receiver}} 	o d_{	ext{blocker}}$），$W_{	ext{penumbra}} 	o 0$，阴影呈现极其锐利的硬边缘（如脚底、桌腿接触地面处）；
2. **渐进软化（Progressive Softening）**：当接收面远离遮挡物时（$d_{	ext{receiver}} \gg d_{	ext{blocker}}$），半影宽度随相对距离呈线性放大扩散，阴影边缘高度柔化弥散（如高处树冠投射到地面的树影）。

.. list-table:: 软阴影四大技术路线对比矩阵
   :widths: 15 25 25 35
   :header-rows: 1
   :class: tight-table

   * - 算法名称
     - 核心原理
     - 物理保真度
     - 性能开销与硬件特征
   * - **PCF (百分比临近滤波)**
     - 固定滤波核内多次深度比较并取平均
     - 伪软阴影（全局均一虚化，无接触硬化）
     - 开销低至中等；硬件原生支持（$2 	imes 2$ 硬件 PCF 采样器）
   * - **PCSS (接触硬化软阴影)**
     - 遮挡搜寻 + 半影估算 + 变核 PCF
     - 逼近真实面积光（物理级接触硬化）
     - 需多次动态纹理采样（32~64 taps），带宽与 ALU 消耗高
   * - **VSM (方差阴影贴图)**
     - 存储深度的一阶/二阶矩，利用切比雪夫不等式估算可见度
     - 支持全局模糊与各向异性过滤
     - 仅需 1 次纹理采样，但存在严重的**漏光（Light Bleeding）**瑕疵
   * - **ESM / EVSM (指数方差阴影)**
     - 指数空间线性化与双向指数矩拟合
     - 彻底压制漏光，边缘过渡极为柔和
     - 需 FP32 高精度纹理，计算指数有一定溢出风险

------------------------------------------------------------------------
23.2 百分比临近滤波 (Percentage-Closer Filtering - PCF) 深度剖析
------------------------------------------------------------------------

PCF（Reeves et al., 1987）是实时渲染中最经典的阴影抗锯齿与伪软阴影滤波算法。其核心准则是：**过滤深度比较的结果，绝不能过滤深度值本身！**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |            PCF 核心本质: 比较后滤波 vs 错误深度预滤波的灾难对比         |
   +-------------------------------------------------------------------------+

   [ 错误路线: 预先对深度图做高斯模糊 (Pre-filtering Depth Map) ]
   物体 A 深度 = 10m, 物体 B 深度 = 100m -> 模糊后交界处深度 = 55m!
   * 结果: 在空间中凭空捏造了一个 55m 处的虚拟遮挡物!
   * 产生极其严重的深度穿透、阴影断裂与形状变形 (Depth Invalidation).

   [ 正确路线: 百分比临近滤波 (PCF) ]
   1. 保持 Shadow Map 原始离散深度完全不变;
   2. 在着色点周围邻域内采集 N 个采样点;
   3. 对每个采样点独立执行深度比较: C_i = (Depth_map[p_i] + bias >= z_receiver) ? 1.0 : 0.0;
   4. 对 N 个二值布尔结果求加权平均值: ShadowFactor = sum(C_i * w_i) / sum(w_i);
   * 结果: 完美生成 [0.0, 1.0] 的连续半影平滑过渡因子!

PCF 数学积分表达与离散卷积
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设着色点在光源投影空间归一化坐标为 $(u, v, z_{	ext{receiver}})$，滤波核为 $\Omega$，连续滤波表达为：

.. math::

   S_{	ext{pcf}}(u, v) = \iint_{\Omega} H\Big( D(u + \Delta u, v + \Delta v) + 	ext{bias} - z_{	ext{receiver}} \Big) \cdot K(\Delta u, \Delta v) \, d\Delta u \, d\Delta v

其中 $H(x)$ 为 Heaviside 阶跃函数（$x \ge 0$ 时为 1，否则为 0），$K$ 为归一化核权重函数。

离散泊松圆盘采样 (Poisson Disk Sampling)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在均匀规则网格（Regular Grid）上采样 PCF 会在阴影边缘引入明显的横平竖直结构化网格条纹。工业级实现普遍采用**泊松圆盘分布（Poisson Disk Distribution）**或**沃格尔螺旋圆盘（Vogel Disk）**，使采样点具有蓝噪声（Blue Noise）的高频无方向随机特性。

Vogel Disk 参数化生成方程：

.. math::

   r_i = \sqrt{\frac{i + 0.5}{N}}, \quad 	heta_i = i \cdot \phi_{	ext{golden}} = i \cdot 2.39996323\,	ext{rad} \quad (i \in [0, N-1])

.. math::

   \Delta u_i = r_i \cdot \cos	heta_i \cdot R_{	ext{filter}}, \quad \Delta v_i = r_i \cdot \sin	heta_i \cdot R_{	ext{filter}}

为了将低采样数（如 16 taps）下的高频噪点转化为均匀随机抖动，着色器利用屏幕空间像素坐标索引交错梯度噪声（Interleaved Gradient Noise - IGN）对 Vogel 采样圆盘进行逐像素随机旋转，再结合时域抗锯齿（TAA）实现零噪波收敛。

------------------------------------------------------------------------
23.3 接触硬化软阴影 (PCSS - Percentage-Closer Soft Shadows) 完整推导
------------------------------------------------------------------------

PCSS（Randi Fernando, 2005）通过在着色器中动态模拟面积光几何投影，实现了物理精准的接触硬化效果。算法严格由三大顺序阶段构成：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                    PCSS 算法三阶段物理计算数据流图                      |
   +-------------------------------------------------------------------------+

   [ 阶段 1: 遮挡物搜寻 (Blocker Search) ]
   输入: 接收点深度 d_r, 光源物理尺寸 W_light
   1. 根据光源锥体计算搜寻半径 R_search = (d_r - z_near) / d_r * W_light;
   2. 在 R_search 范围内采样 N_1 个深度点;
   3. 筛选所有满足 D_i < d_r - bias 的点 (真实遮挡物);
   4. 计算平均遮挡深度: d_avg_blocker = sum(D_blocker) / Count;
        |
        v [ 若 Count == 0: 彻底无遮挡, 提前退出返回 1.0 ]
        |
   [ 阶段 2: 半影宽度估计 (Penumbra Estimation) ]
   1. 应用相似三角形方程: w_penumbra = (d_r - d_avg_blocker) / d_avg_blocker * W_light;
   2. 将世界半影宽度换算为 Shadow Map UV 空间滤波半径: R_filter = w_penumbra * (z_near / d_r);
        |
        v
   [ 阶段 3: 自适应变核 PCF 滤波 (Filtering) ]
   1. 以动态计算的 R_filter 为半径设置 Vogel Disk;
   2. 在 R_filter 范围内执行 N_2 次 PCF 采样深度测试;
   3. 输出最终接触硬化阴影因子 S in [0.0, 1.0].

PCSS 遮挡搜寻半径与滤波半径的严格推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **搜寻半径 $R_{	ext{search}}$**：
   面积光源向着色点聚焦形成一个视锥体，该视锥体在 Shadow Map 近平面（近裁剪面 $z_{	ext{near}}$）上截取的圆形区域半径为：

.. math::

   R_{	ext{search}} = W_{	ext{light}} \cdot \frac{d_{	ext{receiver}} - z_{	ext{near}}}{d_{	ext{receiver}}}

2. **自适应滤波半径 $R_{	ext{filter}}$**：
   由阶段 1 求得平均遮挡物深度 $d_{	ext{avg\_blocker}}$ 后，半影尺寸投影到近平面上的滤波核半径为：

.. math::

   R_{	ext{filter}} = W_{	ext{light}} \cdot \left( \frac{d_{	ext{receiver}} - d_{	ext{avg\_blocker}}}{d_{	ext{avg\_blocker}}} \right) \cdot \frac{z_{	ext{near}}}{d_{	ext{receiver}}}

.. list-table:: PCSS 关键参数与硬件性能权衡
   :widths: 25 25 50
   :header-rows: 1
   :class: tight-table

   * - 参数项
     - 典型工程取值
     - 物理与性能影响
   * - **$W_{	ext{light}}$ (光源物理尺寸)**
     - $0.02 \sim 0.1$ (归一化空间)
     - 决定半影扩散的最大剧烈程度；过大易导致远景半影欠采样噪波
   * - **$N_1$ (Blocker 采样数)**
     - $16 \sim 25$ taps
     - 决定平均遮挡深度估计的准确度；不足会导致半影尺寸跳变
   * - **$N_2$ (Filter 采样数)**
     - $32 \sim 64$ taps
     - 决定大半影模糊区域的平滑度；直接主导像素着色器纹理带宽消耗

------------------------------------------------------------------------
23.4 统计与指数阴影贴图体系：方差阴影 (VSM) 与指数阴影 (ESM/EVSM)
------------------------------------------------------------------------

PCF 与 PCSS 的核心痛点在于**无法对 Shadow Map 预先生成 Mipmap 或应用各向异性过滤**，导致大量离散采样开销。统计阴影贴图从根本上颠覆了这一限制。

方差阴影贴图 (Variance Shadow Maps - VSM) 与切比雪夫不等式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

VSM（Donnelly & Lauritzen, 2006）将深度视作随机变量 $x$，在双通道纹理（`R32G32_FLOAT`）中分别存储深度的一阶矩与二阶矩：

.. math::

   M_1 = E[x] = z, \quad M_2 = E[x^2] = z^2

**核心突破**：由于期望算子是线性的（$E[A + B] = E[A] + E[B]$），**VSM 可以被硬件直接进行双线性插值、高斯模糊卷积、生成 Mipmap 以及 SAT 盒式均值加速！**

当滤波后的矩为 $(M_1, M_2)$ 时，局部深度分布的均值与方差为：

.. math::

   \mu = M_1, \quad \sigma^2 = M_2 - M_1^2

根据单侧切比雪夫不等式（One-Tailed Chebyshev's Inequality），对于任意大于均值的接收深度 $t = z_{	ext{receiver}}$（$t > \mu$），其不可见（被遮挡）概率上限为：

.. math::

   P(x \ge t) \le p_{\max}(t) = \frac{\sigma^2}{\sigma^2 + (t - \mu)^2}

因此，非遮挡可见度因子 $S_{	ext{vsm}}$ 表达为：

.. math::

   S_{	ext{vsm}} = 
   \begin{cases}
   1.0, & 	ext{if } z_{	ext{receiver}} \le \mu \
   \frac{\sigma^2}{\sigma^2 + (z_{	ext{receiver}} - \mu)^2}, & 	ext{if } z_{	ext{receiver}} > \mu
   \end{cases}

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     VSM 漏光 (Light Bleeding) 的物理成因                |
   +-------------------------------------------------------------------------+

   [ 场景构成: 近景遮挡物 A (z=10m) + 远景遮挡物 B (z=90m), 接收面 C (z=100m) ]
   1. 卷积核同时覆盖 A 与 B:
      M_1 = 0.5 * 10 + 0.5 * 90 = 50m
      M_2 = 0.5 * 100 + 0.5 * 8100 = 4100
      方差 sigma^2 = 4100 - 50^2 = 1600 (极大的方差!)
   2. 评估接收面 C (z=100m) 的切比雪夫可见度:
      S = 1600 / (1600 + (100 - 50)^2) = 1600 / (1600 + 2500) = 0.39!
   * 致命缺陷: 接收面原本处于绝对全黑的本影中, 却凭空获得了 39% 的光照!
   * 现象: 阴影内部呈现幽灵般的透光高亮 (Light Bleeding).

指数阴影贴图 (Exponential Shadow Maps - ESM)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了根除 VSM 的漏光缺陷，ESM（Salvi, 2008）采用指数函数对阶跃可见性进行单调逼近：

.. math::

   S_{	ext{esm}}(z, d) \approx \exp\Big( -k \cdot (z_{	ext{receiver}} - D(x,y)) \Big) = \exp(-k \cdot z_{	ext{receiver}}) \cdot \exp(k \cdot D(x,y))

在单通道贴图中存储 $\exp(k \cdot D)$（其中 $k \in [40, 80]$ 为锐度常数）。着色时仅需单次采样：

.. math::

   S = 	ext{saturate}\Big( \exp(k \cdot D_{	ext{filtered}}) \cdot \exp(-k \cdot z_{	ext{receiver}}) \Big)

ESM 彻底消除了切比雪夫方差过大引起的漏光，且仅需单通道显存，但在大景深场景下需要防范浮点溢出（$\exp(80) \approx 5.5 	imes 10^{34}$）。

------------------------------------------------------------------------
23.5 工业级 HLSL 接触硬化 PCSS 着色器完整实现
------------------------------------------------------------------------

以下是符合现代 DX12 / Vulkan 标准的工业级 PCSS 着色器实现，集成 Vogel Disk 采样、交错梯度噪声旋转与遮挡物提前退出机制：

.. code-block:: hlsl

   // HLSL: 工业级 PCSS (Percentage-Closer Soft Shadows) 完整实现
   // 架构特性: 3 阶段流水线 + Vogel Disk 蓝噪声采样 + 逐像素 IGN 随机旋转 + 早期剔除

   Texture2D<float> g_ShadowMap : register(t0);
   SamplerState g_PointClampSampler : register(s0);
   SamplerComparisonState g_ShadowCompSampler : register(s1);

   cbuffer PCSSConstantBuffer : register(b1) {
       float4x4 g_LightViewProj;
       float4   g_LightParams;       // (LightSizeWS, NearPlane, ShadowMapResolution, 1.0/ShadowMapResolution)
       float4   g_SampleCounts;      // (BlockerSearchSamples, PCFSamples, DepthBias, NormalBias)
   };

   // 交错梯度噪声 (Interleaved Gradient Noise - IGN)
   float InterleavedGradientNoise(float2 screenPos) {
       float3 magic = float3(0.06711056f, 0.00583715f, 52.9829189f);
       return frac(magic.z * frac(dot(screenPos, magic.xy)));
   }

   // 2D 向量旋转
   float2 RotateVector(float2 v, float cosAngle, float sinAngle) {
       return float2(v.x * cosAngle - v.y * sinAngle, v.x * sinAngle + v.y * cosAngle);
   }

   // Vogel 螺旋采样点生成
   float2 GetVogelDiskSample(int sampleIndex, int totalSamples, float phi) {
       float goldenAngle = 2.39996323f; // 黄金角弧度
       float r = sqrt((float(sampleIndex) + 0.5f) / float(totalSamples));
       float theta = float(sampleIndex) * goldenAngle + phi;
       return float2(r * cos(theta), r * sin(theta));
   }

   // 阶段 1: 搜寻平均遮挡物深度
   bool FindAverageBlockerDepth(
       float2 shadowUV, 
       float receiverDepth, 
       float searchRadiusUV, 
       float rotationAngle,
       out float avgBlockerDepth)
   {
       int blockerCount = 0;
       float blockerSum = 0.0f;
       int sampleCount = (int)g_SampleCounts.x; // 如 16 taps

       float cosA = cos(rotationAngle);
       float sinA = sin(rotationAngle);
       float depthBias = g_SampleCounts.z;

       for (int i = 0; i < sampleCount; ++i) {
           float2 offset = GetVogelDiskSample(i, sampleCount, rotationAngle);
           float2 sampleUV = shadowUV + offset * searchRadiusUV;

           float sampleDepth = g_ShadowMap.SampleLevel(g_PointClampSampler, sampleUV, 0).r;
           if (sampleDepth < receiverDepth - depthBias) {
               blockerSum += sampleDepth;
               blockerCount++;
           }
       }

       if (blockerCount == 0) {
           avgBlockerDepth = 0.0f;
           return false; // 完全无遮挡
       }

       avgBlockerDepth = blockerSum / float(blockerCount);
       return true;
   }

   // PCSS 主入口解算函数
   float CalculatePCSS(float3 worldPos, float3 worldNormal, float2 screenPos) {
       // 1. 变换至光源投影空间
       float4 lightClipPos = mul(g_LightViewProj, float4(worldPos, 1.0f));
       float3 lightNDC = lightClipPos.xyz / lightClipPos.w;
       float2 shadowUV = float2(lightNDC.x * 0.5f + 0.5f, -lightNDC.y * 0.5f + 0.5f);
       float receiverDepth = lightNDC.z;

       if (shadowUV.x < 0.0f || shadowUV.x > 1.0f || 
           shadowUV.y < 0.0f || shadowUV.y > 1.0f || 
           receiverDepth > 1.0f) {
           return 1.0f;
       }

       // 2. 逐像素随机噪声角度
       float dither = InterleavedGradientNoise(screenPos);
       float rotationAngle = dither * 6.2831853f;

       float lightSizeWS = g_LightParams.x;
       float nearPlane   = g_LightParams.y;

       // 3. 计算遮挡物搜寻半径
       float searchRadiusUV = (receiverDepth - nearPlane) / receiverDepth * (lightSizeWS / 2048.0f);

       // 4. 阶段 1: 执行遮挡物搜寻
       float avgBlockerDepth = 0.0f;
       if (!FindAverageBlockerDepth(shadowUV, receiverDepth, searchRadiusUV, rotationAngle, avgBlockerDepth)) {
           return 1.0f; // 无遮挡物，完全受光
       }

       // 5. 阶段 2: 估算半影宽度并换算为滤波半径
       float penumbraRatio = (receiverDepth - avgBlockerDepth) / avgBlockerDepth;
       float filterRadiusUV = penumbraRatio * lightSizeWS * (nearPlane / receiverDepth) * (1.0f / 2048.0f);

       // 限制最小与最大滤波半径
       float minFilterRadius = 1.0f / g_LightParams.z; // 至少 1 个纹素
       filterRadiusUV = clamp(filterRadiusUV, minFilterRadius, 0.05f);

       // 6. 阶段 3: 执行变核 PCF 采样
       float shadowSum = 0.0f;
       int pcfSamples = (int)g_SampleCounts.y; // 如 32 taps
       float depthBias = g_SampleCounts.z;

       for (int j = 0; j < pcfSamples; ++j) {
           float2 offset = GetVogelDiskSample(j, pcfSamples, rotationAngle);
           float2 sampleUV = shadowUV + offset * filterRadiusUV;

           // 硬件级深度比较采样
           shadowSum += g_ShadowMap.SampleCmpLevelZero(
               g_ShadowCompSampler, 
               sampleUV, 
               receiverDepth - depthBias
           );
       }

       return shadowSum / float(pcfSamples);
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从面积光源与相似三角形几何光学出发，系统解构了半影尺寸与接触硬化（Contact Hardening）的数学物理大厦；深入剖析了百分比临近滤波（PCF）的比较后平均准则与 Vogel 蓝噪声圆盘采样；完整推导了 PCSS 遮挡搜寻、半影估算与变核滤波三阶段流水线；并全面对比了允许直接进行空间模糊预卷积的统计阴影体系（VSM/ESM/EVSM）及其漏光抑制策略。

然而，在包含海量动态网格体与数千个几何组件的工业级 3D 场景中，仅优化阴影与像素着色远远不够。若将所有不可见的多边形全部送入光栅化流水线，GPU 前端图元装配与顶点着色将瞬间遭遇性能过载。下一章我们将深入现代图形引擎的骨干中枢——**全局可见性剔除：视锥体裁剪、遮挡查询 (Occlusion Query)、软件光栅化剔除与分层 Z 缓冲 (Hi-Z)**，解构千万级多边形如何在进入管线前被纳秒级剔除的极致工程实践。
