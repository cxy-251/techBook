========================================================================
Chapter 24: 全局可见性剔除：视锥体裁剪、遮挡查询与分层 Z 剔除 (Hi-Z)
========================================================================

.. note:: 前置背景与认知承接
   在前面的章节中，我们深入剖析了 GPU 硬件的 SIMT 并行微架构、光栅化流水线、材质光照模型以及高保真软阴影过滤算法。然而，在工业级开放世界游戏、超大规模 CAD 协同装配与高保真元宇宙场景中，场景往往包含数以万计的动态网格体、上千万个多边形以及多层重叠的建筑与植被。如果将场景中的全部图元无差别地提交至渲染管线，系统将瞬间遭遇严重的性能危机：CPU 端由于大量 DrawCall 导致驱动提交线程过载；GPU 端前端顶点着色器（VS）与图元装配器（IA）因海量不可见多边形发生管线拥塞；后端光栅化与像素着色器（PS）更会由于严重的**透视过度绘制（Overdraw）**陷入显存带宽与算力瓶颈。

   **“不渲染看不见的东西”是实时图形学最核心的第一性原理。** 可见性剔除（Visibility Culling）是在几何数据进入深层着色管线之前，将其以最低计算代价快速拦截的系统级工程防御体系。本章将从视锥体裁剪的几何代数本质出发，系统解构包围体（Bounding Volumes）求交数学、硬件遮挡查询（Hardware Occlusion Queries）与跨总线延迟解耦、GPU 硬件与 Compute Shader 分层 Z 缓冲（Hi-Z）剔除算法，以及现代 GPU-Driven 渲染管线中的两阶段遮挡剔除架构，并交付工业级 HLSL 计算着色器实现。

------------------------------------------------------------------------
24.1 可见性剔除体系在现代渲染管线中的架构定位
------------------------------------------------------------------------

可见性剔除并非单一算法，而是一个贯穿 CPU、GPU 驱动、Compute Shader 与硬件固定管线的四级多尺度过滤金字塔：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  现代图形渲染管线四级可见性剔除过滤金字塔               |
   +-------------------------------------------------------------------------+

   [ 场景全量多边形: 10,000,000+ Triangles / 20,000+ Mesh Instances ]
                               |
                               v
   +-------------------------------------------------------------------------+
   | 级别 1: 粗粒度空间场景划分 / 潜在可见集 (PVS / Portal / Octree)         |
   | * 运行位置: CPU 端 / 离线预计算                                         |
   | * 过滤对象: 建筑房间、远景区块 (Cells & Portals)                        |
   | * 剔除比例: 拦截 40% ~ 60% 物理绝对无关区域                             |
   +-------------------------------------------------------------------------+
                               |
                               v
   +-------------------------------------------------------------------------+
   | 级别 2: 视锥体几何裁剪 (View Frustum Culling - VFC)                     |
   | * 运行位置: CPU SIMD (AVX2/NEON) 或 GPU Compute (GPU-Driven)            |
   | * 过滤对象: AABB / 包围球 (Bounding Box / Sphere)                        |
   | * 剔除比例: 拦截视场角 (FOV) 之外的 50% ~ 70% 对象                      |
   +-------------------------------------------------------------------------+
                               |
                               v
   +-------------------------------------------------------------------------+
   | 级别 3: 细粒度遮挡剔除 (Occlusion Culling / Hi-Z / Software Rasterizer)  |
   | * 运行位置: GPU Compute Shader (Hi-Z) 或 CPU SIMD 软件光栅化            |
   | * 过滤对象: 被山体、大楼、近景物体完全遮挡的网格体 (Instances/Meshlets) |
   | * 剔除比例: 拦截视野内被遮蔽的 60% ~ 90% 几何体                         |
   +-------------------------------------------------------------------------+
                               |
                               v [仅剩 1% ~ 5% 真正可见图元进入硬件光栅化]
   +-------------------------------------------------------------------------+
   | 级别 4: 硬件光栅化级裁剪 (Hardware Backface / Early-Z / Z-Cull)         |
   | * 运行位置: GPU 固定功能硬件 (Primitive Setup / ROP)                     |
   | * 过滤对象: 背面多边形、像素 Quad 粒度微观深度遮挡                      |
   | * 剔除比例: 彻底终结像素级 Overdraw, 保障着色负载接近 1.0               |
   +-------------------------------------------------------------------------+

