========================================================================
Chapter 43: 几何虚拟化与无限细节：UE5 Nanite 微多边形光栅化、BVH 视锥剔除与软光栅
========================================================================

.. note:: 前置背景与认知承接
   在 Chapter 42 中，我们深入剖析了 GPU-Driven 渲染管线的核心架构，通过间接绘制（Indirect Draw）、全局无绑定资源池（Bindless Mega-Buffers）以及基于层次化深度金字塔的两阶段遮挡剔除（Two-Phase Hi-Z Occlusion Culling），将场景调度与可见性裁决的控制权从 CPU 完全移交至 GPU Compute Shader，彻底粉碎了千万级物体场景在 CPU 侧的提交开销。

   然而，GPU-Driven 流水线本质上解决的是**“实例级（Instance-Level）”**与**“批次级（Batch-Level）”**的粗粒度调度危机。当摄影机无限逼近复杂表面，或者场景中充斥着数千万乃至数十亿由高精度雕刻、CAD 模型直接导入的影视级多边形时，图形系统将不可避免地撞上现代微架构最为坚硬的物理死墙——**硬件光栅化的微多边形危机（Micro-Polygon Crisis）**。当大量三角形的屏幕投影面积缩小至亚像素级（Sub-Pixel，不足 1 个像素或几个像素宽）时，固定功能光栅化器以 $2 	imes 2$ 像素四方块（Pixel Quad）为基准的并行执行模型将彻底崩溃，辅助线程（Helper Invocations）爆炸式吞噬算力，顶点着色与图元装配硬件陷入严重过载。

   为了从根本上颠覆这一物理瓶颈，Epic Games 在 Unreal Engine 5 中确立了革命性的**几何虚拟化体系——Nanite**。Nanite 的核心哲学与虚拟内存（Virtual Memory）和虚拟纹理（Virtual Texturing）一脉相承：**将几何网格剖分为紧凑自包含的网格簇（Cluster/Meshlet），构建多级分层有向无环图（Cluster DAG），在 GPU 上流式自适应评估屏幕误差并动态选择切割面；针对宏大多边形采用硬件光栅化，针对微多边形则切换至纯 Compute Shader 软件光栅化，最终输出仅记录几何拓扑的极简可见性缓冲区（Visibility Buffer），实现着色解耦**。本章将深入 Nanite 底层微架构，系统推导 Cluster DAG、软硬件混合光栅化与可见性着色管线的物理实现全流程。

------------------------------------------------------------------------
43.1 几何微多边形危机与传统流水线的物理崩溃
------------------------------------------------------------------------

亚像素四方块过着色惩罚 (Quad Overshading Penalty)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
现代 GPU 光栅化微架构必须在屏幕空间以 $2 	imes 2$ 像素组成的“四方块（Pixel Quad）”为最小调度单位并发发射线程束（Warp / Wavefront）。这种硬件约束的物理根源在于：**像素着色器中计算纹理采样 Mipmap 级别与各向异性过滤所需的屏幕空间偏导数（`ddx` / `ddy`），必须依赖四方块内水平与垂直相邻像素的属性差分**。

当屏幕上的多边形尺寸正常（覆盖数十或数百个像素）时，四方块内绝大多数像素均处于多边形内部，硬件利用率接近 100%。然而，当三角面片缩小至亚像素级别时，微架构遭遇灾难性坍塌：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                微多边形引发的 Pixel Quad 辅助线程爆炸与算力坍塌            |
   +-------------------------------------------------------------------------+

   [ 理想大三角形光栅化 ]              [ 亚像素微多边形光栅化 (Nanite 前夕) ]
   +-------+-------+                  +-------+-------+
   | P0    | P1    |                  | P0(空)| P1(空)|  <-- 三角形仅覆盖 P2 单个像素
   | (有效)| (有效)|                  | (无效)| (无效)|      P0, P1, P3 被迫作为 Helper Lane
   +-------+-------+                  +-------+-------+      执行全套 PS 计算，结果被丢弃！
   | P2    | P3    |                  | P2    | P3(空)|      
   | (有效)| (有效)|                  | (有效)| (无效)|      **有效算力效率: 25% (甚至更低)**
   +-------+-------+                  +-------+-------+

在亚像素多边形场景下，一个三角形往往仅覆盖四方块中的 1 个像素。为了保证差分指令正常执行，GPU 硬件线程控制器必须将四方块内其余 3 个未覆盖像素标记为**辅助线程（Helper Lanes / Inactive Lanes）**。这些辅助线程同样完整加载常量缓冲、采样纹理、执行复杂的 PBR 表面着色，但在最终输出阶段被硬件强制丢弃其颜色与深度写入！

设像素着色器指令执行时钟周期为 $C_{	ext{ps}}$，覆盖像素数为 $N_{	ext{covered}}$，生成的四方块总数为 $N_{	ext{quad}}$。实际消耗的计算总周期为：

