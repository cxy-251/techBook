========================================================================
Chapter 18: 工业级 PBR 材质模型：金属度/粗糙度与镜面反射/光泽度工作流解析
========================================================================

.. note:: 前置背景与认知承接
   前一章深入推导了 Cook-Torrance 微表面镜面反射模型中的三大核心项（GGX 法线分布 $D$ 项、高度相关 Smith 几何遮蔽 $V$ 项以及 Fresnel-Schlick 菲涅尔 $F$ 项）及其第一性原理积分推导。在工业级商业引擎（Unreal Engine 5、Unity HDRP、Filament、Frostbite、Substance 3D）与图形渲染管线架构中，微观物理反射方程必须转化为标准化的着色器数据通道、G-Buffer 显存纹理打包方案以及美术资产创作规范。目前工业界形成了两大主流工作流：**金属度/粗糙度工作流（Metallic-Roughness Workflow）** 与 **镜面反射/光泽度工作流（Specular-Glossiness Workflow）**。本章将系统解构这两大工作流的物理映射法则、纹理通道占用与 G-Buffer 压缩排布、材质参数双向数学转换矩阵、金属/绝缘体边界处的“黑边”物理假走样成因与抗走样修复算法，以及基于无缝物理能量守恒的工业级着色管线集成范式。

------------------------------------------------------------------------
18.1 两大 PBR 工作流的物理本质与参数空间映射
------------------------------------------------------------------------

在物理真实世界中，宏观固体材质主要分为两大类：**电介质（Dielectrics / 绝缘体）** 与 **导体（Conductors / 金属）**。两者的根本光学区别在于电磁波进入介质内部后的相互作用：

- **电介质**：折射进入介质内部的光子发生多次局部散射，一部分被吸收，另一部分重新穿出表面形成宏观**漫反射（Diffuse）**；其表面垂直入射的基础反射率 $F_0$ 极低（纯灰度，通常在 $2\% \sim 5\%$ 之间，典型默认基准值为 $0.04$）；
- **金属导体**：介质内部存在海量自由电子，折射光子瞬间被自由电子吸收并转换为电子振荡，**内部折射漫反射严格为 0**；其基础反射率 $F_0$ 极高（$70\% \sim 95\%$），且在红、绿、蓝波段具有强烈的选择性反射，呈现鲜明的**彩色高光**。

为了在着色器中用最精简的参数表述这两种截然不同的物理行为，工业界演化出了两种材质抽象模型：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                金属度/粗糙度 vs 镜面反射/光泽度工作流映射拓扑           |
   +-------------------------------------------------------------------------+

   [ 方案 A: 金属度/粗糙度工作流 (Metallic-Roughness - 现代工业绝对主流) ]
   输入纹理:
   * BaseColor (sRGB)  --+--> 当 Metallic = 0 (电介质): 充当漫反射色彩 Albedo
                         +--> 当 Metallic = 1 (金属):   充当镜面反射率 F0 (彩色)
   * Metallic (Linear) ------> 线性插值混合因子 (0.0 = 纯电介质, 1.0 = 纯金属)
   * Roughness (Linear) -----> 微表面感知粗糙度 (alpha = Roughness^2)
   * 约束: 电介质 F0 被硬编码为 0.04 (或由附加 Specular 项在 [0, 0.08] 微调)

   [ 方案 B: 镜面反射/光泽度工作流 (Specular-Glossiness - 传统/影视工作流) ]
   输入纹理:
   * Diffuse (sRGB) --------> 纯漫反射反射率 (金属区域美术必须手动涂黑)
   * Specular (sRGB) -------> 直接指定 3 通道彩色基础反射率 F0
   * Glossiness (Linear) ---> 感知光泽度 (Roughness = 1.0 - Glossiness)
   * 缺陷: 允许美术自由指定 Diffuse 与 Specular，极易打破能量守恒 (Diffuse + Specular > 1.0)

