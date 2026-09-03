========================================================================
Chapter 22: 级联阴影贴图 (CSM)：视锥体分割、稳定对齐与边界平滑过渡
========================================================================

.. note:: 前置背景与认知承接
   前一章深入剖析了两阶段阴影映射（Two-Pass Shadow Mapping）的数学数据流、离散网格采样导致自阴影粉刺（Shadow Acne）的几何机理，并通过斜率比例深度偏差（Slope-Scaled Depth Bias）与法线偏移偏差（Normal Offset Bias）建立了工业级无瑕疵硬阴影求解方案。然而，标准 Shadow Map 采用单一投影矩阵覆盖整个视锥体，在开放世界大场景中暴露了严重的物理瓶颈：相机近处的地面细节与数千米外的远山共用同一张分辨率有限的贴图，导致近景阴影边缘呈现严重的马赛克粗糙锯齿——即**透视走样（Perspective Aliasing）**。为了解决大纵深场景下的分辨率均匀分配问题，现代工业引擎普遍采用**级联阴影贴图（Cascaded Shadow Maps - CSM，又称 PSSM）**。本章将系统解构透视走样的数学本质、视锥体混合对数分割算法（Practical Split Scheme）、视锥包围球紧密拟合与光源矩阵构建、亚像素抖动消除的纹素对齐稳定化（Texel Snapping）技术、级联接缝平滑混合（Cascade Blending）以及基于 `Texture2DArray` 的工业级 GPU 采样流水线。

------------------------------------------------------------------------
22.1 透视走样 (Perspective Aliasing) 与几何投影走样的物理根源
------------------------------------------------------------------------

在定向光源（如太阳光）照射下，阴影映射面临两大核心走样矛盾：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     阴影映射两大走样成因与微观网格失配                  |
   +-------------------------------------------------------------------------+

   [ 走样 1: 透视走样 (Perspective Aliasing) ]
   * 摄像机视锥体具有近窄远宽的透视特性:
     - 距离相机近处的 1 个像素在世界空间覆盖的物理尺寸微小 (如 1mm);
     - 距离相机远处的 1 个像素在世界空间覆盖的物理尺寸巨大 (如 1m);
   * 但单一正交定向光 Shadow Map 是均匀网格划分 (每 Texel 世界尺寸恒定, 如 50cm):
     -> 近景区域: 1 个 Shadow Texel 对应成百上千个屏幕像素! (严重马赛克边缘)
     -> 远景区域: 成百上千个 Shadow Texel 压缩在 1 个屏幕像素内! (严重欠采样浪费)

   [ 走样 2: 投影走样 (Projective Aliasing) ]
   * 当光线方向与几何表面法线近乎垂直 (大掠射角, 光线平掠表面) 时:
     -> 光源视点投影到多边形表面的有效面积发生极大拉伸!

透视走样比率 (Aliasing Ratio) 的定量数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设主摄像机近裁剪面为 $n$，远裁剪面为 $f$，当前观察点的视点深度为 $z_v \in [n, f]$，垂直视场角为 $	ext{FOV}_y$，屏幕垂直分辨率为 $H_{	ext{screen}}$。
单个屏幕像素在视距 $z_v$ 处对应的世界空间物理高度为：

.. math::

   \Delta y_{	ext{screen}}(z_v) = \frac{2 \cdot z_v \cdot 	an(	ext{FOV}_y / 2)}{H_{	ext{screen}}} \propto z_v

若定向光 Shadow Map 的正交视锥体世界空间高度为 $S_{	ext{light}}$，分辨率为 $R_{	ext{shadow}}$，则单个阴影纹素在世界空间中的恒定物理高度为：

.. math::

   \Delta y_{	ext{shadow}} = \frac{S_{	ext{light}}}{R_{	ext{shadow}}} = 	ext{Constant}

定义走样倍率（Aliasing Factor）为阴影纹素物理尺寸与屏幕像素物理尺寸之比：

.. math::

   	ext{AliasingFactor}(z_v) = \frac{\Delta y_{	ext{shadow}}}{\Delta y_{	ext{screen}}(z_v)} = \frac{S_{	ext{light}} \cdot H_{	ext{screen}}}{2 \cdot R_{	ext{shadow}} \cdot 	an(	ext{FOV}_y / 2)} \cdot \frac{1}{z_v} \propto \frac{1}{z_v}

