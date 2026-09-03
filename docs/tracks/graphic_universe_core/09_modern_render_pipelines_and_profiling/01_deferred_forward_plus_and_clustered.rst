========================================================================
Chapter 41: 现代渲染管线架构：Forward+、Deferred Shading 与 Clustered Light Culling
========================================================================

.. note:: 前置背景与认知承接
   在 Chapter 40 中，我们解构了工业级渲染硬件接口（RHI）的引擎级抽象体系，剖析了跨平台对象模型、不可变管线状态对象（PSO）运行时双级缓存拓扑、无锁多线程命令列表池化架构，以及基于声明式 FrameGraph 的全局资源屏障自动化推导规则。通过 RHI，图形引擎得以在 Direct3D 12、Vulkan、Metal 与 WebGPU 之上建立统一、无损且高吞吐的硬件命令下发通道。

   然而，在解决了“命令与资源如何向硬件提交”之后，现代游戏与影视渲染引擎面临着更为本质的系统级挑战：**海量场景几何体（数十万个 Mesh 实例）与复杂动态光照系统（成百上千个点光、聚光与面光源）应当在何种时序、空间划分与显存拓扑下完成物理交互与着色解算？**

   传统的前向渲染（Forward Rendering）在多光源场景下面临着严重的复杂度爆炸；而经典的延迟着色（Deferred Shading）虽然成功解耦了可见性与着色计算，却引入了高昂的 G-Buffer 显存带宽消耗，并在硬件多重采样抗锯齿（MSAA）与半透明渲染上遭遇物理架构层面的阻碍。为了兼顾多光源高扩展性、高保真材质多样性与硬件带宽利用率，图形学界相继演进出了 **分块前向渲染（Forward+ / Tiled Forward）** 与 **分簇光照着色体系（Clustered Forward / Clustered Deferred Shading）**。本章将从微架构物理事实与空间划分算法出发，系统化推导现代三大渲染管线的演进脉络、数据流流动机制、分簇光照剔除的核心算法与工程实现。

------------------------------------------------------------------------
41.1 经典渲染管线的演进动力与复杂度危机
------------------------------------------------------------------------

传统前向渲染的复杂度危机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在早期固定管线与可编程流水线初期，图形引擎普遍采用前向渲染模型。在前向渲染中，每个网格物体（Mesh）在执行几何光栅化生成片元的同时，立即在像素着色器（Pixel Shader）内部遍历影响该物体的所有光源并解算光照方程：

.. math::

   C_{	ext{final}} = \sum_{i=0}^{N_{	ext{lights}}-1} f_{	ext{BRDF}}(\mathbf{l}_i, \mathbf{v}, \mathbf{n}) \cdot (\mathbf{n} \cdot \mathbf{l}_i) \cdot \frac{\Phi_i}{4\pi \|\mathbf{p} - \mathbf{x}_i\|^2} \cdot V(\mathbf{x}_i, \mathbf{p})

设场景中可见几何体的图元片元总数为 $M$，场景中的动态光源数量为 $L$。若场景存在深度遮挡（Overdraw 因子为 $D \ge 1$），则全场景前向光照计算的理论时间复杂度为：

.. math::

   T_{	ext{Forward}} = O(M 	imes D 	imes L)

该模型在现代复杂场景中暴露出三大致命瓶颈：

1. **遮挡过绘制算力浪费 (Overdraw Waste)**：在没有严格硬件 Early-Z 剔除或存在复杂 Alpha 深度遮挡的场景下，被后续近景完全遮挡的远处表面，依然执行了极其昂贵的多光源 PBR 着色计算，着色产物随后被深度测试直接丢弃；
2. **多通道与动态分支的双重困境**：
   - *Multi-Pass Forward*：每个光源（或每 4 个光源）渲染一个独立的 Draw Call，通过启用加法混合（Additive Blending）叠加光照。此方案会导致顶点变换与几何光栅化重复执行 $L$ 次，直接打穿硬件顶点处理吞吐上限；
   - *Single-Pass Forward with Loops*：将所有光源参数打包进常量缓冲区（Constant Buffer / UBO），在单个着色器内执行大循环。当光源数量超过数十个时，寄存器用量（VGPR）急剧膨胀，导致 GPU 流水线 Occupancy 断崖式下跌，且循环内频繁的分支预测失败造成严重的 SIMT 线程发散（Divergence）；
3. **着色器变体爆炸 (Shader Permutation Explosion)**：不同物体受到的光源类型组合（点光、聚光、平行光、阴影开关）各不相同，迫使离线编译期生成数以万计的条件宏变体。

经典延迟着色 (Deferred Shading) 的解耦哲学与局限
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为彻底粉碎 $O(M 	imes L)$ 的乘积依赖，经典延迟着色体系确立了**“可见性测试（Visibility）与光照积分（Lighting）完全解耦”**的设计哲学。管线将一帧划分为两个核心物理阶段：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       传统延迟着色管线物理执行流水线                      |
   +-------------------------------------------------------------------------+

   [ 阶段 1: 几何阶段 (G-Buffer Pass) ]
     - 仅渲染不透明表面几何体，执行顶点变换与表面纹理采样
     - 关闭光照解算，直接将几何与材质属性写入多个渲染目标 (MRT)
     - 产物: GBuffer0 (Albedo), GBuffer1 (Normal), GBuffer2 (Material), Depth
                                   |
                                   v
   [ 阶段 2: 光照解算阶段 (Deferred Lighting Pass) ]
     - 渲染全屏四边形 (Screen Quad) 或光照几何体 (Light Volume Sphere/Cone)
     - 从 G-Buffer 与 Depth 读取表面物理参数，利用逆投影矩阵重建世界坐标
     - 仅对最终可见的屏幕像素执行 PBR 光照求值，写入最终 HDR 颜色缓冲区