.. list-table:: 工业级两大 PBR 材质工作流全方位特性对比
   :widths: 18 22 22 20 18
   :header-rows: 1
   :class: tight-table

   * - 维度对比
     - 金属度/粗糙度 (Metallic-Roughness)
     - 镜面反射/光泽度 (Specular-Glossiness)
     - 工业设计权衡 (Trade-offs)
     - 代表引擎/标准
   * - **核心参数组合**
     - BaseColor (RGB), Metallic (1ch), Roughness (1ch)
     - Diffuse (RGB), Specular (RGB), Glossiness (1ch)
     - 金属度工作流节省 **2 个浮点纹理通道**
     - glTF 2.0, UE5, Unity HDRP
   * - **物理能量守恒**
     - **代码强制物理守恒**（通过单向参数派生）
     - 依赖美术规范（极易因配比失误导致过曝）
     - 金属度模型杜绝了反物理材质资产的产生
     - Filament, Frostbite
   * - **电介质 $F_0$ 表现力**
     - 固定为 $0.04$（特殊宝石/高折射需额外参数）
     - 自由指定（可精准表达钻石 $F_0=0.17$ 等）
     - 绝大多数自然材质 $F_0 \approx 0.04$，固定化收益更高
     - Substance, 3ds Max
   * - **贴图通道打包**
     - 极易压缩打包进单个 4 通道纹理（ORM）
     - 需要两张独立 3 通道 RGB 贴图
     - **显存带宽与采样器消耗降低 40%**
     - 移动端与主机首选

------------------------------------------------------------------------
18.2 G-Buffer 压缩排布与纹理通道打包优化 (Channel Packing)
------------------------------------------------------------------------

在现代延迟渲染（Deferred Shading）与分块延迟渲染（Clustered Deferred Shading）架构中，几何通道（Geometry Pass）向多个渲染目标（Multiple Render Targets - MRT）写入的 **G-Buffer 显存带宽与显存占用** 是全局最严苛的物理瓶颈。

金属度工作流之所以统治实时工业界，其核心优势在于**完美的纹理通道打包能力（Texture Channel Packing）**。

标准 ORM / RMA 纹理打包标准
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

美术制作的单张 4 通道贴图（RGBA）可以整合三项独立的单通道材质属性，工业界通常采用 **ORM 格式**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     标准 ORM 材质贴图通道打包拓扑                       |
   +-------------------------------------------------------------------------+

   [ Texture 1: BaseColor 贴图 (sRGB 色彩空间, BC7 / DXT1 压缩, 24/32-bit) ]
     R 通道: BaseColor.R (红)
     G 通道: BaseColor.G (绿)
     B 通道: BaseColor.B (蓝)
     A 通道: 可选 Opacity 透明度裁切 (Alpha Test)

   [ Texture 2: ORM 贴图 (线性色彩空间 Linear, BC7 / DXT5 压缩, 32-bit) ]
     R 通道 (O): Ambient Occlusion (烘焙的环境光遮蔽, 缩放微观漫反射环境光)
     G 通道 (R): Roughness (感知粗糙度, 决定微表面 NDF 高光扩散半宽)
     B 通道 (M): Metallic (金属度掩码, 0=绝缘体, 1=金属)
     A 通道:     备用通道 (如 Cavity 微孔遮蔽, Displacement 局部视差高度)

   [ Texture 3: Normal 法线贴图 (线性色彩空间 Linear, BC5 / RGTC2 压缩, 16-bit) ]
     R 通道: 切线空间法线 X 分量 ([-1, 1] 映射到 [0, 1])
     G 通道: 切线空间法线 Y 分量
     B 通道: 无需存储！硬件着色器实时重建 Z = sqrt(saturate(1 - X^2 - Y^2))

延迟渲染 G-Buffer 显存槽位排布拓扑 (UE5 / Frostbite 范式)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 现代延迟渲染 G-Buffer 4 槽位极限压缩排布方案
   :widths: 15 20 25 40
   :header-rows: 1
   :class: tight-table

   * - 渲染目标 (MRT)
     - 显存像素格式
     - 通道分配定义
     - 压缩与重构机理
   * - **GBuffer A (RT0)**
     - `R8G8B8A8_SRGB`
     - RGB: BaseColor / A: Pre-baked AO
     - 硬件自动执行 sRGB $	o$ Linear 解码
   * - **GBuffer B (RT1)**
     - `R10G10B10A2_UNORM`
     - RGB: World Space Normal / A: Shading Model ID
     - 10-bit 高精度法线；2-bit 支持 4 种着色模型切换
   * - **GBuffer C (RT2)**
     - `R8G8B8A8_UNORM`
     - R: Metallic / G: Roughness / B: Specular / A: Selective Mask
     - 8-bit 线性存储，单次抓取完整微表面物理属性
   * - **GBuffer D (RT3)**
     - `R11G11B10_FLOAT`
     - RGB: Emissive 自发光 + Pre-pass GI
     - 11/10-bit 浮点存储高动态范围（HDR）自发光辐射率