.. list-table:: 现代主流可见性剔除技术特性全景对比
   :widths: 15 15 20 25 25
   :header-rows: 1
   :class: tight-table

   * - 剔除技术
     - 执行位置
     - 计算复杂度
     - 内存与带宽开销
     - 适用场景与工程优劣
   * - **视锥体裁剪 (VFC)**
     - CPU / GPU Compute
     - $O(N)$ (包围盒相交)
     - 极低（仅需 6 个平面方程）
     - 全场景必须启用；无法剔除视野内重叠遮挡
   * - **门室系统 (Portals/PVS)**
     - CPU (基于预计算)
     - $O(1) \sim O(K)$
     - 需离线烘焙 PVS 拓扑数据
     - 室内、地牢等结构化场景极致高效；不适用动态破坏与开放世界
   * - **硬件遮挡查询 (HOQ)**
     - GPU 渲染管线
     - 取决于包围盒绘制量
     - 需回读计数器，引发 CPU-GPU 停顿
     - 传统 API 方案；存在 1~2 帧延迟或严重的管线气泡（Bubble）
   * - **CPU 软件光栅化剔除**
     - CPU 多线程 + SIMD
     - $O(M)$ (低分辨率光栅化)
     - 占用 CPU 缓存与线程时间
     - 移动端与主机常用（如 Frostbite/UE）；免除 GPU 额外负载
   * - **GPU Hi-Z 遮挡剔除**
     - GPU Compute Shader
     - $O(N)$ (GPU 并行测试)
     - 需构建深度 Mipmap 金字塔 (Hi-Z)
     - 现代 GPU-Driven 渲染标配；吞吐极大，完美适配 Indirect Draw

------------------------------------------------------------------------
24.2 视锥体几何与包围体求交测试数学推导
------------------------------------------------------------------------

视锥体裁剪（View Frustum Culling）的核心是在三维空间中构建描述视见体边界的 6 个齐次半空间平面（左、右、底、顶、近、远），并与场景中物体的空间包围体进行快速分离轴或有向距离测试。

从 View-Projection 矩阵直接提取 6 个裁剪平面的代数推导 (Gribb-Hartmann 算法)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

设齐次裁剪空间坐标 $\mathbf{p}_c = (x_c, y_c, z_c, w_c)^T$，其由世界空间坐标 $\mathbf{p}_w = (x_w, y_w, z_w, 1)^T$ 乘以视图投影矩阵 $\mathbf{M} = \mathbf{M}_{	ext{view}} \cdot \mathbf{M}_{	ext{proj}}$ 得到：

.. math::

   \mathbf{p}_c = \mathbf{M} \cdot \mathbf{p}_w = 
   \begin{pmatrix}
   \mathbf{m}_1 \cdot \mathbf{p}_w \
   \mathbf{m}_2 \cdot \mathbf{p}_w \
   \mathbf{m}_3 \cdot \mathbf{p}_w \
   \mathbf{m}_4 \cdot \mathbf{p}_w
   \end{pmatrix}

其中 $\mathbf{m}_i$ 表示矩阵 $\mathbf{M}$ 的第 $i$ 行行向量。

在标准化设备坐标（NDC）中（以 DirectX / Vulkan $x, y \in [-1, 1], z \in [0, 1]$ 规范为例），几何点位于视锥体内部的充要代数条件为：

.. math::

   -w_c \le x_c \le w_c, \quad -w_c \le y_c \le w_c, \quad 0 \le z_c \le w_c

将 $\mathbf{p}_c$ 的分量展开为矩阵行向量的点积：