通过两阶段拆分，光照求值的执行次数被严格约束在屏幕可见像素总数 $W 	imes H$ 之内，与场景的原始几何复杂度彻底解耦，其时间复杂度降为：

.. math::

   T_{	ext{Deferred}} = O(M 	imes D) + O(W 	imes H 	imes L_{	ext{visible}})

尽管延迟着色极大解放了动态光源数量，但随着渲染分辨率跃升至 1440p、4K 乃至 8K，经典延迟着色在现代硬件上遭遇了严重的物理反噬：

1. **海量 G-Buffer 显存带宽吞吐压制**：全高清分辨率下，一套典型的 4 MRT G-Buffer 尺寸高达每像素 $24 \sim 32$ 字节。在 4K (3840×2160) 分辨率、60 FPS 下，仅 G-Buffer 的单向写入与二次读回就将产生超过 **$3840 	imes 2160 	imes 32 	imes 2 	imes 60 \approx 31.8	ext{ GB/s}$** 的绝对总线带宽消耗，严重挤占材质贴图与计算管线的显存通道；
2. **硬件多重采样抗锯齿 (MSAA) 架构性失效**：延迟管线的像素着色发生于光栅化之后，G-Buffer 若开启 $4	imes$ MSAA，则内存占用与写带宽将直接放大 4 倍，且自定义 Resolve 需对几何边缘执行繁琐的子像素复原；
3. **半透明渲染的断层与孤立**：G-Buffer 深度仅能记录最前方的单一不透明表面点，无法容纳多层半透明物体的深度拓扑与混合顺序，所有玻璃、粒子、水雾必须回退至独立的前向渲染通道（Transparent Forward Pass）中二次处理，造成管线割裂；
4. **材质模型均一化约束**：所有物体必须塞入统一格式的 G-Buffer 中，当场景中同时存在次表面散射（皮肤）、各向异性（头发）、微孔织物（布料）与标准 PBR 金属时，光照着色器必须依赖材质 ID 执行动态分支，引发 SIMT 核心严重发散。

------------------------------------------------------------------------
41.2 G-Buffer 物理布局设计与显存带宽优化
------------------------------------------------------------------------

高紧凑 G-Buffer 物理通道对齐设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在延迟着色管线中，G-Buffer 的通道布局直接决定了全管线的带宽基线。工业级引擎绝不直接使用原始浮点通道（如 `R32G32B32A32_FLOAT`），而是通过数学编码与位域压缩技术，将表面物理量压缩至最小位宽。

以现代基于物理的金属-粗糙度（PBR Metallic-Roughness）模型为例，光照阶段必须获取的核心参数包括：
- 世界空间位置 $\mathbf{p}$（或观察空间位置）；
- 世界空间表面法线 $\mathbf{n}$；
- 基础漫反射反照率 $\mathbf{c}_{	ext{albedo}}$；
- 微表面粗糙度 $\alpha$（Roughness）与金属度 $m$（Metallic）；
- 镜面反射强度 $F_0$（Specular）或遮挡因子 $AO$；
- 表面自发光辐射度 $\mathbf{L}_{	ext{emissive}}$；
- 运动矢量 $\mathbf{v}_{	ext{motion}}$（服务于 TAA、运动模糊与重建）；
- 材质模型标识符 $	ext{ID}_{	ext{material}}$（区分次表面、清漆层与毛发）。

世界空间位置的零显存存储推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
工业级 G-Buffer **严禁分配专用的位置纹理（Position Buffer）**。因为屏幕像素对应的三维空间位置，可以通过硬件深度缓冲区（`D32_FLOAT` 或 `D24_UNORM_S8_UINT`）结合相机的逆视图投影矩阵（Inverse View-Projection Matrix）严格数学逆运算获得。

设屏幕像素的标准化纹理坐标为 $(u, v) \in [0, 1]^2$，硬件深度缓冲采样值为 $d \in [0, 1]$（采用 Reversed-Z 规范时，近平面为 $1.0$，远平面为 $0.0$）。该像素对应的标准化设备坐标（NDC）为：

.. math::

   \mathbf{p}_{	ext{ndc}} = \begin{bmatrix} 2u - 1 \ 1 - 2v \ d \ 1 \end{bmatrix}

利用相机当前的齐次逆投影逆视图矩阵 $\mathbf{M}_{	ext{inv}} = (\mathbf{P} \cdot \mathbf{V})^{-1}$ 对其执行逆变换并完成透视除法：

.. math::

   \mathbf{p}_{	ext{world\_h}} = \mathbf{M}_{	ext{inv}} \cdot \mathbf{p}_{	ext{ndc}}, \quad \mathbf{p}_{	ext{world}} = \frac{\mathbf{p}_{	ext{world\_h}}.xyz}{\mathbf{p}_{	ext{world\_h}}.w}