------------------------------------------------------------------------
18.3 两大工作流的双向数学转换矩阵与色彩空间对齐
------------------------------------------------------------------------

在跨引擎资产管线迁移（如将 3ds Max/V-Ray 影视 Specular 资产导入 Unreal Engine 5）或构建多后端渲染器时，必须在数学层面精确执行两大工作流的双向转换。

从 Specular-Glossiness 到 Metallic-Roughness 的转换算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

已知输入：漫反射色彩 $\mathbf{C}_{	ext{diff}}$、镜面高光反射率 $\mathbf{F}_0$ 以及光泽度 $G \in [0, 1]$：

1. **粗糙度计算**：

   .. math::

      	ext{Roughness} = 1.0 - G

2. **金属度估算**：
   电介质的 $F_0$ 通常为接近 $0.04$ 的单色灰度，而纯金属的 $F_0$ 极高且常带色彩。通过 $F_0$ 偏离电介质常数的程度估算金属度因子：

   .. math::

      F_{0, 	ext{dielectric}} = 0.04

   .. math::

      	ext{Metallic} = 	ext{saturate}\left( \frac{\max(F_{0,r}, F_{0,g}, F_{0,b}) - F_{0, 	ext{dielectric}}}{1.0 - F_{0, 	ext{dielectric}}} \right)

3. **基础色彩 BaseColor 重构**：

   .. math::

      \mathbf{C}_{	ext{base}} = 	ext{lerp}\left( \mathbf{C}_{	ext{diff}}, \mathbf{F}_0, 	ext{Metallic} \right)

从 Metallic-Roughness 到 Specular-Glossiness 的转换算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

已知输入：基础色彩 $\mathbf{C}_{	ext{base}}$、金属度 $M \in [0, 1]$ 以及粗糙度 $R \in [0, 1]$：

1. **光泽度计算**：

   .. math::

      G = 1.0 - R

2. **基础高光反射率 $F_0$ 派生**：

   .. math::

      \mathbf{F}_0 = 	ext{lerp}\left( \mathbf{F}_{0, 	ext{dielectric}}, \mathbf{C}_{	ext{base}}, M \right) \quad (	ext{其中 } \mathbf{F}_{0, 	ext{dielectric}} = (0.04, 0.04, 0.04))

3. **漫反射色彩 Diffuse 计算**：

   .. math::

      \mathbf{C}_{	ext{diff}} = \mathbf{C}_{	ext{base}} 	imes (1.0 - M)

色彩空间（Color Space）对齐铁律
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       PBR 贴图色彩空间导入与处理铁律                    |
   +-------------------------------------------------------------------------+

   [ sRGB 空间纹理 (必须开启 sRGB 采样器硬件伽马转换) ]
   * BaseColor / Albedo / Diffuse: 存储人眼感知色彩，采样时必须解码为线性辐射率！
   * Specular (RGB):              存储人眼色彩反射率，必须执行 sRGB -> Linear 解码！

   [ Linear 空间纹理 (绝对禁止勾选 sRGB 导入选项!) ]
   * Roughness / Glossiness: 代表物理微表面法线半宽角度平方，伽马校正会彻底破坏高光分布！
   * Metallic:               代表物理二元材质掩码，伽马曲线会导致中间过渡带严重非线性畸变！
   * Normal Map:             代表空间三维矢量，任何非线性变换都会导致法线方向偏转与光照破损！
   * Ambient Occlusion:      代表空间半球几何遮蔽积分比率，必须保持严格线性！

------------------------------------------------------------------------
18.4 金属/电介质交界处的物理假走样（黑边现象）与抗走样修复
------------------------------------------------------------------------