1. **左裁剪平面 (Left Plane)**：$x_c \ge -w_c \implies \mathbf{m}_1 \cdot \mathbf{p}_w \ge -\mathbf{m}_4 \cdot \mathbf{p}_w \implies (\mathbf{m}_4 + \mathbf{m}_1) \cdot \mathbf{p}_w \ge 0$；
2. **右裁剪平面 (Right Plane)**：$x_c \le w_c \implies (\mathbf{m}_4 - \mathbf{m}_1) \cdot \mathbf{p}_w \ge 0$；
3. **下裁剪平面 (Bottom Plane)**：$y_c \ge -w_c \implies (\mathbf{m}_4 + \mathbf{m}_2) \cdot \mathbf{p}_w \ge 0$；
4. **上裁剪平面 (Top Plane)**：$y_c \le w_c \implies (\mathbf{m}_4 - \mathbf{m}_2) \cdot \mathbf{p}_w \ge 0$；
5. **近裁剪平面 (Near Plane)**：$z_c \ge 0 \implies \mathbf{m}_3 \cdot \mathbf{p}_w \ge 0$；
6. **远裁剪平面 (Far Plane)**：$z_c \le w_c \implies (\mathbf{m}_4 - \mathbf{m}_3) \cdot \mathbf{p}_w \ge 0$。

每个平面可统一定义为代数形式 $\pi_k = (A_k, B_k, C_k, D_k)^T$。为了使代数方程表示真实的欧几里得物理距离，必须对平面法向量进行归一化：

.. math::

   \hat{\pi}_k = \frac{\pi_k}{\sqrt{A_k^2 + B_k^2 + C_k^2}} = (\mathbf{n}_k, d_k)

此时，空间中任意点 $\mathbf{x}$ 到平面 $\hat{\pi}_k$ 的有向欧氏距离严格为：$	ext{Dist}(\mathbf{x}) = \mathbf{n}_k \cdot \mathbf{x} + d_k$。若 $	ext{Dist}(\mathbf{x}) < 0$，则点 $\mathbf{x}$ 严格位于该平面的外侧。

空间包围盒 (AABB) 与视锥体平面的相交判定优化 (P-Vertex / N-Vertex 算法)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于轴对齐包围盒 $	ext{AABB} = [\mathbf{x}_{\min}, \mathbf{x}_{\max}]$，如果逐一测试其 8 个顶点与 6 个平面的关系，需执行 $8 	imes 6 = 48$ 次点积运算。

工业级优化利用 AABB 的轴对齐单调性，对每个平面法向量 $\mathbf{n} = (n_x, n_y, n_z)$ 直接确定**最外侧正顶点（$P$-Vertex）**与**最内侧负顶点（$N$-Vertex）**：

.. math::

   P_x = (n_x > 0) \,?\, x_{\max} : x_{\min}, \quad N_x = (n_x > 0) \,?\, x_{\min} : x_{\max}

.. math::

   P_y = (n_y > 0) \,?\, y_{\max} : y_{\min}, \quad N_y = (n_y > 0) \,?\, y_{\min} : y_{\max}

.. math::

   P_z = (n_z > 0) \,?\, z_{\max} : z_{\min}, \quad N_z = (n_z > 0) \,?\, z_{\min} : z_{\max}

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                AABB 针对平面的 P-Vertex 与 N-Vertex 几何定义            |
   +-------------------------------------------------------------------------+

                 法向量 n ↗
                         \
       (x_min, y_max) ----+-------------- (x_max, y_max) [P-Vertex: 沿 n 方向极远点]
                     |                  |
                     |       AABB       |
                     |                  |
   [N-Vertex] -------+------------------- (x_max, y_min)
   (x_min, y_min)

**判定准则**：
1. 若 $\mathbf{n} \cdot \mathbf{P} + d < 0$：整盒完全位于该平面外侧，**立即断定剔除（Culled Outside）**；
2. 若 $\mathbf{n} \cdot \mathbf{N} + d \ge 0$：整盒完全位于该平面内侧；
3. 否则：包围盒跨越该裁剪平面（Intersecting）。

通过该优化，判定一个 AABB 仅需执行 6 次点积，计算量骤降 87.5%。

------------------------------------------------------------------------
24.3 硬件遮挡查询 (Hardware Occlusion Queries) 与管线停顿解耦
------------------------------------------------------------------------

视锥体裁剪仅能剔除视野外的几何体。在城市街道或森林场景中，大量处于视锥体内部的建筑物和道具会被近景的巨型建筑完全遮挡。硬件遮挡查询（HOQ）允许应用程序利用 GPU 深度测试电路评估复杂物体的可见性。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  传统硬件遮挡查询的时序停顿危机 (Pipeline Stall)         |
   +-------------------------------------------------------------------------+

   CPU 线程: [提交 Occluders] -> [提交 Bounding Box Query] -> [回读结果 (等待 GPU)] !!! 停顿 1.5~2ms
                                                                    |
                                        +---------------------------+ (PCIe 同步阻塞)
                                        v
   GPU 渲染:                     [光栅化 Occluders] -> [光栅化 BBox] -> [写出通过采样数]