此举直接从物理布局中砍掉了占用 12 字节的 Float3 位置纹理，消除了 25% 以上的写入总线带宽。

八面体法线编码 (Octahedral Normal Encoding)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
单位表面法线 $\|\mathbf{n}\| = 1$ 本质上仅具备 2 个自由度。传统方案将其直接截断存储于 `R8G8B8A8_UNORM` 中，存在明显的量化阶梯与通道浪费。现代管线采用 **八面体法线映射（Octahedral Mapping）**，将三维球面单位向量双射展开至二维正方形 $[-1, 1]^2$ 内，仅用 2 个 8 位通道（`R8G8_SNORM`）即可达到极高保真度：

.. math::

   \mathbf{p}_{	ext{oct}} = \frac{\mathbf{n}.xy}{\|\mathbf{n}.x\| + \|\mathbf{n}.y\| + \|\mathbf{n}.z\|}

当 $\mathbf{n}.z < 0$ 时，利用反射投影折叠外围象限：

.. math::

   \mathbf{p}_{	ext{oct}} = (1 - |\mathbf{p}_{	ext{oct}}.yx|) \cdot 	ext{sign}(\mathbf{p}_{	ext{oct}})

解算时只需一次绝对值与符号判断即可无损复原出三维法线 $\mathbf{n}$，量化误差小于 $0.005$ 弧度，显存占用从 12 字节骤降至 2 字节。

.. list-table:: 工业级 4-MRT 紧凑型 G-Buffer 显存布局契约
   :widths: 15 18 25 22 20
   :header-rows: 1
   :class: tight-table

   * - 目标附着 (Target)
     - 物理格式
     - 通道分配 (R / G / B / A)
     - 编码规范 / 色彩空间
     - 单像素内存
   * - **GBuffer A**
     - `R8G8B8A8_UNORM`
     - Albedo.R, Albedo.G, Albedo.B, AO
     - sRGB 伽马校正 $	o$ 线性空间
     - 4 Bytes
   * - **GBuffer B**
     - `R8G8B8A8_SNORM`
     - Normal.x (Oct), Normal.y (Oct), Roughness, Metallic
     - 八面体压缩法线，感知线性粗糙度
     - 4 Bytes
   * - **GBuffer C**
     - `R10G10B10A2_UNORM`
     - Emissive.R, Emissive.G, Emissive.B, MaterialID
     - 对数编码 HDR 自发光，4 类材质标识
     - 4 Bytes
   * - **GBuffer D**
     - `R16G16_FLOAT`
     - MotionVector.X, MotionVector.Y
     - 屏幕空间裁剪坐标差值 (UV 偏移)
     - 4 Bytes
   * - **Depth-Stencil**
     - `D32_FLOAT_S8_UINT`
     - Depth (32-bit Float), Stencil (8-bit)
     - Reversed-Z 无限远深度，材质掩码
     - 5 Bytes
   * - **合计总计**
     - **4 MRT + 1 Depth**
     - **全场景物理材质与可见性状态全集**
     - **单像素物理带宽严格控制在 21 Bytes**
     - **21 Bytes / Pixel**

移动平台片上分块内存 (Tile Memory) 优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在移动端基于贴片的延迟渲染架构（TBDR，如 Apple Silicon、Qualcomm Adreno、ARM Mali）中，GPU 具备物理片上高速 SRAM（Tile Buffer，容量通常为 $16 \sim 32	ext{ KB}$）。

现代图形 API（Vulkan Subpasses / Metal Memoryless Textures）允许将 G-Buffer 标记为**瞬态附着（Transient Attachments）**：
- G-Buffer 的写入仅发生在片上 Tile Memory 中；
- 光照阶段紧随其后直接从片上 SRAM 读取 G-Buffer 参数计算着色；
- 计算完成后，G-Buffer 附着直接丢弃（`VK_ATTACHMENT_STORE_OP_DONT_CARE`），仅将最终颜色写入外部 LPDDR 显存。

这一机制使移动端延迟着色的外部带宽消耗削减了 75% 以上，彻底颠覆了“移动端无法承载延迟着色”的传统技术偏见。

------------------------------------------------------------------------
41.3 Forward+ (Tiled Forward) 分块光照剔除微架构
------------------------------------------------------------------------

Forward+ 核心架构设计思想
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为在保留前向渲染优势（天然支持 MSAA、半透明渲染、异构材质无发散）的同时，彻底摆脱多光源 $O(M 	imes L)$ 复杂度陷阱，AMD 于 2012 年提出了 **Forward+（又称 Tiled Forward）渲染管线**。