.. math::

   C_{	ext{total}} = N_{	ext{quad}} 	imes 4 	imes C_{	ext{ps}}

当平均三角形面积 $\bar{A} \approx 0.5	ext{ 像素}$ 时，产生每个有效着色像素平均需要消耗 $2 \sim 4$ 个四方块。这意味着 **高达 75% 至 90% 以上的 GPU 片元着色器 ALU 算力和显存采样带宽被彻底空耗在辅助线程的废弃计算上**。

几何前端吞吐瓶颈与离散 LOD 的局限
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
除了像素阶段的四方块过着色惩罚，传统流水线在处理海量多边形时还面临三大根本性瓶颈：

1. **顶点装配与索引带宽瓶颈**：传统网格使用 32 位顶点位置（12 字节）结合法线、切线、UV 与 32 位索引缓冲。渲染 1000 万个三角形仅索引缓冲区便占据 $120\,	ext{MB}$，几何前端在读取未压缩顶点数据时迅速打满显存总线；
2. **离散 LOD 的跳变伪影 (Popping Artifacts)**：传统美术流水线手工制作 LOD 0 到 LOD 4。不同层级切换时，物体轮廓发生突兀跳变，阴影贴图随之闪烁；为了平滑跳变引入的跨淡入淡出（Cross-Fading）在过渡期双重绘制几何体，使过绘制（Overdraw）恶化一倍；
3. **裂缝灾难 (Cracking Dilemma)**：如果允许单个物体内部不同部位独立切换不同 LOD，由于高精度区域与低精度区域在交界处的边无法精确对齐，几何裂缝（Holes/T-Junctions）将直接暴露天空球底色，导致自适应细节在工程上难以落地。

------------------------------------------------------------------------
43.2 Nanite 核心数据结构：Cluster 聚类与分层有向无环图 (Cluster DAG)
------------------------------------------------------------------------

Cluster 网格簇：自包含几何微元
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Nanite 彻底摒弃了以“整网格（Mesh）”或“材质子网格（Submesh）”为调度的传统单位，将三维模型切分为极小且尺寸受严格约束的几何块——**Cluster（簇 / Meshlet）**：

- **严格硬件尺寸限制**：每个 Cluster 内部固定包含 **最多 128 个三角形**，以及 **最多 64 个去重后的独立顶点**；
- **自包含局部坐标量化**：网格簇内部不再存储全局 32 位世界浮点坐标，而是以 Cluster 的三维 AABB 中心为原点，使用局部 10 位到 12 位定点数（Fixed-Point）进行相对坐标编码。顶点法线与切线则通过八面体编码（Octahedral Normal Encoding）压缩为 16 位整型。
- **显存占用骤减**：相比传统未经量化的顶点格式（单顶点 32~48 字节），Nanite Cluster 的顶点数据被高密度压缩至单顶点不足 5 字节，拓扑索引以 8 位局部微索引（Local Micro-Index, `uint8`）连续排列，全量适配片上 Shared Memory / LDS 读写对齐。

Cluster DAG 的构建拓扑与化简合并
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了在运行时支持任意连续视距下的动态无缝渐变，Nanite 在离线预处理阶段通过自底向上（Bottom-Up）的迭代图化简算法，构建了一个**分层有向无环图（Cluster Directed Acyclic Graph - Cluster DAG）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Nanite 分层有向无环图 (Cluster DAG) 拓扑与切割面演进          |
   +-------------------------------------------------------------------------+

   [ Root Level: 极粗粒度 (LOD N) ]             [ Cluster R0 ]
                                                   /        \
   [ Mid Level: 渐进过渡 (LOD 1) ]        [ Cluster M0 ]   [ Cluster M1 ]
                                             /      \       /      \
   [ Leaf Level: 雕刻原始几何 (LOD 0) ] [ C0 ]   [ C1 ]   [ C2 ]   [ C3 ]
   ---------------------------------------------------------------------------
   [ 动态视距切割面 (Active Cut) ] ===> 截断 DAG，提取不同深度活跃簇集合渲染

构建 Cluster DAG 的核心算子递归执行如下步骤：

1. **初始聚类 (Initial Clustering)**：将原始原始精度网格（LOD 0）按照空间局部性划分为一系列叶子节点簇 $\{C_0, C_1, C_2, \dots, C_k\}$，每个簇含 128 个三角形；
2. **分组选区 (Grouping)**：利用图划分算法（如 METIS），将拓扑相邻的 $4$ 个簇聚合成一个 Group（包含 $4 	imes 128 = 512$ 个三角形）；
3. **闭锁边界与局部化简 (Locked-Boundary Simplification)**：
   - 提取该 Group 的**外轮廓共享边界边（Shared Boundary Edges）**并将其物理“锁定”（禁止移动或折叠边缘顶点）；
   - 对 Group 内部的非锁定几何拓扑执行 Quadric Error Metrics (QEM) 二次误差边折叠，将 512 个三角形**腰斩化简为严格的 256 个三角形（恰好构成 2 个上层父节点 Cluster）**；