在金属度工作流中，存在一个著名的工业级物理渲染陷阱——**金属与电介质交界边缘的“黑边假走样（Dark Fringe / Black Halo Artifact）”**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |              Mipmap 降采样导致金属交界处产生黑边的物理成因              |
   +-------------------------------------------------------------------------+

   [ 纹素 1: 纯金属 (例如黄金) ]         [ 纹素 2: 纯绝缘体 (例如红色塑料) ]
   BaseColor = (1.0, 0.78, 0.34) (金黄)  BaseColor = (0.8, 0.1, 0.1) (大红)
   Metallic  = 1.0                       Metallic  = 0.0
   ---------------------------------------------------------------------------
   [ 远处 Mipmap 线性双线性插值 (Bilinear Filtering) 生成的交界过渡像素 ]:
   BaseColor_mixed = 0.5 * Gold + 0.5 * Red = (0.9, 0.44, 0.22) (平均颜色)
   Metallic_mixed  = 0.5 * 1.0 + 0.5 * 0.0  = 0.5 (变成“半金属”!)
   ---------------------------------------------------------------------------
   [ 着色器执行能量解算 ]:
   1. 漫反射能量因子: Diffuse = BaseColor * (1.0 - Metallic_mixed)
                           = (0.9, 0.44, 0.22) * 0.5  --> 漫反射被腰斩 50%! (变暗)
   2. 镜面反射率 F0:  F0 = lerp(0.04, BaseColor, Metallic_mixed)
                           = lerp(0.04, (0.9, 0.44, 0.22), 0.5) = (0.47, 0.24, 0.13)
                           --> 高光反射率从金黄色 1.0 暴跌至 0.47! (变暗)
   [ 综合视觉呈现 ]:
   该交界过渡带像素的漫反射与镜面反射能量同时发生严重的非物理跌落，
   在物体轮廓边缘形成一圈极其扎眼的**暗黑色脏污轮廓线（Dark Halo）**！

黑边假走样的工业级解决方案
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **美术资产制作规范（Asset Authoring Guidelines）**：
   - 严禁美术在 Substance Painter 等软件中使用软渐变笔刷绘制 Metallic 掩码；
   - 金属度贴图必须严格保持二值化（Binary Mask）：除金属氧化锈迹、粉尘等过渡层外，纹素值必须非 $0.0$ 即 $1.0$；
2. **着色器端边缘对比度硬化（Shader Sharpening / Thresholding）**：
   在像素着色器中，对金属度参数施加非线性过渡曲线，压缩中间半金属态的像素宽度：

   .. code-block:: hlsl

      // 将 [0.1, 0.9] 的过渡带非线性硬化，消除半金属低能陷阱
      float HardenedMetallic(float rawMetallic) {
          return smoothstep(0.15f, 0.85f, rawMetallic);
      }

3. **Mipmap 预滤波加权生成器（Specular Anti-Aliasing in Texture Baking）**：
   在离线烘焙生成纹理 Mipmap 链时，使用带物理权重的非线性下采样算法，禁止对色彩空间与金属掩码进行无差别朴素双线性平均。

------------------------------------------------------------------------
18.5 标准工业级 PBR 材质解算着色器完整实现
------------------------------------------------------------------------

以下给出在现代实时商业引擎中执行的标准金属度/粗糙度 PBR 材质片元着色器全链路实现（HLSL 规范，集成 ORM 贴图解析、法线重建与 Cook-Torrance + Lambert 能量守恒解算）：