Forward+ 的核心思想在于：**在进入前向材质着色前，预先在计算着色器（Compute Shader）中完成光源对屏幕空间网格的粗粒度分块相交测试，为每个屏幕分块（Tile）构建精准的局部活跃光源索引列表。**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       Forward+ 渲染管线三阶段物理流水线                   |
   +-------------------------------------------------------------------------+

   [ 阶段 1: 深度预通道 (Depth Pre-Pass) ]
     - 仅渲染不透明表面几何体的深度值 (输出至 Z-Buffer)，禁用像素着色器颜色计算
     - 产物: 物理深度缓冲区 (硬件 Early-Z 状态就绪)
                                   |
                                   v
   [ 阶段 2: 计算分块光照剔除 (Light Culling Compute Pass) ]
     - 将屏幕划分为 16x16 像素的网格分块 (Tiles)
     - 读取 Depth Buffer，通过片上共享内存 (LDS) 并行归约计算每个 Tile 的 [Z_min, Z_max]
     - 构造 Tile 视锥体包围盒 (Frustum AABB / 6 个平截头体平面)
     - 全场景光源球体/圆锥体与 Tile 视锥体做相交测试
     - 产物: 光源索引列表 (Light Index List) 与 Tile-光源网格映射表 (Light Grid)
                                   |
                                   v
   [ 阶段 3: 前向着色通道 (Forward Shading Pass) ]
     - 正常前向渲染所有几何体 (开启硬件 Depth Equal 测试，零 Overdraw 浪费)
     - 像素着色器根据当前像素坐标 (x, y) 定位其所属 Tile
     - 仅循环遍历该 Tile 内部的局部光源列表 (通常从数百个降至数个至数十个)
     - 完美支持 MSAA、透明物体使用同一套光源列表

分块视锥体构建与极值深度归约 (Min/Max Depth Reduction)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Forward+ 的分块尺寸通常选取为 $16 	imes 16$ 像素。在计算着色器中，每个线程组（Thread Group / Workgroup）分配 $16 	imes 16 = 256$ 个线程，一一对应 Tile 内部的 256 个像素。

第一步，每个线程读取自身像素的硬件深度，并通过片上共享内存（GroupShared / LDS）执行平行动行归约，提取当前分块内所有可见几何体的物理深度极值范围 $[Z_{	ext{min}}, Z_{	ext{max}}]$：

.. code-block:: hlsl

   groupshared uint s_MinZ_Uint;
   groupshared uint s_MaxZ_Uint;

   [numthreads(16, 16, 1)]
   void CS_TileLightCulling(uint3 dispatchThreadId : SV_DispatchThreadID,
                            uint3 groupThreadId : SV_GroupThreadID,
                            uint3 groupId : SV_GroupID)
   {
       // 初始化共享原子极值
       if (groupThreadId.x == 0 && groupThreadId.y == 0) {
           s_MinZ_Uint = 0xFFFFFFFF;
           s_MaxZ_Uint = 0;
       }
       GroupMemoryBarrierWithGroupSync();

       // 采样深度并转换为线性视空间深度 Z_view
       float rawDepth = DepthTexture.Load(int3(dispatchThreadId.xy, 0)).r;
       float linearZ = ConvertDeviceDepthToViewZ(rawDepth);

       // 利用原子操作在 256 线程间并行归约视空间深度极值
       uint zUint = asuint(linearZ);
       InterlockedMin(s_MinZ_Uint, zUint);
       InterlockedMax(s_MaxZ_Uint, zUint);
       GroupMemoryBarrierWithGroupSync();

       float minTileZ = asfloat(s_MinZ_Uint);
       float maxTileZ = asfloat(s_MaxZ_Uint);
       // ... 依据 minTileZ 与 maxTileZ 构建视锥体裁剪平截头体
   }

分块视锥体由 4 个基于屏幕 Tile 边界向视点发散的侧平面，结合 $Z_{	ext{min}}$ 近截面与 $Z_{	ext{max}}$ 远截面共同围成一个 6 平面三维凸多面体（Frustum Box）。

光源相交测试与数据布局
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在求得分块平截头体后，线程组内部的 256 个线程以步进循环的方式协同遍历全场景光源：

.. math::

   i_{	ext{light}} = 	ext{LocalThreadIndex} + k 	imes 256, \quad (k = 0, 1, 2, \dots)

对于点光源，将其位置转换为视空间坐标 $\mathbf{c}_L$，与分块平截头体的 6 个平面方程 $\mathbf{P}_j: \mathbf{n}_j \cdot \mathbf{x} + d_j = 0$ 进行带符号距离测试。若满足：

.. math::

   \forall j \in [0, 5], \quad (\mathbf{n}_j \cdot \mathbf{c}_L + d_j) \ge -r_L

则判定该点光源影响当前 Tile。相交成立时，通过原子操作 `InterlockedAdd` 递增分块共享计数器，将光源索引写入局部 LDS 缓存，并在线程同步后一次性刷写至全局显存的结构化缓冲区（StructuredBuffer）中。

Forward+ 的物理瓶颈：深度不连续性缺陷 (Depth Discontinuity)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Forward+ 管线在室外开阔场景或具有复杂前后景遮挡的场景中，暴露出了严重的微架构缺陷——**二维屏幕分块忽略了视线方向上的深度跨度**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             Forward+ (Tiled) 深度不连续性导致的视锥体膨胀问题              |
   +-------------------------------------------------------------------------+

   视点 Eye (0, 0, 0)
        \
         \    近处树枝/立柱 (Z_min = 2m)
          \       [||]
           \       |                      巨大虚警盲区 (Huge Empty Volume)
            \      |                  (沿途数十个不相关的光源被错误划入当前 Tile!)
             \     |                      *        *          *
              \    |                                                    远方天空/建筑 (Z_max = 500m)
               \   |                                                        [==================]
                \-------------------------------------------------------------------------------->
                 <----------------------- 膨胀的 Tile 视锥体深度跨度 ---------------------------->