.. list-table:: 单一 2048x2048 Shadow Map 覆盖 500m 视距时的走样倍率量化
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 观察视距 ($z_v$)
     - 屏幕像素世界尺寸 ($\Delta y_{	ext{screen}}$)
     - 阴影纹素世界尺寸 ($\Delta y_{	ext{shadow}}$)
     - 走样倍率 ($\Delta y_{	ext{shadow}} / \Delta y_{	ext{screen}}$)
   * - **近景 ($z = 1.0\,	ext{m}$)**
     - $0.0008\,	ext{m}$ ($0.8\,	ext{mm}$)
     - $0.25\,	ext{m}$ ($250\,	ext{mm}$)
     - **312.5 倍！(极其严重的马赛克粗斑)**
   * - **中景 ($z = 20\,	ext{m}$)**
     - $0.016\,	ext{m}$ ($16\,	ext{mm}$)
     - $0.25\,	ext{m}$ ($250\,	ext{mm}$)
     - 15.6 倍 (明显锯齿)
   * - **远景 ($z = 100\,	ext{m}$)**
     - $0.08\,	ext{m}$ ($80\,	ext{mm}$)
     - $0.25\,	ext{m}$ ($250\,	ext{mm}$)
     - 3.1 倍 (边缘较平滑)
   * - **极限远景 ($z = 500\,	ext{m}$)**
     - $0.40\,	ext{m}$ ($400\,	ext{mm}$)
     - $0.25\,	ext{m}$ ($250\,	ext{mm}$)
     - 0.625 倍 (纹素过密，出现高频闪烁)

从推导可见，当 $z_v 	o n$ 时，走样倍率呈反比例激增至数百倍。必须将视锥体沿深度方向切分，为近景分配极小范围的高精度投影，为远景分配覆盖广阔的大范围投影。

------------------------------------------------------------------------
22.2 视锥体分割算法：对数、线性与实际混合分割 (PSSM)
------------------------------------------------------------------------

级联阴影贴图将主相机的视锥体沿视线方向切割为 $M$ 个连续子视锥体（通常 $M = 4$），每个子视锥体对应一个独立的级联层级（Cascade $0 \sim M-1$）。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  4 级级联阴影视锥体几何分层切分示意图                   |
   +-------------------------------------------------------------------------+

   摄像机 Eye
      \   Cascade 0 (近景: 0.1m ~ 10m) -> 极高分辨率密集体积
       \  +-----------+
        \ | Cascade 1 | (中近景: 10m ~ 35m)
         \|           |
          +-----------+
          | Cascade 2 | (中远景: 35m ~ 120m)
          |           |
          +-----------+
          | Cascade 3 | (超远景: 120m ~ 500m)
          |           |
          +-----------+ 远裁剪面 f = 500m

三种视锥体分割模型数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设总裁剪范围为 $[n, f]$，级联数为 $M$，求第 $i$ 个分割点深度 $z_i$（其中 $z_0 = n, z_M = f, i \in [0, M]$）：

1. **线性均匀分割（Uniform Split）**：
   各层级沿深度等间距递增：

.. math::

   z_i^{	ext{uniform}} = n + (f - n) \cdot \frac{i}{M}

*缺陷*：近景层级跨度过大（如 $500/4 = 125	ext{m}$），无法有效抑制近景走样。

2. **对数分割（Logarithmic Split）**：
   在理论上使每个级联层级的最大透视走样倍率保持完全相等：

.. math::

   z_i^{	ext{log}} = n \cdot \left( \frac{f}{n} \right)^{\frac{i}{M}}

*缺陷*：若近裁剪面 $n$ 极小（如 $n = 0.01	ext{m}$），对数分割会将前两级级联全部聚集在相机鼻子前方不足 1 米的极小区域，导致中景过早失去高精度覆盖。

3. **实际混合分割（Practical Split Scheme / PSSM）**：
   将对数分割与线性分割进行可调权重 $\lambda \in [0, 1]$（通常取 $0.7 \sim 0.9$）的线性插值融合：

.. math::

   z_i^{	ext{pssm}} = \lambda \cdot z_i^{	ext{log}} + (1 - \lambda) \cdot z_i^{	ext{uniform}} = \lambda \left[ n \left( \frac{f}{n} \right)^{\frac{i}{M}} \right] + (1 - \lambda) \left[ n + (f - n) \frac{i}{M} \right]