.. code-block:: hlsl

   // =========================================================================
   // 工业级标准金属度/粗糙度 PBR 着色器核心函数 (HLSL)
   // =========================================================================
   #define PBR_PI 3.14159265359f
   #define DIELECTRIC_F0 float3(0.04f, 0.04f, 0.04f)

   // 材质纹理与采样器绑定
   Texture2D<float4> g_BaseColorMap : register(t0); // sRGB 纹理
   Texture2D<float4> g_NormalMap    : register(t1); // 线性切线空间法线 (BC5)
   Texture2D<float4> g_ORMMap       : register(t2); // R=AO, G=Roughness, B=Metallic
   SamplerState      g_LinearSampler: register(s0);

   // 微表面 D 项: GGX / Trowbridge-Reitz
   float DistributionGGX(float NdotH, float roughness) {
       float a = roughness * roughness;
       float a2 = a * a;
       float NdotH2 = NdotH * NdotH;
       
       float denom = (NdotH2 * (a2 - 1.0f) + 1.0f);
       denom = PBR_PI * denom * denom;
       return a2 / max(denom, 1e-5f);
   }

   // 微表面 V 项: 合并分母的 Height-Correlated Smith 联合可视性函数
   float VisibilitySmithJoint(float NdotV, float NdotL, float roughness) {
       float a = roughness * roughness;
       float a2 = a * a;
       
       float gv = NdotL * sqrt(NdotV * (NdotV - a2 * NdotV) + a2);
       float gl = NdotV * sqrt(NdotL * (NdotL - a2 * NdotL) + a2);
       return 0.5f / max(gv + gl, 1e-5f);
   }

   // 微表面 F 项: Fresnel-Schlick 近似
   float3 FresnelSchlick(float VdotH, float3 F0) {
       return F0 + (1.0f - F0) * pow(saturate(1.0f - VdotH), 5.0f);
   }

   // 切线空间法线重构与坐标变换
   float3 UnpackAndTransformNormal(float2 uv, float3 worldPos, float3 worldNormal, float4 worldTangent) {
       float2 normalXY = g_NormalMap.Sample(g_LinearSampler, uv).xy * 2.0f - 1.0f;
       float  normalZ  = sqrt(saturate(1.0f - dot(normalXY, normalXY)));
       float3 tangentNormal = float3(normalXY, normalZ);

       float3 N = normalize(worldNormal);
       float3 T = normalize(worldTangent.xyz);
       float3 B = cross(N, T) * worldTangent.w; // 考虑切线翻转符号
       float3x3 TBN = float3x3(T, B, N);

       return normalize(mul(tangentNormal, TBN));
   }

   // 核心表面光照解算入口
   float3 ShadePBRSurface(
       float2 uv,
       float3 worldPos,
       float3 worldNormal,
       float4 worldTangent,
       float3 cameraPos,
       float3 lightDir,
       float3 lightRadiance)
   {
       // 1. 纹理采样与数据解耦
       float4 baseColorSample = g_BaseColorMap.Sample(g_LinearSampler, uv);
       float3 baseColor = baseColorSample.rgb; // 硬件自动执行 sRGB -> Linear
       
       float3 orm = g_ORMMap.Sample(g_LinearSampler, uv).rgb;
       float ao        = orm.r;
       float roughness = max(orm.g, 0.045f); // 锁定微观粗糙度下限，防止高光除零与走样
       float metallic  = orm.b;

       // 2. 几何矢量计算
       float3 N = UnpackAndTransformNormal(uv, worldPos, worldNormal, worldTangent);
       float3 V = normalize(cameraPos - worldPos);
       float3 L = normalize(lightDir);
       float3 H = normalize(V + L);

       float NdotL = saturate(dot(N, L));
       float NdotV = max(dot(N, V), 1e-4f);
       float NdotH = saturate(dot(N, H));
       float VdotH = saturate(dot(V, H));

       // 3. 物理参数空间映射 (金属度工作流核心转换)
       float3 F0 = lerp(DIELECTRIC_F0, baseColor, metallic);
       float3 diffuseAlbedo = baseColor * (1.0f - metallic);

       // 4. 求解 Cook-Torrance 镜面高光反射
       float  D = DistributionGGX(NdotH, roughness);
       float  V_term = VisibilitySmithJoint(NdotV, NdotL, roughness);
       float3 F = FresnelSchlick(VdotH, F0);

       float3 specularBRDF = D * V_term * F;

       // 5. 求解能量守恒漫反射 (Lambert)
       float3 kD = (float3(1.0f, 1.0f, 1.0f) - F) * (1.0f - metallic);
       float3 diffuseBRDF = kD * (diffuseAlbedo / PBR_PI);

       // 6. 最终光照合成
       float3 directLighting = (diffuseBRDF + specularBRDF) * lightRadiance * NdotL;

       // 叠加环境光遮蔽 (AO)
       return directLighting * ao;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从工业工程实践出发，系统解构了金属度/粗糙度与镜面反射/光泽度两大工作流的物理映射法则、G-Buffer 极限压缩与 ORM 纹理打包标准、资产双向转换数学矩阵、Mipmap 降采样引发的“黑边”假走样物理成因与消除算法，并给出了完整的生产级 HLSL 着色器实现。

至此，标准硬表面（Hard-Surface）的物理反射模型已建立完毕。然而真实世界中还广泛存在半透明、透光、多层复合以及各向异性结构（如人体皮肤、玉石、汽车清漆车漆、拉丝金属与丝绸织物）。下一章我们将深入更广阔的材质表述空间——**复杂材质表述：次表面散射 (BSSRDF)、各向异性、清漆涂层与织物微纤维模型**，解构偶极子扩散、离散次表面散射拟合与微纤维毛茸光晕的高阶材质渲染体系。