硬件工作机制与 API 流程
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\

1. 应用程序先正常渲染场景中的主要遮挡物（如地形、大楼墙体），写入深度缓冲区；
2. 禁用颜色写入与深度写入（仅保留深度测试），包裹目标物体的粗糙包围盒（AABB 几何网格）并发起遮挡查询（如 `D3D12_QUERY_TYPE_OCCLUSION`）；
3. GPU 光栅化该包围盒，硬件计数器统计通过 Depth Test 的像素点数量（Passed Samples）；
4. 若 $	ext{PassedSamples} > 0$，表明包围盒部分或全部暴露在遮挡物之外，CPU 随后提交该物体的完整高精度网格渲染指令；若计数为 0，则直接跳过该物体。

CPU-GPU 跨总线同步停顿解耦的三大工程策略
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **跨帧延迟查询（Temporal Coherence Query）**：
   CPU 从不在当前帧同步等待查询结果，而是读取**上一帧（Frame $N-1$）**的遮挡查询数据来决定当前帧（Frame $N$）是否提交渲染。基于时间连续性，相机与物体的运动在 16.6ms 间隔内变化极小。对于在上一帧不可见但在当前帧突然移出遮挡区的物体，可设置保守的重检测间隔（如每 5 帧强制激活一次渲染测试）。
2. **条件渲染（Conditional Rendering / Predication）**：
   现代 API（`vkCmdBeginConditionalRenderingEXT` 或 `ID3D12GraphicsCommandList::SetPredication`）支持将查询结果缓冲区直接绑定为 GPU 绘制的前提条件。GPU 前端命令处理器（Command Streamer）直接在设备端根据显存中的计数器决定是否丢弃后续的 DrawCall，**完全消除了回读 CPU 的 PCIe 总线开销与停顿**。

------------------------------------------------------------------------
24.4 分层 Z 缓冲 (Hierarchical-Z / Hi-Z) 与 Compute Shader 剔除
------------------------------------------------------------------------

虽然条件渲染消除了总线回读，但为数万个物体分别绘制 AABB 依然会产生巨额的硬件光栅化与命令分发开销。现代工业界普遍采用 **GPU Compute Shader 驱动的分层 Z 缓冲（Hi-Z）剔除算法**。

Hi-Z 深度金字塔构建微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Hi-Z 本质上是由场景不透明几何体深度图构建的**单通道保守深度金字塔（Depth Mipmap Chain）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Hi-Z 保守深度金字塔生成规则 (基于 Reverse-Z 规范)        |
   +-------------------------------------------------------------------------+

   Mip 0 (1920x1080 原始深度)       Mip 1 (960x540)             Mip 2 (480x270)
   +-----+-----+-----+-----+         +-----------+-----------+   +-------------------+
   | 0.8 | 0.9 | 0.2 | 0.3 |         |           |           |   |                   |
   +-----+-----+-----+-----+  --->   |   0.95    |   0.30    |-> |       0.95        |
   | 0.7 | 0.95| 0.1 | 0.25|         |           |           |   |                   |
   +-----+-----+-----+-----+         +-----------+-----------+   +-------------------+
   |   4 像素分块 (2x2)    |         | 4 像素分块 (2x2) 取极值   |   | 全局最保守覆盖深度|
   +-----------------------+         +-----------------------+   +-------------------+

**核心保守性准则**：
- 在传统的近大远小深度模式（Near=0, Far=1）下，上一级 Mip 必须取子区域 4 个像素的**最大值（Max Depth）**，代表该区域内最远表面的深度；
- 在现代标准的 **反转 Z（Reverse-Z，Near=1, Far=0）** 规范下，上一级 Mip 必须取子区域 4 个像素的**最小值（Min Depth）**，代表该区域内最远离相机的保守遮挡深度！

Hi-Z 遮挡测试四步闭环推导
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

给定任意物体的空间 AABB：