4. **递归向上合并**：以新生成的父节点 Cluster 作为新一级输入，重复步骤 2 与 3，直至整个模型最终收敛为唯一的根节点 Cluster。

.. list-table:: 传统离散树形 LOD 与 Nanite Cluster DAG 物理对比矩阵
   :widths: 22 25 25 28
   :header-rows: 1
   :class: tight-table

   * - 架构维度
     - 传统离散 LOD 链
     - 传统树形网格 (Hierarchical Tree)
     - Nanite Cluster DAG
   * - **拓扑组织形态**
     - $N$ 个互相孤立的全网格拷贝
     - 严格单向单亲树（Single Parent Tree）
     - **多对多多亲图（Directed Acyclic Graph）**
   * - **调度与流送粒度**
     - 整网格显存加载 (巨型缓冲区)
     - 粗粒度包围块 (几十万面)
     - **极细网格簇 (固定 128 三角形)**
   * - **交界缝隙控制**
     - 无缝隙控制 (整体换模型)
     - 依赖共享顶点对齐 (容易出现裂缝)
     - **外部轮廓锁定 + 严格成组父子切换 (数学零裂缝)**
   * - **屏幕误差连续性**
     - 阶梯式突变跳跃 (明显 Popping)
     - 块状局部切换跳跃
     - **亚像素级屏幕连续微平滑自适应**

屏幕投影误差判定准则与裂缝规避证明
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
DAG 如何确保运行时“无缝切换”且“零裂缝”？其秘密在于 DAG 的**成组替换机制（Group-Based Replacement）**与数学误差边界：

在预处理化简时，每个 Cluster 节点记录两个核心度量指标：
1. **自身几何误差 $\epsilon_{	ext{self}}$ 与包围球**：本簇相对于原始模型的最大空间几何偏离距离；
2. **父级依赖几何误差 $\epsilon_{	ext{parent}}$ 与包围球**：将其化简为更粗父级簇时所引入的更大空间误差。

在运行时渲染时，GPU Compute Shader 将三维包围球投影至屏幕空间，计算其在当前视口像素下的**屏幕空间投影像素误差 $\rho$**：

.. math::

   \rho = \frac{\epsilon 	imes r_{	ext{screen}}}{d_{	ext{view}} 	imes 	an(\frac{	ext{FOV}}{2})}

Nanite 设定全局质量阈值 $	au$（通常设为 $	au = 1.0	ext{ 像素}$）。一个 Cluster 成为当前渲染活跃切割面（Cut）成员的**充要条件**为：

.. math::

   	ext{Active}(C) \iff (\rho_{	ext{parent}} > 	au) \land (\rho_{	ext{self}} \le 	au)

- $\rho_{	ext{parent}} > 	au$：意味着若使用更粗糙的父节点，其引起的屏幕形变误差超过了 1 个像素，不可接受，必须展开至更精细层级；
- $\rho_{	ext{self}} \le 	au$：意味着本节点的自身误差在当前屏幕上小于 1 个像素，人眼无法分辨，无需继续向下细分！

**裂缝彻底消除的物理证明**：
由于化简时一个 Group（4 个子簇）的外部轮廓边被绝对锁定，子簇集（4 个簇）与父簇集（2 个簇）的物理外边界几何形状完全等价。当屏幕误差跨越阈值时，**系统强制且原子性地将整个 Group 的 4 个子簇同步替换为 2 个父簇，或者逆向替换**。任何相邻 Group 无论处于何种细分深度，它们之间的公共外边界都严格保持相同的锁死轮廓，因此在数学上**绝对不可能产生任何悬空边（T-Junctions）或几何破洞！**

------------------------------------------------------------------------
43.3 GPU-Driven 层次化视锥、背面与 Hi-Z 剔除流水线
------------------------------------------------------------------------

持久化线程与动态无锁任务分发队列
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Nanite 渲染流水线在每一帧启动时，CPU 仅需向 GPU 提交单次间接计算分发（`DispatchIndirect`）。GPU 端维护一个全局工作队列（Global Task Queue），包含待处理的候选节点。Compute Shader 采用持久化线程块（Persistent Wavefronts）并发拉取队列条目：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             Nanite GPU-Driven Cluster 层次遍历与无锁剔除管线             |
   +-------------------------------------------------------------------------+

   [ 顶层任务: 遍历根节点实例 ] ---> [ 实例级粗粒度包围盒剔除 (Frustum & Hi-Z) ]
                                             |
                                             v (展开通过实例)
   [ 写入 Global Candidate Queue ] <---------+
                 |
                 v (Compute Shader 并发多波次消费队列)
   +-------------------------------------------------------------------------+
   | 对当前候选 Cluster 执行三级硬件级极限剪枝:                              |
   |   1. 视锥体相交测试 (Frustum Culling)                                   |
   |   2. 法线圆锥背面剔除 (Cluster Cone Backface Culling)                   |
   |   3. 两阶段 Hi-Z 遮挡判定 (Hierarchical Z-Buffer Occlusion Culling)     |
   |   4. DAG 屏幕投影误差阈值判定 (Screen-Space Error Metric)               |
   +-------------------------------------------------------------------------+
        |                                        |
        v (误差超标: 细分继续推入下级节点)        v (误差达标且可见: 最终可见叶子簇)
   [ 产生子节点回填至 Queue ]                 [ 写入最终待光栅化命令列表 ]
                                                 |
                                                 v
                                 [ 面积判定: 决定软硬件光栅化分流 ]