当一个 $16 	imes 16$ 像素的 Tile 内部同时包含前景的一根细立柱（$Z_{	ext{min}} = 2	ext{m}$）与背景的远山/天空（$Z_{	ext{max}} = 500	ext{m}$）时：
- 该 Tile 的视锥体深度范围被强制拉伸至 $[2	ext{m}, 500	ext{m}]$；
- 空间体积急剧膨胀，导致物理上处于半空中、根本未照射到任何实际可见表面的数十个光源，全被判定为与该 Tile 相交；
- 前向着色阶段，属于该分块的所有像素被迫执行大量无意义的光照循环，直接冲垮了着色器性能。

这一本质缺陷催生了三维空间更细粒度的光照划分——**分簇光照着色体系（Clustered Shading）**。

------------------------------------------------------------------------
41.4 Clustered Shading (分簇光照剔除) 算法与数据结构
------------------------------------------------------------------------

三维空间分簇 (Cluster / Froxel) 的数学建模
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Clustered Shading 由 Ola Olsson 等人于 2012 年提出，其核心构想是：**不仅在屏幕空间将视锥体沿二维横纵向（X, Y）划分，更在视线深度方向（Z）沿对数尺度切分为离散的切片，将整个视锥体剖分为数以万计的三维微视锥台（Clusters，在体积雾中亦称为 Froxels）。**

视锥体三维分簇划分维度通常定义为：
- $S_x$：水平方向划分段数（例如 $16 \sim 64$ 分块）；
- $S_y$：垂直方向划分段数（例如 $9 \sim 36$ 分块）；
- $S_z$：视线深度方向切片数（例如 $16 \sim 32$ 层切片）。
- 全视锥体总簇数为 $N_{	ext{clusters}} = S_x 	imes S_y 	imes S_z$（例如 $32 	imes 16 	imes 24 = 12,288$ 个独立微立方体）。

对数深度切片公式与物理合理性推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
如果沿深度方向采用线性均匀切片（Linear Slicing），由于透视投影的锥形扩散特性，近处的簇体积微小，而远处的簇体积将呈二次方剧烈发散，使得远处的簇丧失空间分辨能力。

Clustered 算法严格采用**指数/对数深度切片（Logarithmic Depth Slicing）**，使切片厚度随深度呈几何级数递增：

.. math::

   Z_k = Z_{	ext{near}} \cdot \left( \frac{Z_{	ext{far}}}{Z_{	ext{near}}} \right)^{\frac{k}{S_z}}, \quad (k = 0, 1, 2, \dots, S_z)

对于任意一个在观察空间深度为 $Z_{	ext{view}} \in [Z_{	ext{near}}, Z_{	ext{far}}]$ 的片元或光照点，推导其所属深度切片索引 $k$ 的连续映射函数：

.. math::

   \frac{Z_{	ext{view}}}{Z_{	ext{near}}} = \left( \frac{Z_{	ext{far}}}{Z_{	ext{near}}} \right)^{\frac{k}{S_z}} \implies \ln\left(\frac{Z_{	ext{view}}}{Z_{	ext{near}}}\right) = \frac{k}{S_z} \ln\left(\frac{Z_{	ext{far}}}{Z_{	ext{near}}}\right)

由此得出在着色器中执行的常数时间极速索引定位公式：

.. math::

   k = \left\lfloor \frac{\ln(Z_{	ext{view}}) - \ln(Z_{	ext{near}})}{\ln(Z_{	ext{far}}) - \ln(Z_{	ext{near}})} \cdot S_z \right\rfloor = \left\lfloor \ln(Z_{	ext{view}}) \cdot 	ext{Scale}_z + 	ext{Bias}_z \right\rfloor

其中常数因子：

.. math::

   	ext{Scale}_z = \frac{S_z}{\ln(Z_{	ext{far}} / Z_{	ext{near}})}, \quad 	ext{Bias}_z = -\frac{S_z \cdot \ln(Z_{	ext{near}})}{\ln(Z_{	ext{far}} / Z_{	ext{near}})}

该公式的精妙之处在于：在像素着色器中，只需**一次对数运算（调用硬件极速 SFU 的 `log2` 指令）、一次乘法与一次加法**，即可直接定位当前像素所在的精确三维空间切片，彻底消除了分块内的深度跨度膨胀！

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                对数空间分簇 (Logarithmic Clustered Shading) 拓扑         |
   +-------------------------------------------------------------------------+

   视点 Eye (0,0,0)
         \  Cluster[k=0] (薄)
          \   |  Cluster[k=1]
           \  |   |   Cluster[k=2] (厚度指数增加)
            \ |   |    |         Cluster[k=3]
             \|   |    |          |
              +---+----+----------+-------------------+--------------------->
             近平面                 远平面 (切片大小与空间几何扩散完美对齐)