1. **投影屏幕包围矩形**：将 AABB 的 8 个顶点变换至齐次裁剪空间，执行透视除法得到 8 个 NDC 坐标，取其外接轴对齐包围矩形 $[u_{\min}, u_{\max}] 	imes [v_{\min}, v_{\max}]$；
2. **计算物体最近深度**：找出 8 个顶点中离相机最近的深度值 $d_{	ext{nearest}}$（在 Reverse-Z 下即为最大 Z 值 $\max(z_0 \dots z_7)$）；
3. **自适应选取 Mip 级别**：根据屏幕包围矩形的长宽尺寸 $(\Delta u \cdot W, \Delta v \cdot H)$，选取一个能使包围盒在对应 Mip 层级上投影尺寸**不超过 $2 	imes 2$ 纹素**的最精细 Mip 级别：

.. math::

   	ext{mipLevel} = 	ext{ceil}\left( \log_2\left( \max(	ext{rectWidth}, 	ext{rectHeight}) \right) \right)

4. **保守深度采样与判定**：在选定的 Mip 级别上，采样覆盖包围矩形的 $2 	imes 2$（共 4 个）Hi-Z 深度值，取其最保守遮挡深度 $D_{	ext{occluder}}$。
   
   在 Reverse-Z 规范下：
   
   - 若 $d_{	ext{nearest}} < D_{	ext{occluder}}$：物体的最近点比最远遮挡物还要靠后，**判定完全被遮挡（Culled）**；
   - 否则：物体潜在可见，保留渲染！

------------------------------------------------------------------------
24.5 GPU-Driven 渲染管线中的两阶段遮挡剔除架构
------------------------------------------------------------------------

为了实现 100% 运行在 GPU 上的全自动可见性剔除，现代工业级引擎（如 UE5、Frostbite）采用了基于 Compute Shader 与间接绘制（Indirect Draw）的**两阶段遮挡剔除流水线（Two-Pass GPU Occlusion Culling）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                现代 GPU-Driven 两阶段遮挡剔除完整运行流水线              |
   +-------------------------------------------------------------------------+

   [ 阶段 1: 基于上一帧 Hi-Z 的可见性初筛 ]
   1. 读取上一帧历史深度构建的 Hi-Z 金字塔;
   2. Compute Shader 遍历全场景 N 万个物体包围盒:
      - 视锥体剔除 (VFC);
      - 基于历史 Hi-Z 执行遮挡测试;
   3. 将通过初筛的可见物体写入 IndirectDrawBuffer_Pass1;
   4. 将未通过初筛的潜在遮挡物体写入 PotentiallyOccludedList;
        |
        v
   [ 阶段 2: 渲染已知可见网格体 (Early Occluders Pass) ]
   1. 调用 vkCmdDrawIndexedIndirect 绘制 Pass 1 中的所有物体;
   2. 写入当帧 Early-Z 深度缓冲 (构建最强遮挡物骨架);
        |
        v
   [ 阶段 3: 当帧实时 Hi-Z 金字塔极速重构 ]
   1. 利用 Compute Shader 对当前深度缓冲区做下采样, 生成当帧最新 Hi-Z Mipmap;
        |
        v
   [ 阶段 4: 二次精确补漏筛选 (Late Occlusion Pass) ]
   1. Compute Shader 遍历 PotentiallyOccludedList 中的物体;
   2. 基于当帧最新的 Hi-Z 进行二次遮挡测试;
   3. 将因场景物体运动/镜头旋转而暴露的新可见物体写入 IndirectDrawBuffer_Pass2;
        |
        v
   [ 阶段 5: 补漏网格体渲染 (Late Mesh Draw Pass) ]
   1. 调用 vkCmdDrawIndexedIndirect 绘制 Pass 2 中被修正为可见的新增物体;
   * 结果: 零漏检、零闪烁、全自动化、完全解放 CPU 算力!

------------------------------------------------------------------------
24.6 工业级 HLSL Hi-Z 遮挡剔除 Compute Shader 完整实现
------------------------------------------------------------------------

以下是符合现代 DirectX 12 / Vulkan 标准的工业级 GPU-Driven 视锥体与 Hi-Z 遮挡剔除 HLSL 计算着色器，内置 AABB 投影、Reverse-Z 适配与间接命令缓冲区原子写入：