法线圆锥背面剔除 (Normal Cone Backface Culling)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在传统管线中，背面剔除是在光栅化器中逐三角形计算叉乘面积执行。而在 Nanite 中，由于 128 个三角形处于同一空间网格簇，预处理阶段会为该簇计算一个**包围法线圆锥（Bounding Cone of Normals）**，由圆锥中心轴方向向量 $\vec{A}$ 与半角余弦值 $\cos	heta$ 唯一确定：

.. math::

   \vec{V}_{	ext{cam}} = 	ext{normalize}(\vec{P}_{	ext{cluster}} - \vec{P}_{	ext{eye}})

若相机视线向量 $\vec{V}_{	ext{cam}}$ 与圆锥轴向 $\vec{A}$ 的夹角满足：

.. math::

   \vec{A} \cdot \vec{V}_{	ext{cam}} > \sin	heta

则数学上保证该簇内的 **全部 128 个三角形均处于背面朝向**。Compute Shader 仅需执行单次点积比较，即可在一条指令周期内将整整 128 个三角形一次性全部剔除，完全不进入光栅化阶段！

两阶段两级别 Hi-Z 遮挡判定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
与 Chapter 42 所述的两阶段遮挡思想深度融合，Nanite 在 Cluster 粒度上严格实施两阶段 Hi-Z 遮挡测试：
1. **第一阶段 (Phase 1)**：使用上一帧生成的物理 Hi-Z 缓冲。被历史 Hi-Z 判为被遮挡的 Cluster 直接压入不可见候选缓冲区，可见 Cluster 立即光栅化并写入最新的当前帧深度缓冲；
2. **Hi-Z 动态金字塔重构**：从最新深度中实时提取局部 Mip 链；
3. **第二阶段 (Phase 2)**：将不可见候选集基于最新当前帧 Hi-Z 二次复核，仅补画露出表面。

这一机制将可见网格簇的筛选精度推进到了数十微秒量级，在海量城市场景中能够稳定过滤掉 95% 以上的不可见几何。

------------------------------------------------------------------------
43.4 软硬件双光栅化混合引擎 (Software vs. Hardware Rasterizer)
------------------------------------------------------------------------

硬件光栅化的临界尺寸反转
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
既然固定管线光栅化硬件执行微多边形会导致严重的四方块过着色算力崩溃，那么能否使用纯通用并行计算（Compute Shader）自行模拟光栅化？

这构成了 Nanite 核心的技术创新之一：**软硬件混合自适应双光栅化引擎（Hybrid Rasterization Engine）**。Nanite 并未彻底抛弃硬件光栅化，而是发现了一个物理性能交叉临界点：

.. list-table:: 硬件固定功能光栅化器 vs Compute Shader 软件光栅化对比
   :widths: 25 35 40
   :header-rows: 1
   :class: tight-table

   * - 性能特征维度
     - 传统硬件光栅化 (Hardware Rasterizer)
     - Compute Shader 软件光栅化 (Software Rasterizer)
   * - **优势区域**
     - **宏观大三角形 ($> 16 \sim 32$ 像素面积)**
     - **微多边形与亚像素多边形 ($\le 16$ 像素面积)**
   * - **吞吐性能模型**
     - 固定硬件光栅化单元吞吐受限于 1~4 Triangles/Clock
     - 通用计算单元（SM/CU）数十万线程并发，受限于显存原子写
   * - **Pixel Quad 惩罚**
     - 产生 $2 	imes 2$ 辅助线程，亚像素下有效率暴跌至 10%
     - **零辅助线程！按实际像素精确评估，有效率 100%**
   * - **同步与合并机制**
     - 硬件 ROP 单元自动排队与颜色混合
     - 依赖 64 位整型原子操作（`InterlockedMax`）更新 Z-Buffer
   * - **网格着色集成**
     - 与 Mesh Shader 硬件管线直接挂钩
     - 纯通用并行着色器，跨平台适配性极佳