.. list-table:: 4 级级联在 $n=0.1	ext{m}, f=500	ext{m}, \lambda=0.85$ 时的切分距离对照
   :widths: 20 20 20 20 20
   :header-rows: 1
   :class: tight-table

   * - 级联编号 (Cascade)
     - 分割点 $z_i$ 距离
     - 层级覆盖跨度 ($\Delta z$)
     - 正交视锥体半径
     - 单纹素世界精度 (2048 贴图)
   * - **Cascade 0**
     - $0.1\,	ext{m} \sim 7.2\,	ext{m}$
     - $7.1\,	ext{m}$
     - $\sim 6\,	ext{m}$
     - **$5.8\,	ext{mm}$ (毫米级极致锐利)**
   * - **Cascade 1**
     - $7.2\,	ext{m} \sim 28.5\,	ext{m}$
     - $21.3\,	ext{m}$
     - $\sim 22\,	ext{m}$
     - $21.5\,	ext{mm}$
   * - **Cascade 2**
     - $28.5\,	ext{m} \sim 115.0\,	ext{m}$
     - $86.5\,	ext{m}$
     - $\sim 85\,	ext{m}$
     - $83.0\,	ext{mm}$
   * - **Cascade 3**
     - $115.0\,	ext{m} \sim 500.0\,	ext{m}$
     - $385.0\,	ext{m}$
     - $\sim 360\,	ext{m}$
     - $351.5\,	ext{mm}$

------------------------------------------------------------------------
22.3 各级级联正交投影构建与包围球紧密拟合
------------------------------------------------------------------------

确定了每个子视锥体的深度区间 $[z_{i-1}, z_i]$ 后，CPU 必须为每个级联计算一个严密包围该几何体且分辨率最大化利用的光源视图投影矩阵 $\mathbf{M}_{	ext{vp}, i} = \mathbf{P}_{	ext{ortho}, i} \cdot \mathbf{V}_{	ext{light}, i}$。

包围体构建的两大算法路线对比
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   +-------------------------------------------------------------------------+
   |          光源正交投影包围体构建: AABB 紧密包围盒 vs 旋转不变包围球       |
   +-------------------------------------------------------------------------+

   [ 路线 A: 光源空间紧密 AABB (Tight Light-Space AABB) ]
   1. 提取子视锥体 8 个世界空间角点并变换至光源空间;
   2. 计算包围这 8 个点的最小 Axis-Aligned Bounding Box (minX, maxX, minY, maxY);
   * 优点: 贴图利用率极高 (无冗余空白);
   * 致命缺陷: 当相机旋转时，8 个角点在光源空间投影不断变形，包围盒尺寸剧烈跳变!
     -> 导致 Shadow Map 像素网格不停缩放变动，阴影边缘爆发严重的旋转闪烁 (Edge Shimmering)!

   [ 路线 B: 视锥外接球包围体 (Frustum Bounding Sphere) - 工业界标准 ]
   1. 计算能够完美包裹当前子视锥体的最小三维外接球 (中心点 Center, 半径 Radius);
   2. 构建正交投影矩阵: X/Y 范围固定为 [-Radius, +Radius];
   * 核心物理优势: 无论相机如何原地旋转 (Pitch/Yaw/Roll)，外接球在三维空间中绝对恒定不变!
     -> 正交投影视口尺寸彻底锁死，从根源上消除了相机旋转引发的阴影闪烁!

外接包围球半径与中心点数学推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于一个近平面为 $z_{	ext{near}}$、远平面为 $z_{	ext{far}}$、高宽比为 $a$、垂直半视场角为 $\alpha = 	ext{FOV}_y / 2$ 的对称平截头体：
其外接球中心必定位于相机视线中轴线上，设其相机空间坐标为 $\mathbf{C}_{	ext{view}} = [0, 0, z_c]$。
为了使中心到近平面 4 个角点的距离等于到远平面 4 个角点的距离：

.. math::

   z_c = \frac{(z_{	ext{near}} + z_{	ext{far}})(1 + a^2 	an^2\alpha + 	an^2\alpha)}{2} = \frac{z_{	ext{near}} + z_{	ext{far}}}{2} \left(1 + \frac{	an^2\alpha (1 + a^2)}{2} \right) \quad (	ext{简化近似})

严格求得外接球中心世界坐标 $\mathbf{C}_{	ext{world}}$ 与半径 $R$：

.. math::

   R = \sqrt{\left(\frac{z_{	ext{far}} - z_{	ext{near}}}{2}\right)^2 + \left(z_{	ext{far}} \cdot 	an\alpha \cdot \sqrt{1 + a^2}\right)^2}

光源视图矩阵与投影矩阵配置：