.. code-block:: hlsl

   // HLSL: GPU-Driven 视锥体裁剪与 Hi-Z 遮挡剔除 Compute Shader
   // 特性: Reverse-Z 规范 + AABB 投影 + 自适应 Mip 采样 + 间接参数无锁追加

   struct ObjectData {
       float4x4 WorldMatrix;
       float3   AABBMin;
       float    Padding0;
       float3   AABBMax;
       float    Padding1;
       uint     IndexCount;
       uint     StartIndexLocation;
       int      BaseVertexLocation;
       uint     InstanceIndex;
   };

   struct DrawIndexedIndirectCommand {
       uint IndexCountPerInstance;
       uint InstanceCount;
       uint StartIndexLocation;
       int  BaseVertexLocation;
       uint StartInstanceLocation;
   };

   // 资源绑定
   StructuredBuffer<ObjectData>              g_AllObjects            : register(t0);
   Texture2D<float>                          g_HiZPyramid            : register(t1);
   SamplerState                              g_PointClampSampler     : register(s0);

   RWStructuredBuffer<DrawIndexedIndirectCommand> g_VisibleCommands  : register(u0);
   RWStructuredBuffer<uint>                  g_VisibleCountBuffer    : register(u1);

   cbuffer CullingConstants : register(b0) {
       float4x4 g_ViewProj;
       float4   g_FrustumPlanes[6]; // 归一化的 6 个裁剪平面 (Ax + By + Cz + D >= 0 为内)
       float2   g_RTSize;           // 渲染目标分辨率 (Width, Height)
       float2   g_HiZSize;          // Hi-Z 顶层 Mip0 分辨率
       uint     g_TotalObjectCount;
       uint     g_HiZMaxMipLevel;
   };

   // 视锥体 AABB 裁剪测试
   bool IsAABBInFrustum(float3 boxMin, float3 boxMax) {
       for (int i = 0; i < 6; ++i) {
           float4 plane = g_FrustumPlanes[i];
           // 确定 P-Vertex
           float3 pVertex = float3(
               (plane.x > 0.0f) ? boxMax.x : boxMin.x,
               (plane.y > 0.0f) ? boxMax.y : boxMin.y,
               (plane.z > 0.0f) ? boxMax.z : boxMin.z
           );

           if (dot(plane.xyz, pVertex) + plane.w < 0.0f) {
               return false; // 完全在外侧
           }
       }
       return true;
   }

   // 计算 AABB 8 顶点在屏幕空间的投影包围矩形与最近深度 (Reverse-Z)
   bool ProjectAABB(float3 boxMin, float3 boxMax, out float4 screenRect, out float maxDepth) {
       float3 corners[8] = {
           float3(boxMin.x, boxMin.y, boxMin.z),
           float3(boxMax.x, boxMin.y, boxMin.z),
           float3(boxMin.x, boxMax.y, boxMin.z),
           float3(boxMax.x, boxMax.y, boxMin.z),
           float3(boxMin.x, boxMin.y, boxMax.z),
           float3(boxMax.x, boxMin.y, boxMax.z),
           float3(boxMin.x, boxMax.y, boxMax.z),
           float3(boxMax.x, boxMax.y, boxMax.z)
       };

       float2 minUV = float2(1.0f, 1.0f);
       float2 maxUV = float2(0.0f, 0.0f);
       maxDepth = 0.0f; // 在 Reverse-Z 下，越大越靠近相机 (Near=1.0)

       bool isNearClipped = false;

       for (int i = 0; i < 8; ++i) {
           float4 clipPos = mul(g_ViewProj, float4(corners[i], 1.0f));

           // 若顶点跨越近平面背后
           if (clipPos.w <= 0.0f) {
               isNearClipped = true;
               continue;
           }

           float3 ndc = clipPos.xyz / clipPos.w;
           float2 uv = float2(ndc.x * 0.5f + 0.5f, -ndc.y * 0.5f + 0.5f);

           minUV = min(minUV, uv);
           maxUV = max(maxUV, uv);

           // Reverse-Z 模式：最近点具有最大 NDC-Z
           maxDepth = max(maxDepth, ndc.z);
       }

       // 若包围盒跨越近裁剪面，直接判定为可见，规避投影畸变
       if (isNearClipped) {
           screenRect = float4(0.0f, 0.0f, 1.0f, 1.0f);
           maxDepth = 1.0f;
           return true;
       }

       screenRect = float4(saturate(minUV), saturate(maxUV));
       return true;
   }

   // 主剔除 Compute Kernel
   [numthreads(64, 1, 1)]
   void CS_VisibilityCulling(uint3 dispatchThreadId : SV_DispatchThreadID) {
       uint objectIndex = dispatchThreadId.x;
       if (objectIndex >= g_TotalObjectCount) {
           return;
       }

       ObjectData obj = g_AllObjects[objectIndex];

       // 1. 变换 AABB 到世界空间
       float3 worldMin = obj.AABBMin;
       float3 worldMax = obj.AABBMax;

       // 2. 第一道防线: 视锥体裁剪 (VFC)
       if (!IsAABBInFrustum(worldMin, worldMax)) {
           return;
       }

       // 3. 计算屏幕投影矩形与最近深度
       float4 screenRect;
       float  nearestDepth;
       ProjectAABB(worldMin, worldMax, screenRect, nearestDepth);

       // 4. 第二道防线: Hi-Z 遮挡测试
       float2 rectSize = (screenRect.zw - screenRect.xy) * g_HiZSize;
       float  maxDimension = max(rectSize.x, rectSize.y);
       
       // 计算覆盖 <= 2x2 纹素的 Mip Level
       float mipLevel = clamp(ceil(log2(max(maxDimension, 1.0f))), 0.0f, (float)g_HiZMaxMipLevel);

       // 采样 4 样本取最保守深度 (Reverse-Z: 最小值代表最远遮挡物)
       float2 uvMin = screenRect.xy;
       float2 uvMax = screenRect.zw;

       float d0 = g_HiZPyramid.SampleLevel(g_PointClampSampler, float2(uvMin.x, uvMin.y), mipLevel).r;
       float d1 = g_HiZPyramid.SampleLevel(g_PointClampSampler, float2(uvMax.x, uvMin.y), mipLevel).r;
       float d2 = g_HiZPyramid.SampleLevel(g_PointClampSampler, float2(uvMin.x, uvMax.y), mipLevel).r;
       float d3 = g_HiZPyramid.SampleLevel(g_PointClampSampler, float2(uvMax.x, uvMax.y), mipLevel).r;

       float minOccluderDepth = min(min(d0, d1), min(d2, d3));

       // Reverse-Z 判定: 若物体最近深度 < 遮挡物深度，则被完全遮蔽
       if (nearestDepth < minOccluderDepth) {
           return; // 遮挡剔除成功
       }

       // 5. 物体完全可见: 原子追加至 DrawIndexedIndirectBuffer
       uint visibleIndex;
       InterlockedAdd(g_VisibleCountBuffer[0], 1, visibleIndex);

       DrawIndexedIndirectCommand cmd;
       cmd.IndexCountPerInstance   = obj.IndexCount;
       cmd.InstanceCount           = 1;
       cmd.StartIndexLocation      = obj.StartIndexLocation;
       cmd.BaseVertexLocation      = obj.BaseVertexLocation;
       cmd.StartInstanceLocation   = obj.InstanceIndex;

       g_VisibleCommands[visibleIndex] = cmd;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从渲染管线前端过载与 Overdraw 瓶颈出发，系统构建了涵盖视锥体几何裁剪、硬件遮挡查询与分层 Z 缓冲（Hi-Z）的多尺度可见性过滤金字塔；严格推导了 Gribb-Hartmann 裁剪平面提取与 AABB $P/N$-Vertex 极速相交判定；剖析了硬件遮挡查询的跨总线停顿缺陷与条件渲染优化；并深入解构了 Compute Shader 驱动的 Hi-Z 深度金字塔下采样与现代 GPU-Driven 两阶段遮挡剔除闭环架构。

然而，当场景进一步扩展到包含数十万个离散物体、动态刚体碰撞以及硬件光线追踪（Hardware Ray Tracing）求交时，单纯依靠视锥体与屏幕空间 Hi-Z 无法高效组织场景的三维空间拓扑关系。下一章我们将深入现代图形引擎与光线追踪的核心骨干——**空间加速层次结构：BVH 动态重构、SAH 启发式表面积分割与 GPU 遍历栈优化**，解构光线与空间几何体如何在对数时间复杂度内实现纳秒级求交定位。