当三角形投影在屏幕上的长宽仅为数个像素（面积 $\le 16	ext{ 像素}$）时，固定光栅化管线的图元装配开销、ROP 调度冲突以及辅助线程过着色惩罚使得性能急剧恶化；而在此尺度下，Compute Shader 通过简单的点包含测试，直接以像素为单位写入，其吞吐性能反超硬件光栅化器 **300% 以上**！

软光栅实现微架构：64-bit 原子深写
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Nanite 软件光栅化内核在处理微多边形时，每个线程组处理一个 Cluster。三角形在屏幕投影后，线程计算其 2D 紧凑 AABB 包围盒，针对盒内覆盖的离散像素执行 Juan Pineda 2D 边缘方程（Edge Functions）判定。

在写入深度与图元标记时，传统光栅化依赖硬件 ROP 和 Early-Z。而 Compute Shader 无法直接挂载 ROP，Nanite 采用的解决方案是：**将可见性缓冲区（VisBuffer）格式设定为 64 位无符号整型（`uint64` / `uint2`），利用 GPU 硬件底层的 64-bit 原子极大值指令（`InterlockedMax`）同步完成深度测试与几何标识写入！**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |            Nanite 64-bit VisBuffer 原子操作内存位域编码规范             |
   +-------------------------------------------------------------------------+

    高位 MSB (Bit 63 ~ Bit 32)                低位 LSB (Bit 31 ~ Bit 0)
   +-----------------------------------------+-----------------------------------------+
   | 32-bit Reversed-Z 浮点深度的整型保序映射  | 25-bit Cluster ID  | 7-bit Triangle ID  |
   | (映射至 uint32，深度越近数值严格越大)      | (全局网格簇索引)    | (0~127 局部三角形) |
   +-----------------------------------------+-----------------------------------------+
   |<---------------- 64-bit 单次原子写入 (InterlockedMax) -------------------->|

在 **Reversed-Z 规范** 下，距离相机越近的表面，其深度值越大。将 32 位浮点深度值直接按位解释为等价的 `uint32`，浮点数的大小关系与无符号整型完全等保序！
因此，将 **32 位深度置于高 32 位，将 Cluster ID 与 Triangle ID 置于低 32 位**：

1. 当多个微三角形并发竞争写入同一个像素时，`InterlockedMax` 比较 64 位无符号整数；
2. 高 32 位的深度占据绝对裁决权：只有距离相机更近（深度更大）的三角形，其 64 位整数整体数值才会严格大于当前缓冲存储的值；
3. 一旦高位深度胜出，低 32 位所携带的几何身份标记（Cluster ID + 局部三角形索引）将伴随原子指令**一次性、无条件、零撕裂**地就地覆写更新！

------------------------------------------------------------------------
43.5 可见性缓冲区 (Visibility Buffer) 与延迟材质着色解耦
------------------------------------------------------------------------

G-Buffer 显存带宽危机
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在经典延迟渲染（Deferred Shading，Chapter 41）中，几何阶段必须将材质全量参数写入由多目标渲染（MRT）构成的 G-Buffer 中：
- G-Buffer 0: BaseColor.rgb (24-bit), Roughness (8-bit)
- G-Buffer 1: WorldNormal.xyz (32-bit FP16/Octahedral), Metallic (8-bit)
- G-Buffer 2: WorldPosition / Depth (32-bit)
- G-Buffer 3: Velocity / MotionVectors (32-bit), AO (8-bit)

单像素仅几何写入就需要吞吐 **16 到 32 字节（128 ~ 256 位）**。当全屏充斥数十亿微多边形时光栅化写入带宽将彻底打满显存物理总线，引发毁灭性的访存停顿。

可见性缓冲区 (Visibility Buffer) 范式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Nanite 从底层重构了几何渲染输出，彻底消除了庞大的 G-Buffer：**光栅化阶段（无论软硬光栅）不再输出任何材质属性、UV 贴图、法线或光照参数，全屏输出且仅输出一个 64-bit 的可见性缓冲区（VisBuffer）！**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |          传统 G-Buffer 管线 vs Nanite Visibility Buffer 管线架构对比    |
   +-------------------------------------------------------------------------+

   [ 传统延迟渲染 G-Buffer 流水线 ]
   Geometry Pass ===> [ VS -> PS 采样全套材质 ] ===> 写入巨型 G-Buffer (16~32 Bytes/Pixel)
                                                           |
   Lighting Pass <=========================================+ (解包光照计算)

   [ Nanite Visibility Buffer 流水线 ]
   Geometry Pass ===> [ 仅几何投射，完全不触碰材质! ] ==> 写入极简 VisBuffer (8 Bytes/Pixel)
                                                           |
   Material Shading <======================================+ (屏幕分类，按需拉取顶点重构)

延迟材质解耦与屏幕空间材质分箱 (Material Binning)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当几何阶段光栅化完毕后，屏幕上每个像素确切记录了其所属的全局 Cluster ID 以及 0~127 的局部三角形索引。后续的着色流程演变为极致高效的**延迟材质求值（Deferred Material Evaluation）**：