.. math::

   \mathbf{V}_{	ext{light}} = 	ext{LookAt}(\mathbf{C}_{	ext{world}} - \mathbf{L} \cdot R_{	ext{depth}}, \mathbf{C}_{	ext{world}}, \mathbf{Up}_{	ext{world}}), \quad
   \mathbf{P}_{	ext{ortho}} = 	ext{Ortho}(-R, +R, -R, +R, 0.0, 2 \cdot R_{	ext{depth}})

其中 $R_{	ext{depth}}$ 必须向光源后方延伸足够距离（通常取 $R + 	ext{MaxSceneCasterExtents}$），确保视锥体外部但能投射阴影进入当前视锥的遮挡物（Casters）不会被正交近平面剔除。

------------------------------------------------------------------------
22.4 亚像素抖动消除：纹素对齐稳定化 (Texel Snapping)
------------------------------------------------------------------------

即使采用了外接球消除了相机旋转带来的闪烁，当相机在世界中平移（Translation）时，外接球中心 $\mathbf{C}_{	ext{world}}$ 产生连续微小位移。这导致 Shadow Map 的离散像素网格在世界几何体表面产生连续滑动，造成阴影边缘以像素为单位剧烈抖动（Crawling Edges / Shimmering）。

Texel Snapping (纹素离散网格量化对齐) 算法
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

核心思想：**强制光源视图投影矩阵的原点只能以单个阴影纹素的世界尺寸（World Units per Texel）为步长进行阶梯式跳跃，禁止亚纹素级微小位移！**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     Texel Snapping 纹素网格量化对齐原理                 |
   +-------------------------------------------------------------------------+

   [ 连续平移计算出的原始光源视图矩阵 V_light ]
        |
        v
   1. 将原点投影至光源观察空间 (Light Space): P_light = V_light * [0, 0, 0, 1]^T
   2. 计算当前级联单纹素物理尺寸: TexelSize = (2 * Radius) / ShadowMapResolution
   3. 对光源空间 X/Y 坐标执行量化取整:
        P_snapped.x = floor(P_light.x / TexelSize) * TexelSize;
        P_snapped.y = floor(P_light.y / TexelSize) * TexelSize;
   4. 计算亚纹素偏移差值: Delta = P_snapped.xy - P_light.xy;
   5. 修正正交投影矩阵: 将 Delta.xy 补偿注入投影矩阵的平移项中!
        |
        v
   [ 最终生成的 Shadow Map 物理网格在世界坐标系中绝对固定不动! ]
   [ 摄像机平移时, 阴影像素边缘完全静止, 彻底消除了闪烁抖动! ]

C++ 引擎端 Texel Snapping 算法实现代码
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: cpp

   // C++: 级联阴影矩阵计算与 Texel Snapping 稳定化算法
   void BuildStableCascadeMatrix(
       const BoundingSphere& sphere,
       const Vector3& lightDir,
       uint32_t shadowMapRes,
       Matrix4x4& outLightView,
       Matrix4x4& outLightProj)
   {
       float radius = sphere.radius;
       Vector3 center = sphere.center;

       // 1. 计算单个 Texel 在世界空间中的物理米数
       float worldUnitsPerTexel = (2.0f * radius) / static_cast<float>(shadowMapRes);

       // 2. 构建未对齐的基础光源 View 矩阵 (看向包围球中心)
       Vector3 lightPos = center - lightDir * radius * 2.0f;
       outLightView = Matrix4x4::LookAt(lightPos, center, Vector3(0.0f, 1.0f, 0.0f));

       // 3. 将包围球中心变换至光源空间
       Vector3 centerLightSpace = outLightView.TransformPoint(center);

       // 4. 执行 Floor 量化对齐
       float snappedX = std::floor(centerLightSpace.x / worldUnitsPerTexel) * worldUnitsPerTexel;
       float snappedY = std::floor(centerLightSpace.y / worldUnitsPerTexel) * worldUnitsPerTexel;

       // 5. 反算位移偏差并修正 View 矩阵的位置平移
       Vector3 snappedCenterLightSpace(snappedX, snappedY, centerLightSpace.z);
       Vector3 snappedCenterWorld = outLightView.Inverse().TransformPoint(snappedCenterLightSpace);
       
       Vector3 snappedLightPos = snappedCenterWorld - lightDir * radius * 2.0f;
       outLightView = Matrix4x4::LookAt(snappedLightPos, snappedCenterWorld, Vector3(0.0f, 1.0f, 0.0f));

       // 6. 构建稳定的正交投影矩阵
       outLightProj = Matrix4x4::Ortho(
           -radius, radius,
           -radius, radius,
           0.0f, radius * 4.0f
       );
   }