紧凑双级间接光照网格 (Two-Level Light Grid Buffer)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了在 GPU 上以极小显存存储每个 Cluster 包含的光源索引，工业级管线设计了连续紧凑的扁平化缓冲区架构：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |               工业级双级连续紧凑型 Clustered Light Grid 内存布局          |
   +-------------------------------------------------------------------------+

   [ 缓冲区 1: Cluster Grid Buffer (结构化数组，大小固定为 N_clusters) ]
     每个元素为一个 uint2 紧凑结构体 (共 8 字节):
     +-----------------------------------+-----------------------------------+
     | uint offset                       | uint count                        |
     | (全局光源索引池中的起始物理偏移地址)  | (照射到该 Cluster 的活跃光源总数量) |
     +-----------------------------------+-----------------------------------+
       Cluster 0:  offset = 0, count = 3   ---+
       Cluster 1:  offset = 3, count = 1      |
       Cluster 2:  offset = 4, count = 0      |  连续致密内存布局 (零碎片)
       ...                                    v
   [ 缓冲区 2: Global Light Index List (扁平化光源索引连续数组) ]
     +-----------------------------------------------------------------------+
     | LightID: 12 | LightID: 45 | LightID: 88 | LightID: 3 | ...            |
     +-----------------------------------------------------------------------+
       ^                                         ^
       |--- Cluster 0 的 3 个光源索引 (12,45,88)  |--- Cluster 1 的 1 个光源索引 (3)

着色器读取时，首先计算三维索引：

.. math::

   	ext{ClusterIndex} = x_{	ext{tile}} + y_{	ext{tile}} \cdot S_x + k_{	ext{slice}} \cdot (S_x \cdot S_y)

随后单次内存事务提取 `ClusterGrid[ClusterIndex]`，获得 `(offset, count)`，紧接着在连续缓存中循环读取 `count` 个光源执行着色。全局数据致密无碎片，且各像素只访问物理相交的真子集，Cache 命中率达到极致。

------------------------------------------------------------------------
41.5 现代三种主流管线核心架构对比与选型法则
------------------------------------------------------------------------

为了在多变的项目需求与硬件平台之间建立科学的工程选型决策标准，我们将传统前向、传统延迟、Forward+、Clustered Forward 以及结合了 G-Buffer 的 Clustered Deferred 进行多维度的系统对比。

.. list-table:: 现代主流工业级渲染管线物理架构特性全景横向矩阵
   :widths: 16 16 17 17 17 17
   :header-rows: 1
   :class: tight-table

   * - 核心评估维度
     - 经典前向 (Forward)
     - 经典延迟 (Deferred)
     - 分块前向 (Forward+)
     - 分簇前向 (Clustered Fwd)
     - 分簇延迟 (Clustered Def)
   * - **时间复杂度**
     - $O(M \cdot D \cdot L)$
     - $O(MD) + O(WH \cdot L_v)$
     - $O(MD) + O(WH \cdot L_t)$
     - $O(MD) + O(WH \cdot L_c)$
     - $O(MD) + O(WH \cdot L_c)$
   * - **动态光源容量**
     - 极低 ($<8$ 个)
     - 高 ($100 \sim 1000$ 个)
     - 极高 ($1000+$ 个)
     - 工业级无限 ($10000+$)
     - 工业级无限 ($10000+$)
   * - **显存读写带宽**
     - 极低 (仅 FrameBuffer)
     - 极高 (海量 G-Buffer)
     - 极低 (需 Depth Prepass)
     - 极低 (需 Depth Prepass)
     - 极高 (MRT + Cluster)
   * - **硬件 MSAA 支持**
     - 原生完美支持
     - 架构冲突 (需手工解析)
     - 原生完美支持
     - 原生完美支持
     - 架构冲突 (高成本)
   * - **半透明物体光照**
     - 原生支持
     - 无法支持 (需 Forward)
     - 原生支持 (共享 Tile)
     - 原生完美支持 (按 3D 簇)
     - 需回退 Clustered Fwd
   * - **异构复杂材质多样性**
     - 极高 (独立 Shader)
     - 受限 (固定 G-Buffer)
     - 极高 (独立 Shader)
     - 极高 (独立 Shader)
     - 受限 (固定 G-Buffer)
   * - **深度断层开销退化**
     - 无退化
     - 无退化
     - **严重退化 (Tile 膨胀)**
     - **免疫深度断层**
     - **免疫深度断层**
   * - **典型商业引擎应用**
     - 极简移动手游
     - Unity Built-in, 早期 UE4
     - 现代 VR 项目, 特殊管线
     - 寒霜 (Frostbite), Doom
     - **UE5, 孤岛危机, 绝大部分 AAA**

工业级选型决策树
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
基于上述物理事实，现代商业引擎的渲染架构选型准则可高度收敛为三条黄金法则：

1. **AAA 级画质、重度屏幕空间效果与次时代网格管线 $	o$ 选用 Clustered Deferred**：
   - 依赖 G-Buffer 实现高精度次时代特效（SSAO、SSR、接触阴影、贴花 Decals、运动模糊、时间性超分辨率 TSR/DLSS）；
   - 结合虚拟几何体系统（如 UE5 Nanite），由于 Nanite 输出全场景的 VisBuffer（仅存储图元 ID 与深度），必须通过延迟阶段解包属性并利用 Clustered Light Grid 驱动成千上万个点光与局部阴影；