1. **屏幕空间材质分类 (Material Classification / Binning)**：
   - 调度全屏 Compute Shader 读取 VisBuffer，依据 Cluster ID 查表获取其绑定的 Material ID；
   - 利用原子操作构建每个 Material 的屏幕覆盖像素链表，或直接采用光线追踪式分箱（Tile-Based Material Binning），使相同材质的像素聚集在同一个线程束（Warp）内；
2. **顶点属性即时重构 (On-Demand Attribute Reconstruction)**：
   - 着色器依据 Cluster ID 与 Triangle ID，从全局大缓冲（Mega-IndexBuffer 与 Mega-VertexBuffer）中拉取该三角形的 3 个局部顶点位置与属性；
   - 利用当前像素屏幕坐标与 3 个顶点的屏幕投影坐标，逆向解算该像素对应的**重心坐标 $(\lambda_0, \lambda_1, \lambda_2)$**：

.. math::

   \vec{P} = \lambda_0 \vec{V}_0 + \lambda_1 \vec{V}_1 + \lambda_2 \vec{V}_2, \quad \sum \lambda_i = 1

3. **按需插值与无绑定采样**：
   - 仅对可见像素，通过重心坐标插值求出其精确的 UV、世界法线与切线；
   - 通过 Bindless 架构拉取对应材质的 Albedo/Normal/Roughness 纹理，执行完整的 PBR 光照着色！

**架构优势**：彻底消除了不可见多边形的一切材质纹理采样与着色开销。无论场景实际几何有多厚重、过绘制倍数有多高，全屏每个有效像素**在全生命周期内严格只执行一次材质着色计算（Zero Over-Shading）**！

------------------------------------------------------------------------
43.6 工业级 Nanite 核心着色器微架构实现 (HLSL / Compute Shader)
------------------------------------------------------------------------

以下给出基于 **HLSL (Shader Model 6.6+)** 构建的 Nanite 核心光栅化与剔除内核源码。该代码展示了 Cluster 法线圆锥背面剔除、屏幕投影误差推导、软硬件光栅化分流，以及基于 64 位整型原子操作（`InterlockedMax`）向 VisBuffer 写入几何标识的完整工业级逻辑：