------------------------------------------------------------------------
22.5 级联选择与边界平滑过渡 (Cascade Blending)
------------------------------------------------------------------------

在着色通道中，GPU 必须确定当前像素属于哪一级级联，并采样对应的深度贴图。

级联选择策略：深度区间测试 vs 贴图坐标包围盒
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **观察空间深度比较（View-Space Z Comparison）**：
   在着色器中提取当前像素的视空间深度 $z_{	ext{view}}$，依次与 CPU 传入的 4 个分割距离 `g_CascadeSplits[4]` 比较：

.. code-block:: hlsl

   uint cascadeIndex = 0;
   if (viewDepth > g_CascadeSplits[0]) cascadeIndex = 1;
   if (viewDepth > g_CascadeSplits[1]) cascadeIndex = 2;
   if (viewDepth > g_CascadeSplits[2]) cascadeIndex = 3;

*优点*：仅需 3 次标量比较，执行速度极快。

2. **贴图 UV 包围盒测试（Map Bounds Test）**：
   将世界坐标依次投影到 4 个级联的投影空间中，检查 UV 坐标是否处于 $[0, 1]^2$ 内且最贴近。

级联接缝硬断裂伪影与平滑过渡混合 (Cascade Blending)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于相邻级联之间的分辨率存在 $3 \sim 4$ 倍的突变（如 Cascade 0 单纹素 5mm，Cascade 1 单纹素 21mm），在分割交界线处，阴影边缘会瞬间从锐利跳变到模糊，形成一条极为突兀的“硬接缝（Cascade Seam）”。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  级联接缝硬断裂 vs 软过渡混合 (Cascade Blending)        |
   +-------------------------------------------------------------------------+

   [ 无过渡方案: 硬切 ]
   Cascade 0 (锐利边缘) |<--- 突兀硬折线接缝 --->| Cascade 1 (模糊边缘)

   [ 工业级过渡方案: 边界混合区 (Blend Band) 线性插值 ]
   Cascade 0 覆盖区     | 混合带 (如深度末端 15% 区域) | Cascade 1 覆盖区
                        | S = (1-a)*Shadow0 + a*Shadow1 |
                        | 权重 a 沿深度从 0.0 渐变至 1.0|

平滑混合权重计算方程：
设当前级联覆盖区间为 $[z_{i-1}, z_i]$，混合过渡带宽度比例为 $\beta \in [0.1, 0.2]$。
定义混合起始距离 $z_{	ext{blend\_start}} = z_i - (z_i - z_{i-1}) \cdot \beta$。混合权重 $\alpha$ 计算为：

.. math::

   \alpha = 	ext{saturate}\left( \frac{z_{	ext{view}} - z_{	ext{blend\_start}}}{z_i - z_{	ext{blend\_start}}} \right)

若 $\alpha > 0$，着色器同时采样 Cascade $i$ 与 Cascade $i+1$，输出线性混合阴影因子：

.. math::

   S_{	ext{final}} = (1.0 - \alpha) \cdot S_i + \alpha \cdot S_{i+1}

------------------------------------------------------------------------
22.6 工业级 HLSL 4 级 CSM 采样与 Texture2DArray 完整实现
------------------------------------------------------------------------

在现代图形 API 中，将 4 个级联打包为单张 **`Texture2DArray`（纹理数组）** 是最优的硬件方案——避免在着色器中绑定 4 个独立纹理插槽，允许在一次 API 调用中完成数组切片（Array Slice）采样。