2. **高帧率追求、VR 双目立体渲染与移动平台 $	o$ 选用 Clustered Forward**：
   - 虚拟现实（VR）要求双目 90Hz/120Hz 刷新率，且必须开启硬件 $4	imes$ MSAA 消除几何高频走样；
   - Clustered Forward 零 G-Buffer 带宽开销，半透明粒子直接复用 3D 光照簇，彻底杜绝深度断层开销；
3. **轻量级移动端与带宽受限嵌入式 SoC $	o$ 选用 Forward+ (或结合 Tile Memory 的轻量延迟)**：
   - 在缺乏高级计算着色器多线程分簇能力的老旧硬件上，以轻量级 2D Tile 光照剔除作为性价比折中。

------------------------------------------------------------------------
41.6 工业级 Clustered Light Culling Compute Shader 核心实现
------------------------------------------------------------------------

以下给出遵循 **HLSL (Shader Model 6.0+)** 规范构建的工业级 Clustered 光照裁剪核心着色器源码。代码完整实现了视锥体对数空间计算、Cluster 空间包围盒（AABB）生成、球体相交测试，以及基于原子操作的双级连续致密光照网格输出：

.. code-block:: hlsl

   // =========================================================================
   // File: ClusteredLightCulling.hlsl
   // Architecture: High-Performance Clustered Light Assignment Compute Shader
   // Standard: HLSL Shader Model 6.0+, Explicit Threadgroup Shared Memory
   // =========================================================================

   #define CLUSTER_X 16
   #define CLUSTER_Y 9
   #define CLUSTER_Z 24
   #define TOTAL_CLUSTERS (CLUSTER_X * CLUSTER_Y * CLUSTER_Z)
   #define THREADS_PER_GROUP 64
   #define MAX_LIGHTS_PER_CLUSTER 128

   // -------------------------------------------------------------------------
   // 1. 结构化数据契约定义
   // -------------------------------------------------------------------------
   struct PointLight {
       float3 positionView;  // 观察空间位置
       float  radius;        // 影响物理半径
       float3 color;         // 辐射能量 / 强度
       float  falloff;       // 衰减衰减指数
   };

   struct ClusterAABB {
       float4 minPoint;      // 观察空间最小顶点 (xyz, padding)
       float4 maxPoint;      // 观察空间最大顶点 (xyz, padding)
   };

   struct LightGrid {
       uint offset;          // 全局紧凑索引列表物理起始偏移
       uint count;           // 当前簇包含的实际相交光源数
   };

   // -------------------------------------------------------------------------
   // 2. 资源绑定 (SRV / UAV / ConstantBuffer)
   // -------------------------------------------------------------------------
   cbuffer ClusterUniforms : register(b0) {
       float4x4 g_InverseProjection;
       float2   g_ScreenDimensions;
       float    g_NearZ;
       float    g_FarZ;
       float    g_LogGridRatio; // = CLUSTER_Z / log2(g_FarZ / g_NearZ)
       uint     g_ActiveLightCount;
   };

   StructuredBuffer<PointLight>   g_AllLights          : register(t0);
   StructuredBuffer<ClusterAABB>  g_ClusterAABBs       : register(t1);

   RWStructuredBuffer<LightGrid>  g_RWClusterLightGrid : register(u0);
   RWStructuredBuffer<uint>       g_RWGlobalLightList  : register(u1);
   RWStructuredBuffer<uint>       g_RWGlobalCounter    : register(u2); // 单元素全局计数器

   // -------------------------------------------------------------------------
   // 3. 片上共享内存 (Threadgroup Shared Memory - LDS)
   // -------------------------------------------------------------------------
   groupshared uint s_ClusterLightCount;
   groupshared uint s_ClusterGlobalOffset;
   groupshared uint s_ClusterLightIndices[MAX_LIGHTS_PER_CLUSTER];

   // -------------------------------------------------------------------------
   // 4. 辅助空间数学求交函数：球体与 AABB 求交 (Arvo 算法)
   // -------------------------------------------------------------------------
   bool TestSphereAABB(float3 center, float radius, float3 boxMin, float3 boxMax) {
       float distanceSquared = 0.0f;
       
       // 沿三轴寻找 AABB 上距离球心最近的投影点并累加平方欧氏距离
       [unroll]
       for (int i = 0; i < 3; ++i) {
           float v = center[i];
           if (v < boxMin[i]) distanceSquared += (boxMin[i] - v) * (boxMin[i] - v);
           if (v > boxMax[i]) distanceSquared += (v - boxMax[i]) * (v - boxMax[i]);
       }
       return distanceSquared <= (radius * radius);
   }

   // -------------------------------------------------------------------------
   // 5. Clustered 光照裁剪计算内核
   // 每个 Thread Group 独占处理一个独立的 3D Cluster (SV_GroupID.x = 0 ~ 3455)
   // -------------------------------------------------------------------------
   [numthreads(THREADS_PER_GROUP, 1, 1)]
   void CS_ClusteredLightCulling(uint3 threadIdInGroup : SV_GroupThreadID,
                                uint3 groupId           : SV_GroupID)
   {
       uint clusterIndex = groupId.x;
       if (clusterIndex >= TOTAL_CLUSTERS) return;

       // 1. 初始化当前分簇的共享计数器
       if (threadIdInGroup.x == 0) {
           s_ClusterLightCount = 0;
       }
       GroupMemoryBarrierWithGroupSync();

       // 提取当前 Cluster 的观察空间包围盒 (AABB)
       ClusterAABB aabb = g_ClusterAABBs[clusterIndex];
       float3 boxMin = aabb.minPoint.xyz;
       float3 boxMax = aabb.maxPoint.xyz;

       // 2. 线程组内部多线程步进并行测试全场景光源
       for (uint lightIndex = threadIdInGroup.x; 
            lightIndex < g_ActiveLightCount; 
            lightIndex += THREADS_PER_GROUP) 
       {
           PointLight light = g_AllLights[lightIndex];

           // 执行球体与当前 Cluster AABB 的几何相交裁决
           if (TestSphereAABB(light.positionView, light.radius, boxMin, boxMax)) {
               // 相交成立，通过原子操作原子分配写入局部 LDS 数组的索引槽位
               uint localSlot;
               InterlockedAdd(s_ClusterLightCount, 1, localSlot);

               if (localSlot < MAX_LIGHTS_PER_CLUSTER) {
                   s_ClusterLightIndices[localSlot] = lightIndex;
               }
           }
       }
       GroupMemoryBarrierWithGroupSync();

       // 3. 将当前 Cluster 的光源集合打包申请并写入全局连续输出缓冲区
       if (threadIdInGroup.x == 0) {
           uint finalCount = min(s_ClusterLightCount, (uint)MAX_LIGHTS_PER_CLUSTER);
           
           // 在全局紧凑列表里原子申请一段连续的存放区间
           InterlockedAdd(g_RWGlobalCounter[0], finalCount, s_ClusterGlobalOffset);

           // 写入该 Cluster 的双级索引网格描述符
           LightGrid grid;
           grid.offset = s_ClusterGlobalOffset;
           grid.count  = finalCount;
           g_RWClusterLightGrid[clusterIndex] = grid;
       }
       GroupMemoryBarrierWithGroupSync();

       // 4. 多线程协作将 LDS 中的光源索引批量刷写到全局连续列表
       uint finalCount = min(s_ClusterLightCount, (uint)MAX_LIGHTS_PER_CLUSTER);
       for (uint i = threadIdInGroup.x; i < finalCount; i += THREADS_PER_GROUP) {
           g_RWGlobalLightList[s_ClusterGlobalOffset + i] = s_ClusterLightIndices[i];
       }
   }

   // -------------------------------------------------------------------------
   // 6. 着色阶段快速寻址解码函数 (供 Forward PS 或 Deferred CS 共享调用)
   // -------------------------------------------------------------------------
   uint GetClusterIndex(float2 screenUV, float viewZ) {
       uint tileX = (uint)(screenUV.x * CLUSTER_X);
       uint tileY = (uint)(screenUV.y * CLUSTER_Y);
       
       // 对数深度切片核心计算 (单指令 log2 与乘加)
       float logZ = log2(viewZ / g_NearZ);
       uint sliceZ = (uint)clamp(logZ * g_LogGridRatio, 0.0f, (float)(CLUSTER_Z - 1));

       return tileX + (tileY * CLUSTER_X) + (sliceZ * CLUSTER_X * CLUSTER_Y);
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章作为 **Part 9: 前沿工业渲染管线与性能调优** 的开篇之作，系统解构了现代工业级渲染管线的演进脉络与微架构物理底座：
1. **渲染管线的演进原动力**：传统前向渲染受困于 $O(M 	imes L)$ 几何与光源交叉膨胀及遮挡过绘制；传统延迟着色通过 G-Buffer 彻底解耦可见性与着色计算，但引出了沉重的内存总线带宽负载并割裂了半透明与 MSAA；
2. **G-Buffer 紧凑压缩哲学**：深入推导了从硬件深度反算三维位置的无显存消耗模型、八面体法线压缩（Octahedral Normal Encoding）以及移动端 TBDR 片上高速缓存（Tile Memory）对外部带宽的节约；
3. **Forward+ 分块光照体系及其局限**：解构了基于计算着色器的 2D Tile 视锥体极值深度归约与光照剔除，揭示了其在大深度差遮挡边缘产生的“视锥体膨胀与虚警遍历”微架构缺陷；
4. **Clustered Shading 分簇三维空间划分**：系统推导了对数尺度深度切片的数学推导与物理合理性，解构了双级紧凑连续光照网格（Cluster Grid Buffer）数据结构，实现了对成千上万动态光源与半透明/MSAA 材质的全面兼顾与性能飞跃。

光照计算的空间复杂度已被 Clustered 架构从几何层面完全剥离，但面对包含数十亿三角形的高保真三维世界，CPU 端的 Draw Call 组织、视锥体裁剪与驱动交互仍然是限制场景密度的最大枷锁！
在下一章（**Chapter 42: GPU-Driven 渲染管线深度演进：间接绘制 (Indirect Draw)、Hi-Z 剔除与两阶段遮挡**）中，我们将全面迈向现代显卡的终极形态——**让 GPU 接管全场景绘制指令生成的纯 GPU 自驱动流水线！**