.. code-block:: hlsl

   // =========================================================================
   // File: NaniteCoreRasterizer.hlsl
   // Architecture: Geometry Virtualization Cluster DAG Culling & Software Rasterizer
   // Standard: HLSL SM 6.6+, 64-bit Atomics, Visibility Buffer Pipeline
   // =========================================================================

   #define THREADS_PER_CLUSTER 64
   #define MAX_CLUSTER_VERTS   64
   #define MAX_CLUSTER_TRIS    128

   // -------------------------------------------------------------------------
   // 1. 数据契约定义
   // -------------------------------------------------------------------------
   struct ClusterMetaData {
       float3 sphereCenter;
       float  sphereRadius;
       float3 coneAxis;
       float  coneAngleCos;
       float  lodErrorSelf;
       float  lodErrorParent;
       uint   vertexOffset;
       uint   indexOffset;
       uint   triangleCount;
       uint   materialId;
   };

   struct PackedVertex {
       uint posXY;      // 16位定点数打包 (X: 16位, Y: 16位)
       uint posZ_Normal;// 16位定点数 Z, 16位八面体法线
   };

   // -------------------------------------------------------------------------
   // 2. 全局常数与资源绑定
   // -------------------------------------------------------------------------
   cbuffer ViewUniforms : register(b0) {
       float4x4 g_ViewProjMatrix;
       float3   g_CameraWorldPos;
       float    g_LODScale;          // 屏幕投影缩放系数: (ScreenHeight / (2 * tan(FOV/2)))
       float2   g_ScreenDimensions;
       float    g_ErrorThreshold;    // 目标屏幕像素容忍阈值 (例如 1.0 像素)
   };

   StructuredBuffer<ClusterMetaData> g_Clusters     : register(t0);
   StructuredBuffer<PackedVertex>    g_GlobalVerts  : register(t1);
   ByteAddressBuffer                 g_GlobalIndices: register(t2);

   // 64-bit 连续无符号整型 VisBuffer: 高32位 Depth，低32位 (ClusterID:25 | TriID:7)
   RWTexture2D<uint2> g_RWVisBuffer : register(u0);

   // -------------------------------------------------------------------------
   // 3. 辅助解码与数学计算函数
   // -------------------------------------------------------------------------
   float3 UnpackPosition(PackedVertex v, float3 clusterCenter, float clusterExtent) {
       float x = float(v.posXY & 0xFFFF) / 65535.0f * clusterExtent + clusterCenter.x;
       float y = float(v.posXY >> 16)     / 65535.0f * clusterExtent + clusterCenter.y;
       float z = float(v.posZ_Normal & 0xFFFF) / 65535.0f * clusterExtent + clusterCenter.z;
       return float3(x, y, z);
   }

   // 2D 边缘方程计算: E(P) = (P.x - V0.x)*(V1.y - V0.y) - (P.y - V0.y)*(V1.x - V0.x)
   float EdgeFunction(float2 v0, float2 v1, float2 p) {
       return (p.x - v0.x) * (v1.y - v0.y) - (p.y - v0.y) * (v1.x - v0.x);
   }

   // -------------------------------------------------------------------------
   // 4. Cluster 剔除与自适应软光栅核函数
   // -------------------------------------------------------------------------
   [numthreads(THREADS_PER_CLUSTER, 1, 1)]
   void CS_NaniteClusterRasterize(
       uint3 dispatchThreadId : SV_DispatchThreadID,
       uint  groupIndex       : SV_GroupIndex,
       uint3 groupId          : SV_GroupID
   ) {
       uint clusterId = groupId.x;
       ClusterMetaData meta = g_Clusters[clusterId];

       // 共享内存缓存解包后的屏幕空间几何
       groupshared float4 s_ScreenPos[MAX_CLUSTER_VERTS];
       groupshared bool   s_ClusterVisible;

       // 步骤 1: 单线程主导执行 Cluster 粗粒度视锥、背面与 LOD 裁决
       if (groupIndex == 0) {
           s_ClusterVisible = true;

           // 1.1 屏幕投影误差判定 (DAG Error Metric)
           float distToCam = distance(meta.sphereCenter, g_CameraWorldPos);
           float projectedErrorSelf   = (meta.lodErrorSelf / max(distToCam, 0.001f)) * g_LODScale;
           float projectedErrorParent = (meta.lodErrorParent / max(distToCam, 0.001f)) * g_LODScale;

           // 若当前层级误差过大（且非叶子）或父级误差已满足精度，则当前簇不是合法切割面成员
           if (projectedErrorSelf > g_ErrorThreshold || projectedErrorParent <= g_ErrorThreshold) {
               s_ClusterVisible = false;
           }

           // 1.2 包围法线圆锥背面剔除 (Normal Cone Culling)
           if (s_ClusterVisible) {
               float3 toCenter = normalize(meta.sphereCenter - g_CameraWorldPos);
               if (dot(meta.coneAxis, toCenter) > sqrt(1.0f - meta.coneAngleCos * meta.coneAngleCos)) {
                   s_ClusterVisible = false; // 簇内所有三角形整齐背向相机
               }
           }
       }
       GroupMemoryBarrierWithGroupSync();

       if (!s_ClusterVisible) return;

       // 步骤 2: 协作读取并投影顶点至屏幕坐标系
       for (uint vIdx = groupIndex; vIdx < MAX_CLUSTER_VERTS; vIdx += THREADS_PER_CLUSTER) {
           PackedVertex rawV = g_GlobalVerts[meta.vertexOffset + vIdx];
           float3 worldPos = UnpackPosition(rawV, meta.sphereCenter, meta.sphereRadius);
           
           float4 clipPos = mul(g_ViewProjMatrix, float4(worldPos, 1.0f));
           float3 ndc = clipPos.xyz / max(clipPos.w, 0.00001f);
           
           // 映射到屏幕物理像素坐标
           float2 screenPixel = (ndc.xy * float2(0.5f, -0.5f) + 0.5f) * g_ScreenDimensions;
           s_ScreenPos[vIdx] = float4(screenPixel, ndc.z, clipPos.w); // 保留 Reversed-Z
       }
       GroupMemoryBarrierWithGroupSync();

       // 步骤 3: 协作执行微多边形软件光栅化 (Software Rasterizer)
       // 每个线程独立处理一个三角形，循环直至覆盖 128 个三角形
       for (uint triIdx = groupIndex; triIdx < meta.triangleCount; triIdx += THREADS_PER_CLUSTER) {
           // 从 8-bit 微索引缓冲区读取三角形局部索引
           uint byteOffset = (meta.indexOffset + triIdx * 3);
           uint raw3Bytes = g_GlobalIndices.Load(byteOffset & ~3);
           uint shift = (byteOffset & 3) * 8;
           uint i0 = (raw3Bytes >> shift) & 0xFF;
           uint i1 = (g_GlobalIndices.Load((byteOffset + 1) & ~3) >> (((byteOffset + 1) & 3) * 8)) & 0xFF;
           uint i2 = (g_GlobalIndices.Load((byteOffset + 2) & ~3) >> (((byteOffset + 2) & 3) * 8)) & 0xFF;

           float4 p0 = s_ScreenPos[i0];
           float4 p1 = s_ScreenPos[i1];
           float4 p2 = s_ScreenPos[i2];

           // 背面剔除与微面积裁决 (以 2D 行列式交叉面积为基准)
           float det = (p1.x - p0.x) * (p2.y - p0.y) - (p1.y - p0.y) * (p2.x - p0.x);
           if (det <= 0.0f) continue; // 逆时针为正面，顺时针剔除

           // 计算三角形在屏幕空间的 2D AABB 像素边界
           float2 minPixel = floor(min(min(p0.xy, p1.xy), p2.xy));
           float2 maxPixel = ceil(max(max(p0.xy, p1.xy), p2.xy));

           // 裁剪至当前视口有效区域
           minPixel = max(minPixel, float2(0.0f, 0.0f));
           maxPixel = min(maxPixel, g_ScreenDimensions - 1.0f);

           // 仅针对微小三角形执行软光栅（面积过大时在生产管线中转交 Hardware Rasterizer）
           float area = det * 0.5f;
           if (area > 32.0f) {
               // 实际管线中回退写入硬件分发列表，此处示例紧凑软光栅核心
           }

           // 扫描 AABB 内的所有候选像素执行点包含测试
           for (int y = (int)minPixel.y; y <= (int)maxPixel.y; ++y) {
               for (int x = (int)minPixel.x; x <= (int)maxPixel.x; ++x) {
                   float2 pixelCenter = float2(x, y) + 0.5f;

                   // 评估 2D 边缘方程
                   float w0 = EdgeFunction(p1.xy, p2.xy, pixelCenter);
                   float w1 = EdgeFunction(p2.xy, p0.xy, pixelCenter);
                   float w2 = EdgeFunction(p0.xy, p1.xy, pixelCenter);

                   // Top-Left 填充约定或全正判定
                   if (w0 >= 0.0f && w1 >= 0.0f && w2 >= 0.0f) {
                       // 归一化重心坐标
                       float invDet = 1.0f / det;
                       float lambda0 = w0 * invDet;
                       float lambda1 = w1 * invDet;
                       float lambda2 = w2 * invDet;

                       // 透视校正深度插值 (Reversed-Z: 深度越大越靠前)
                       float interpolatedDepth = lambda0 * p0.z + lambda1 * p1.z + lambda2 * p2.z;
                       uint depthUint = asuint(interpolatedDepth);

                       // 构造 64-bit 紧凑编码: 高32位 Depth, 低32位 (ClusterID << 7 | TriID)
                       uint payload = ((clusterId & 0x01FFFFFF) << 7) | (triIdx & 0x7F);
                       uint64_t newFragment = (uint64_t(depthUint) << 32) | uint64_t(payload);

                       // 64-bit 硬件原子极大值覆写更新 VisBuffer
                       // 深度更大（更近）的片元瞬间以原子方式独占像素
                       InterlockedMax(g_RWVisBuffer[int2(x, y)], newFragment);
                   }
               }
           }
       }
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从传统图形微架构在遭遇微多边形时的硬件失效切入，系统推导了以 **UE5 Nanite** 为代表的几何虚拟化架构革命：
1. **微多边形硬件危机本质**：剖析了传统光栅化以 $2 	imes 2$ Pixel Quad 计算偏导数导致的辅助线程（Helper Invocations）算力空耗，量化了亚像素下有效着色率跌破 10% 的微架构物理根源；
2. **Cluster DAG 数据结构**：解构了固定 128 三角形簇、局部量化坐标与分层有向无环图的构建规则，证明了利用成组锁定外部边界彻底消除跨层几何裂缝的数学完备性；
3. **GPU-Driven 极速粗细粒度剪枝**：阐释了利用法线包围圆锥（Normal Cone）在单周期剔除整簇三角形，以及两阶段 Hi-Z 遮挡测试在数万网格簇下的微秒级收敛；
4. **软硬件双光栅化引擎**：解析了微多边形在 Compute Shader 下纯点包含判定反超硬件光栅化的临界翻转，推导了基于 64-bit 无符号整型原子操作（`InterlockedMax`）实现深度与图元标记原子一致性写入的微架构设计；
5. **可见性缓冲区 (Visibility Buffer)**：揭示了将几何光栅化（仅输出 8 字节 VisBuffer）与材质着色（屏幕材质分箱 + 重心坐标按需重构顶点）完全解耦的巨大带宽红利，达成了全场景零过着色（Zero Over-Shading）的终极工业目标。

当几何虚拟化将几何细节推进到“无限多边形”的物理极限后，图形系统面临的下一个终极挑战便聚焦于光：**如何在拥有数十亿动态微多边形、且完全不依赖离线烘焙光照贴图的宏大世界中，实现全动态、实时更新、无限次弹射的反弹光照？**
在下一章（**Chapter 44: 动态全局光照与无限反弹：UE5 Lumen 表面缓存 (Surface Cache) 与屏幕/硬件追踪融合**）中，我们将深入解析 Lumen 全局光照体系，解构 Mesh Signed Distance Fields (SDF)、物理表面缓存流送以及屏幕空间光线追踪与 DXR/Vulkan 硬件光追的多级混合架构。