.. code-block:: hlsl

   // HLSL: 工业级 4 级级联阴影贴图 (CSM) 完整采样与级联平滑过渡着色器
   // 特性: Texture2DArray 纹理数组 + 观察空间深度索引 + 级联交叉平滑混合 + 硬件 PCF

   Texture2DArray<float> g_CSMTextureArray : register(t0); // 4 切片深度数组 (Layer 0~3)
   SamplerComparisonState g_ShadowCompSampler : register(s0); // 硬件级 LESS_EQUAL 比较采样器

   cbuffer CSMConstantBuffer : register(b1) {
       float4x4 g_LightViewProjs[4];    // 4 个级联的光源视图投影矩阵
       float4   g_CascadeSplitDepths;   // (z0, z1, z2, z3) 观察空间深度阈值
       float4   g_CascadeBlendRange;    // (fade0, fade1, fade2, fade3) 各层级混合带起始深度
       float4   g_ShadowMapResolution;  // (res, res, 1/res, 1/res)
       float4   g_CascadeNormalBias;    // 4 个级联独立的法线偏移系数
       float4   g_LightDirWS;           // 光源入射方向 (指向光源)
   };

   // 单级联阴影因子采样辅助函数
   float SampleSingleCascade(uint cascadeIdx, float3 positionWS, float3 normalWS, float NdotL) {
       // 1. 应用法线偏移偏差 (根据各级级联的物理尺寸缩放)
       float normalOffset = g_CascadeNormalBias[cascadeIdx] * sqrt(saturate(1.0f - NdotL * NdotL));
       float3 biasedPosWS = positionWS + normalWS * normalOffset;

       // 2. 变换至光源裁剪空间
       float4 lightClipPos = mul(g_LightViewProjs[cascadeIdx], float4(biasedPosWS, 1.0f));
       float3 lightNDC = lightClipPos.xyz / lightClipPos.w;

       // 3. 映射至纹理 UV [0, 1]
       float2 shadowUV = float2(lightNDC.x * 0.5f + 0.5f, -lightNDC.y * 0.5f + 0.5f);
       float compareDepth = lightNDC.z;

       // 4. 边界越界保护
       if (shadowUV.x < 0.0f || shadowUV.x > 1.0f || 
           shadowUV.y < 0.0f || shadowUV.y > 1.0f || 
           compareDepth > 1.0f) {
           return 1.0f;
       }

       // 5. 硬件 PCF 纹理数组采样 (UVW 坐标: u, v, sliceIndex)
       float shadow = g_CSMTextureArray.SampleCmpLevelZero(
           g_ShadowCompSampler,
           float3(shadowUV, (float)cascadeIdx),
           compareDepth
       );

       return shadow;
   }

   // 核心 CSM 全局阴影解算主入口
   float CalculateCSMShadow(float3 positionWS, float3 normalWS, float viewDepth) {
       float NdotL = dot(normalWS, g_LightDirWS.xyz);
       if (NdotL <= 0.0f) {
           return 0.0f; // 背光面直接判定为阴影
       }

       // 1. 确定主级联索引
       uint cascadeIndex = 3;
       if (viewDepth < g_CascadeSplitDepths.x) cascadeIndex = 0;
       else if (viewDepth < g_CascadeSplitDepths.y) cascadeIndex = 1;
       else if (viewDepth < g_CascadeSplitDepths.z) cascadeIndex = 2;

       // 2. 采样主级联
       float shadowFactor = SampleSingleCascade(cascadeIndex, positionWS, normalWS, NdotL);

       // 3. 级联平滑过渡计算 (仅在前 3 级且处于混合区时触发)
       if (cascadeIndex < 3) {
           float blendStart = g_CascadeBlendRange[cascadeIndex];
           float blendEnd   = g_CascadeSplitDepths[cascadeIndex];

           if (viewDepth > blendStart) {
               float alpha = saturate((viewDepth - blendStart) / (blendEnd - blendStart));
               
               // 采样下一级较粗精度的级联并执行线性插值
               float nextShadowFactor = SampleSingleCascade(cascadeIndex + 1, positionWS, normalWS, NdotL);
               shadowFactor = lerp(shadowFactor, nextShadowFactor, alpha);
           }
       }

       return shadowFactor;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从定向光源的大纵深透视走样物理矛盾出发，系统建立了级联阴影贴图（CSM）的视锥体几何切分架构，推导了对数与线性混合分割模型（PSSM），通过视锥外接球消除了相机旋转引起的投影形变，给出了基于 Texel Snapping 的亚像素抖动稳定化算法，阐述了级联接缝平滑过渡的混合机制，并基于 `Texture2DArray` 交付了工业级全套 HLSL 采样管线。

然而，无论 CSM 如何提高近景几何分辨率，Shadow Map 生成的阴影边缘依然是锐利的二值硬阴影（Hard Shadow）。在现实世界中，发光体并非理想点光源，而是具有物理面积的面光源（Area Light），投射出的阴影由暗部本影区（Umbra）和随遮挡物距离逐渐扩散变柔的半影区（Penumbra）构成。下一章我们将深入工业级软阴影技术——**软阴影过滤与面积光近似：百分比临近滤波 (PCF)、接触硬化软阴影 (PCSS) 与方差阴影贴图 (VSM)**，解构半影区核尺寸动态搜寻与卷积加速的数学物理大厦。
