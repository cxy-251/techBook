========================================================================
Chapter 29: 硬件光线追踪核心架构：RT Core BVH 求交、D3D12 DXR 与 Vulkan RT 编程管线
========================================================================

.. note:: 前置背景与认知承接
   在上一章（Chapter 28）中，我们系统剖析了基于三维欧氏空间连续辐射场的探针网格（SH / DDGI）与体素锥形追踪（VXGI）全局光照方案。尽管体素与探针能够以有限的计算开销模拟宏观多重反弹漫反射，但受制于空间离散化分辨率（Grid/Voxel Resolution），它们在处理复杂动态几何体的高频接触阴影、高曲率镜面反射（Glossy/Specular Reflection）以及精确几何遮挡时，始终面临漏光、几何失真与显存膨胀的物理妥协。

   要实现无精度妥协的真实光照物理模拟，图形渲染必须回归到光线投射（Ray Casting）的基本微积分定义。然而，纯软件 SIMT 着色器遍历空间加速结构（BVH）存在严重的执行发散与指令吞吐瓶颈。现代 GPU 引入了硬件加速光线追踪（Hardware Ray Tracing）微架构。本章将深入剖析 **RT Core 专用硬件求交流水线、两级加速结构（TLAS / BLAS）构建与紧凑化、D3D12 DXR 与 Vulkan RT 可编程管线状态机、着色器绑定表（Shader Binding Table - SBT）内存寻址拓扑，以及光线查询（Ray Query）内联求交机制**，并交付工业级 HLSL 光线追踪阴影与反射着色器实现。

------------------------------------------------------------------------
29.1 硬件加速光线追踪微架构与 RT Core 物理求交引擎
------------------------------------------------------------------------

在传统 GPU 架构中，光线与场景求交完全依赖通用流式多处理器（SM / Compute Unit）运行通用着色器代码。这种软件模拟光线追踪在微架构层面面临致命的物理制约：

1. **SIMT 分支发散危机**：同一个 Warp 内的 32 条光线在遍历层次包围盒（BVH）时，由于起点和方向各异，会频繁走向不同的 BVH 子树分支，导致 Active Mask 严重稀疏化，ALU 有效利用率跌落至 10% 以下；
2. **寄存器堆（VGPR）与局部内存溢出**：BVH 树的深度遍历必须维护一个遍历栈（Traversal Stack）。在缺乏片上专用硬件栈支持时，每个线程必须在通用寄存器或高延迟本地内存（Local Memory / DRAM Spill）中分配栈空间，直接引发 SM 占用率（Occupancy）断崖；
3. **指令吞吐挤占**：Ray-AABB（轴对齐包围盒）浮点相交测试与 Ray-Triangle 莫勒-特伦博尔（Möller-Trumbore）重心坐标求交算法需要消耗大量 FP32 算力，挤占了原本用于材质着色与后期计算的通用 ALU 吞吐。

专用硬件求交核心 (RT Core / Ray Accelerator) 微架构
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

现代 GPU 硬件（如 NVIDIA Turing/Ampere/Ada Lovelace 架构的 RT Core、AMD RDNA 2/3 的 Ray Accelerator、Intel Xe-HPG 的 Ray Tracing Unit）在每个 SM / CU 内部集成了专用的固定功能光线追踪硬件加速电路。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                GPU SM 内部 RT Core 硬件异步遍历流水线拓扑               |
   +-------------------------------------------------------------------------+

             通用着色器核心 (SM / Warp Execution)
             [ TraceRay() / RayQuery.Proceed() 指令发射 ]
                               |
                               | (异步移交光线描述符 Ray Desc)
                               v
   +-------------------------------------------------------+
   |  RT Core 专用硬件加速器 (Dedicated Hardware ASIC)     |
   |                                                       |
   |   +---------------------+   +---------------------+   |
   |   |   BVH 遍历单元      |   |  三角形求交单元     |   |
   |   | (BVH Traversal Box) |<->| (Ray-Triangle Unit) |   |
   |   +---------------------+   +---------------------+   |
   |              |                         |              |
   |              v                         v              |
   |     [ 硬件专用短栈存储 ]      [ 莫勒-特伦博尔求交电路 ] |
   |     [ (Short Stack Regs) ]    [ (Barycentric Calc)  ] |
   +-------------------------------------------------------+
                               |
                               | (求交完成: 返回最近命中点 / 遮挡状态)
                               v
             通用着色器核心 (SM / Warp Execution)
             [ 恢复 Warp 调度, 执行 Closest Hit / Any Hit ]

RT Core 的微架构工作流包含三大核心硬件单元：

1. **BVH 包围盒求交单元（Box Traversal Unit）**：
   专用硬件管线以单周期吞吐执行光线与 AABB 包围盒（Ray-AABB）的 6 平面相交测试：

   .. math::

      t_{\min} = \max\left( \min(t_{x1}, t_{x2}), \min(t_{y1}, t_{y2}), \min(t_{z1}, t_{z2}) \right)

   .. math::

      t_{\max} = \min\left( \max(t_{x1}, t_{x2}), \max(t_{y1}, t_{y2}), \max(t_{z1}, t_{z2}) \right)

   若 $t_{\min} \le t_{\max}$ 且 $t_{\max} > 0$，则判定光线穿透包围盒。硬件单元自动将相交子节点压入内部硬件短栈，并在遇到叶子节点前完全由硬件自主推进，无需 SM 介入。

2. **三角形求交单元（Ray-Triangle Intersection Unit）**：
   当遍历抵达 BVH 叶子节点时，专用硬件电路单周期加载三角形顶点坐标 $\mathbf{V}_0, \mathbf{V}_1, \mathbf{V}_2$，执行硬件莫勒-特伦博尔求交，解算重心坐标 $(u, v)$ 与光线距离 $t$：

   .. math::

      \begin{bmatrix} t \ u \ v \end{bmatrix} = \frac{1}{\mathbf{P} \cdot \mathbf{E}_1} \begin{bmatrix} \mathbf{Q} \cdot \mathbf{E}_2 \ \mathbf{P} \cdot \mathbf{T} \ \mathbf{Q} \cdot \mathbf{D} \end{bmatrix}

   其中 $\mathbf{E}_1 = \mathbf{V}_1 - \mathbf{V}_0, \mathbf{E}_2 = \mathbf{V}_2 - \mathbf{V}_0, \mathbf{T} = \mathbf{O} - \mathbf{V}_0, \mathbf{P} = \mathbf{D} 	imes \mathbf{E}_2, \mathbf{Q} = \mathbf{T} 	imes \mathbf{E}_1$。

3. **异步卸载与重排序引擎（Shader Execution Reordering - SER）**：
   最新硬件（如 NVIDIA Ada 架构）引入了 SER 机制。当成百上千条遍历中的光线命中不同材质时，SER 硬件调度器在执行命中着色器之前，自动在片上将发散的光线按着色器类型与内存空间局部性进行动态聚类（Re-clustering），将离散的 SIMT 分支发散重新整合成高度一致的 Warp，大幅降低指令 Cache Miss 与显存发散访存开销。

.. list-table:: 纯软件 SIMT 光追 vs RT Core 专用硬件光追微架构对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 维度指标
     - 软件 SIMT 光追 (Compute Shader Ray Marching)
     - 硬件 RT Core 光追 (DXR / Vulkan RT)
   * - **求交指令执行**
     - 消耗大量通用 FP32 ALU 与分支跳转指令
     - **专用固定功能硬件电路，零 ALU 占用**
   * - **遍历栈内存分配**
     - 占用通用寄存器（VGPR）或本地显存 Spill
     - 片上专用高速硬件短栈寄存器（Short Stack）
   * - **分支发散影响**
     - Warp 内线程执行路径分化，吞吐严重退化
     - 硬件自主异步遍历，结合 SER 动态重排序
   * - **求交性能基准**
     - 约 500 万 ~ 1500 万 Rays/s
     - **百亿级 Rays/s（10+ GigaRays/s）**

------------------------------------------------------------------------
29.2 两级加速结构 (Two-Level Acceleration Structure - TLAS / BLAS)
------------------------------------------------------------------------

为了使硬件 RT Core 能够高效遍历包含数百万三角形的宏大动态场景，图形 API（DirectX 12 DXR 与 Vulkan KHR）强制规定了标准化的 **两级加速结构（Two-Level Acceleration Structure）**。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                 两级加速结构 (TLAS 与 BLAS) 拓扑引用模型                |
   +-------------------------------------------------------------------------+

      [ 顶层加速结构: TLAS (Top-Level Acceleration Structure) ]
      (以世界空间为基准, 维护场景所有实例的 3x4 变换矩阵与材质索引)
                    /                               \
                   /                                 \
          [ Instance 0 (角色) ]             [ Instance 1 (建筑) ]
          Transform: M_0                    Transform: M_1
          InstanceMask: 0xFF                InstanceMask: 0x01
          BLAS Pointer: &BLAS_A             BLAS Pointer: &BLAS_B
                   |                                 |
                   v                                 v
      [ 底层加速结构: BLAS_A ]          [ 底层加速结构: BLAS_B ]
      (局部模型空间几何 BVH)             (局部模型空间几何 BVH)
        +-- AABB Node --+                 +-- AABB Node --+
        |               |                 |               |
     Leaf (Tri 0..2)  Leaf (Tri 3..5)   Leaf (Tri 0..8)  Leaf (Tri 9..15)

底层加速结构 (BLAS - Bottom-Level Acceleration Structure)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **几何定义域**：BLAS 在局部模型空间（Object Space）构建，封装实际的物理几何体。一个 BLAS 可以包含多个几何子网格（Geometries），支持两类几何描述：
  1. **三角形几何体（Triangles）**：由顶点缓冲区（Vertex Buffer）、索引缓冲区（Index Buffer）与变换矩阵偏移构成；
  2. **程序化 AABB 图元（Procedural AABBs）**：由自定义边界框构成的非三角形几何（如毛发曲线、SDF 体素）。
- **静态复用性**：BLAS 可以被场景中成百上千个实例（Instances）共享引用（如场景中摆放的 1000 棵相同树木，只需构建 1 个 BLAS）。

顶层加速结构 (TLAS - Top-Level Acceleration Structure)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **场景实例域**：TLAS 在世界坐标系（World Space）下构建，其叶子节点包含一系列 `VkAccelerationStructureInstanceKHR` / `D3D12_RAYTRACING_INSTANCE_DESC` 描述符结构体：

.. code-block:: cpp

   struct RaytracingInstanceDesc {
       float                     Transform[3][4];          // 3x4 仿射变换矩阵 (模型 -> 世界)
       uint32_t                  InstanceID : 24;          // 自定义 24 位实例 ID (着色器可读: InstanceID())
       uint32_t                  InstanceMask : 8;         // 8 位可见性掩码 (配合 TraceRay RayMask 过滤)
       uint32_t                  InstanceContributionToHitGroupIndex : 24; // SBT 命中组基底偏移
       uint32_t                  Flags : 8;                // 实例标志 (如禁用背面剔除、强制不透明)
       uint64_t                  AccelerationStructureReference; // 指向目标 BLAS 的 64 位 GPU 虚拟地址 (GPUVA)
   };

- **动态构建开销**：TLAS 必须每帧在 GPU 侧重建（Rebuild）或更新（Update/Refit），以反映动态物体的移动、旋转、骨骼变换与可见性剔除。

加速结构构建、紧凑化与内存开销模型
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

加速结构的构建完全在 GPU 侧异步完成（通过 `vkCmdBuildAccelerationStructuresKHR` 或 `BuildRaytracingAccelerationStructure`）。构建过程受以下物理与内存机制约束：

1. **Scratch 临时缓冲区**：
   驱动在执行 BVH 空间分割（如 SAH - Surface Area Heuristic 表面积启发式算法）时，需要分配临时的 GPU Scratch 显存用于排序和构建中间树节点。
2. **紧凑化压缩（Acceleration Structure Compaction）**：
   初次构建时，驱动必须按最坏情况预估分配保守的显存尺寸。构建完成后，GPU 发送查询命令获取实际所需的紧凑内存大小（通常仅为预估值的 40%~60%），随后调用紧凑化拷贝（Compaction Copy），释放未使用的显存碎片。
3. **重建 (Rebuild) vs 更新 (Refit)**：
   - **Rebuild**：重新计算 SAH 并完全重构 BVH 树拓扑。耗时较高，但生成的 BVH 质量高、包围盒重叠小，光线遍历效率极高；
   - **Refit（更新）**：保持现有的 BVH 树节点拓扑不变，仅根据变动后的顶点坐标自底向上更新父包围盒 AABB。耗时极低（常用于骨骼蒙皮网格），但若网格发生大尺度形变，包围盒重叠加剧会导致光线遍历性能急剧劣化。

.. list-table:: 加速结构构建参数与更新策略选型矩阵
   :widths: 20 25 30 25
   :header-rows: 1
   :class: tight-table

   * - 资产类型
     - 推荐构建标志 (Build Flags)
     - 每帧更新策略 (Per-Frame Strategy)
     - 内存管理建议
   * - **静态场景建筑 / 地形**
     - `PREFER_FAST_TRACE | ALLOW_COMPACTION`
     - 场景加载时一次性 Rebuild
     - 强制执行 Compaction 压缩显存
   * - **动态刚体 / 载具**
     - `PREFER_FAST_TRACE` (BLAS 静态)
     - **仅每帧 Rebuild TLAS**，BLAS 保持完全静态
     - 仅更新 TLAS 实例 Transform
   * - **骨骼蒙皮动态角色**
     - `ALLOW_UPDATE | PREFER_FAST_BUILD`
     - 每帧在 Compute Shader 蒙皮后执行 **BLAS Refit**
     - 当包围盒退化严重时定期触发 Rebuild

------------------------------------------------------------------------
29.3 光线追踪着色器管线 (Ray Tracing Pipeline & Shaders)
------------------------------------------------------------------------

与传统光栅化管线（VS $	o$ Rasterizer $	o$ PS）线性的固定流程不同，光线追踪管线是一个基于 **事件驱动与动态递归分发** 的异步状态机。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |            DirectX Raytracing (DXR) / Vulkan RT 管线执行状态机          |
   +-------------------------------------------------------------------------+

              [ Ray Generation Shader (rgen) ]
              (主入口: 计算屏幕射线, 调用 TraceRay)
                             |
                             v
              +------------------------------+
              |   RT Core 硬件加速遍历       | <--------------------+
              | (TLAS -> Instance -> BLAS)   |                      |
              +------------------------------+                      |
                 /                        \                         |
     [ 遍历中发现潜在候选相交 ]     [ 射线未命中任何几何体 ]        |
               /                            \                       |
              v                              v                      |
   +--------------------+         +--------------------+            |
   | Intersection (rint)|         | Miss Shader (rmiss)|            |
   | (自定义 AABB 图元) |         | (采样天空盒/环境光)|            |
   +--------------------+         +--------------------+            |
              |                              |                      |
              v                              |                      |
   +--------------------+                    |                      |
   | Any Hit (rahit)    |                    |                      |
   | (透明度 Alpha 判定)|                    |                      |
   +--------------------+                    |                      |
              |                              |                      |
     [ 确认相交: 压入最近命中 ]              |                      |
              |                              |                      |
              v                              |                      |
   +--------------------+                    |                      |
   | Closest Hit (rchit)| -------------------+ (可能递归调用) ------+
   | (PBR 材质/次级反射)|
   +--------------------+
              |
              v
     [ 写回最终结果至 UAV ]

五大可编程着色器阶段职责剖析
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **光线生成着色器 (Ray Generation Shader - `rgen`)**：
   - **执行起点**：由 `DispatchRays` / `vkCmdTraceRaysKHR` 启动的二维网格（如屏幕分辨率 $1920 	imes 1080$）并行触发；
   - **核心职责**：根据当前像素索引计算反投影视锥光线，初始化光线载荷（Ray Payload），并调用 `TraceRay()` 发起求交遍历，最终将光照结果写入全局 UAV 纹理（Output Texture）。

2. **交点着色器 (Intersection Shader - `rint`)**：
   - **执行时机**：当光线命中程序化 AABB 包围盒（Procedural Geometry）时由硬件自动触发；
   - **核心职责**：计算自定义解析几何体（如数学解析球体、SDF 隐式曲面、NURBS 曲线）的交点，调用 `ReportHit()` 提交命中参数 $(t, 	ext{Attributes})$。三角形几何体跳过此阶段，直接由硬件求交电路处理。

3. **任意命中着色器 (Any Hit Shader - `rahit`)**：
   - **执行时机**：光线在遍历过程中每发现一个潜在候选三角形交点时立即触发；
   - **核心职责**：主要用于 **透明度镂空剔除（Alpha-Tested / Stipple Foliage）**。采样纹理判断 Alpha 值，若透明则调用 `IgnoreHit()` 放弃该交点，命令硬件继续向前遍历；若不透明则接受命中。
   - *性能警示*：Any Hit 会打断硬件 RT Core 的纯硬件连续求交流水线，频繁触发 SM 上下文切换，应尽量配合不透明标志（`RAY_FLAG_FORCE_OPAQUE`）关闭。

4. **最近命中着色器 (Closest Hit Shader - `rchit`)**：
   - **执行时机**：当整条光线沿着当前路径完成全局遍历后，对测得距离最近的有效几何交点触发 **唯一一次** 调用；
   - **核心职责**：提取顶点插值属性与材质参数，执行复杂 PBR 光照着色，并可根据需要发射次级光线（Secondary Rays，如阴影射线、镜面反射射线）。

5. **未命中着色器 (Miss Shader - `rmiss`)**：
   - **执行时机**：当光线在设定的最大距离 $T_{\max}$ 内未碰撞到任何场景图元时触发；
   - **核心职责**：采样天空盒、HDR 环境贴图或直接返回常数背景色，将环境辐射亮度写入 Ray Payload。

------------------------------------------------------------------------
29.4 着色器绑定表 (Shader Binding Table - SBT) 内存拓扑与索引计算公式
------------------------------------------------------------------------

在光线追踪管线中，不同几何网格可能绑定完全不同的材质着色器（如金属反射、玻璃透射、漫反射泥土）。**着色器绑定表（Shader Binding Table - SBT）是驱动与着色器硬件在无 CPU 参与下动态将命中图元精准路由至对应着色器记录与本地资源描述符的内存路由拓扑。**

SBT 内存物理布局 (SBT Memory Layout)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

SBT 是一段由应用程序在 GPU 显存中开辟并填充的线性缓冲区，严格按以下 4 个连续区域组织：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |             着色器绑定表 (Shader Binding Table - SBT) 内存对齐拓扑       |
   +-------------------------------------------------------------------------+

   [ RayGen Section ] (对齐至 64/128 字节)
   +-------------------------------------------------------------------------+
   | [Shader ID (32B)] | [Local Root Arguments / Descriptors (CBV/SRV/UAV)]  |
   +-------------------------------------------------------------------------+

   [ Miss Section ] (每个 Record 步长对齐至 HandleSizeAligned)
   +-------------------------------------------------------------------------+
   | Record 0 (Primary Miss): [Shader ID (32B)] | [Skybox Texture Handle]    |
   | Record 1 (Shadow Miss) : [Shader ID (32B)] | [Constant 1.0 (No Occ)]    |
   +-------------------------------------------------------------------------+

   [ HitGroup Section ] (包含 ClosestHit + AnyHit + Intersection)
   +-------------------------------------------------------------------------+
   | Record 0 (Mesh 0 - PBR Metal) : [Shader ID (32B)] | [Material Buf GPUVA]|
   | Record 1 (Mesh 0 - Shadow Ray): [Shader ID (32B)] | [Empty / Null]      |
   | Record 2 (Mesh 1 - Alpha Leaf): [Shader ID (32B)] | [Texture SRV Handle]|
   | Record 3 (Mesh 1 - Shadow Ray): [Shader ID (32B)] | [Alpha Mask Handle] |
   +-------------------------------------------------------------------------+

   [ Callable Section ]
   +-------------------------------------------------------------------------+
   | Record 0 .. N: [Shader ID (32B)] | [Function Local Arguments]           |
   +-------------------------------------------------------------------------+

单个 Shader Record 的二进制组成：
- **Shader Identifier（着色器标识符）**：固定 32 字节（由驱动 API 获取的唯一硬件程序指针散列值）；
- **Local Root Arguments / Root Descriptors**：内联追加在 Shader ID 后方的数据（如常量缓冲、材质结构体 GPU 虚拟地址、Bindless 资源索引）。

Hit Group 索引定位数学公式
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当光线在场景中命中某个图元时，GPU 硬件通过以下严格的代数公式计算出该命中点在 SBT HitGroup 表中的目标 Shader Record 字节偏移地址：

.. math::

   	ext{RecordIndex} = 	ext{RayBaseOffset} + \left( 	ext{GeometryIndex} 	imes 	ext{RayGeometryStride} \right) + 	ext{InstanceOffset}

其中各参数的定义与事实源如下：
- **`RayBaseOffset`（光线类型基底偏移）**：在着色器调用 `TraceRay()` 时传入的 `RayContributionToHitGroupIndex` 参数（例如：主相机射线为 0，阴影射线为 1）；
- **`RayGeometryStride`（光线类型乘数因子）**：在 `TraceRay()` 中传入的 `MultiplierForGeometryContributionToHitGroupIndex` 参数（等于场景支持的光线类型总数，例如 2 种光线则步长为 2）；
- **`GeometryIndex`（几何体索引）**：当前命中三角形所在 BLAS 内部的几何子网格索引编号（$0, 1, 2, \dots$ 由底层 BLAS 装配顺序决定）；
- **`InstanceOffset`（实例贡献偏移）**：定义在 TLAS 实例描述符中的 `InstanceContributionToHitGroupIndex` 字段。

最终目标 Shader Record 的显存物理地址为：

.. math::

   	ext{GPUVA}_{	ext{target}} = 	ext{SBT}_{	ext{HitGroupBaseGPUVA}} + \left( 	ext{RecordIndex} 	imes 	ext{HitGroupRecordStride} \right)

.. list-table:: SBT 索引计算实例：包含普通着色与阴影双光线系统的场景拓扑
   :widths: 15 20 20 20 25
   :header-rows: 1
   :class: tight-table

   * - 场景图元
     - InstanceOffset
     - GeometryIndex
     - 光线类型 (Ray Type)
     - 最终 SBT RecordIndex 计算
   * - **建筑主体**
     - 0
     - 0
     - 辐射着色 (Ray 0)
     - $0 + (0 	imes 2) + 0 = \mathbf{0}$
   * - **建筑主体**
     - 0
     - 0
     - 阴影射线 (Ray 1)
     - $1 + (0 	imes 2) + 0 = \mathbf{1}$
   * - **树木树叶**
     - 2
     - 0 (树干)
     - 辐射着色 (Ray 0)
     - $0 + (0 	imes 2) + 2 = \mathbf{2}$
   * - **树木树叶**
     - 2
     - 1 (透明树叶)
     - 辐射着色 (Ray 0)
     - $0 + (1 	imes 2) + 2 = \mathbf{4}$
   * - **树木树叶**
     - 2
     - 1 (透明树叶)
     - 阴影射线 (Ray 1)
     - $1 + (1 	imes 2) + 2 = \mathbf{5}$

------------------------------------------------------------------------
29.5 光线查询 (Ray Query / Inline RT) vs 光线追踪管线 (RTP)
------------------------------------------------------------------------

现代图形 API 提供了两种截然不同的硬件光线追踪集成范式：

1. **光线追踪管线 (Ray Tracing Pipeline - RTP)**：
   基于 `DispatchRays` 与完整 SBT 体系，支持动态着色器分发与深层递归追踪；
2. **光线查询 (Ray Query / Inline Ray Tracing - DXR 1.1 / Vulkan KHR)**：
   允许在 **任意现有着色器阶段（Compute Shader, Pixel Shader, Vertex/Mesh Shader）** 内部直接声明 `RayQuery` 局部对象，内联调用硬件 RT Core 执行遍历，以确定性的代码逻辑在当前着色器内处理命中结果。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |          Ray Tracing Pipeline (RTP) vs Ray Query (Inline RT) 架构对比   |
   +-------------------------------------------------------------------------+

      [ 范式 A: Ray Tracing Pipeline (RTP) ]
      +-----------------------------------------------------------------------+
      |  RayGen Shader  -->  [ 动态硬件调度器 / SBT 解析 ]                    |
      |                            |                                          |
      |             +--------------+--------------+                           |
      |             v                             v                           |
      |     ClosestHit Shader A           ClosestHit Shader B                 |
      |  (复杂材质着色/动态发射光线)    (不同材质着色/动态发射光线)           |
      +-----------------------------------------------------------------------+
      特性: 极致灵活, 支持异构材质动态路由, 但存在调度开销与寄存器占用上限。

      [ 范式 B: Ray Query (Inline RT) ]
      +-----------------------------------------------------------------------+
      |  标准 Compute Shader / Pixel Shader                                   |
      |  {                                                                    |
      |      RayQuery<RAY_FLAG_ACCEPT_FIRST_HIT_AND_END_SEARCH> q;           |
      |      q.TraceRayInline(TLAS, ...);                                     |
      |      while(q.Proceed()) { /* 硬件 RT Core 在循环内求交 */ }          |
      |      if (q.CommittedStatus() == HIT) { /* 直接在当前函数体内处理 */ }  |
      |  }                                                                    |
      +-----------------------------------------------------------------------+
      特性: 零 SBT 依赖, 零着色器切换开销, 完全受控的局部寄存器分配。

.. list-table:: Ray Tracing Pipeline (RTP) 与 Ray Query (Inline RT) 核心维度对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 评估维度
     - 光线追踪管线 (Ray Tracing Pipeline)
     - 光线查询 (Ray Query / Inline RT)
   * - **运行环境**
     - 独立的专用 RT 状态机与着色器集合
     - **嵌入任意标准 Shader（Compute/Pixel/Mesh）**
   * - **SBT 依赖**
     - 强依赖复杂的 Shader Binding Table 配置
     - **完全无需 SBT**，资源直接由当前 Shader 绑定
   * - **着色器动态性**
     - 极高：命中不同几何体自动执行不同 Hit Shader
     - 固定：所有命中图元均在当前代码逻辑中统一处理
   * - **寄存器与调度开销**
     - 较高（必须按所有可能 Hit Shader 的最大寄存器预留）
     - **极低（完全遵循普通 Compute Shader 编译优化）**
   * - **工业最佳应用场景**
     - 复杂路径追踪（Path Tracing）、多材质反射/折射
     - **硬件光追硬阴影、环境光遮蔽（RTAO）、可见性剔除**

------------------------------------------------------------------------
29.6 工业级 DXR / HLSL 硬件光追阴影与反射着色器完整实现
------------------------------------------------------------------------

以下是符合 DirectX 12 / DXR 1.1 与 Vulkan 规范的工业级光线追踪硬阴影与光线查询 Compute Shader HLSL 完整实现：

Ray Query 内联硬件光追阴影 Compute Shader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: hlsl

   // HLSL 6.5+: 基于 RayQuery (Inline RT) 的高吞吐硬件光追阴影生成
   // 特性: 零 SBT 依赖, 硬件级遍历, 早期命中即终止, 零着色器发散

   struct SceneConstants {
       float4x4 InvViewProj;
       float4   LightDirection; // xyz: 趋向光源的方向向量, w: 最大光线距离
       float2   RenderTargetSize;
       float    NormalBias;
       float    Padding;
   };

   ConstantBuffer<SceneConstants>                g_SceneCB  : register(b0);
   RaytracingAccelerationStructure               g_SceneTLAS: register(t0);
   Texture2D<float>                              g_DepthTex : register(t1);
   Texture2D<float4>                             g_NormalTex: register(t2);
   RWTexture2D<float>                            g_ShadowOut: register(u0);

   [numthreads(8, 8, 1)]
   void CS_RayQueryShadow(uint3 dispatchThreadID : SV_DispatchThreadID) {
       uint2 pixelCoord = dispatchThreadID.xy;
       if (any(pixelCoord >= uint2(g_SceneCB.RenderTargetSize))) {
           return;
       }

       // 1. 读取 G-Buffer 深度与法线
       float depth = g_DepthTex[pixelCoord];
       if (depth >= 1.0f) {
           // 天空盒区域无阴影
           g_ShadowOut[pixelCoord] = 1.0f;
           return;
       }

       // 2. 重建世界坐标
       float2 uv = (float2(pixelCoord) + 0.5f) / g_SceneCB.RenderTargetSize;
       float2 ndcXY = uv * 2.0f - 1.0f;
       ndcXY.y = -ndcXY.y; // 翻转 Y 轴匹配 D3D 规则

       float4 clipPos = float4(ndcXY, depth, 1.0f);
       float4 worldPosH = mul(g_SceneCB.InvViewProj, clipPos);
       float3 worldPos = worldPosH.xyz / worldPosH.w;

       // 读取世界法线并归一化
       float3 worldNormal = normalize(g_NormalTex[pixelCoord].xyz * 2.0f - 1.0f);

       // 3. 构建光线描述符并应用法线偏移 (Normal Bias) 彻底消除自相交粉刺 (Acne)
       RayDesc ray;
       ray.Origin = worldPos + worldNormal * g_SceneCB.NormalBias;
       ray.Direction = normalize(g_SceneCB.LightDirection.xyz);
       ray.TMin = 0.001f;
       ray.TMax = g_SceneCB.LightDirection.w;

       // 4. 初始化硬件光线查询对象
       // 标志位: 强制不透明 (忽略 AnyHit) + 首次相交即终止 (Accept First Hit) + 跳过多边形背面
       RayQuery<RAY_FLAG_FORCE_OPAQUE | 
                RAY_FLAG_ACCEPT_FIRST_HIT_AND_END_SEARCH | 
                RAY_FLAG_SKIP_CLOSEST_HIT_SHADER> q;

       q.TraceRayInline(
           g_SceneTLAS,
           RAY_FLAG_NONE,
           0xFF, // 遍历所有可见性实例 (Instance Mask)
           ray
       );

       // 5. 驱动 RT Core 硬件遍历循环
       while (q.Proceed()) {
           // 对于复杂 Alpha 剔除网格, 可在此处手动内联解算透明度
       }

       // 6. 获取最终遍历提交状态 (CommittedStatus)
       float visibility = 1.0f;
       if (q.CommittedStatus() == COMMITTED_TRIANGLE_HIT || 
           q.CommittedStatus() == COMMITTED_PROCEDURAL_PRIMITIVE_HIT) {
           // 射线与场景几何体发生阻挡 -> 处于阴影中
           visibility = 0.0f;
       }

       g_ShadowOut[pixelCoord] = visibility;
   }

Ray Tracing Pipeline (RTP) 镜面反射 RayGen 与 ClosestHit 实现
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: hlsl

   // HLSL 6.3+: DXR 光线追踪管线反射着色器
   // 特性: 动态材质求交路由 + 递归光线载荷 (Ray Payload)

   struct RayPayload {
       float3 Radiance;      // 返回的辐射亮度
       float  HitDistance;   // 命中距离 (用于降噪模糊权重)
   };

   RaytracingAccelerationStructure g_SceneTLAS : register(t0, space0);
   RWTexture2D<float4>             g_OutputTex : register(u0, space0);
   Texture2D<float4>               g_GBufferNormRough : register(t1, space0);
   Texture2D<float>                g_GBufferDepth     : register(t2, space0);

   // -------------------------------------------------------------------------
   // Ray Generation Shader
   // -------------------------------------------------------------------------
   [shader("raygeneration")]
   void RayGen_Reflections() {
       uint2 pixelCoord = DispatchRaysIndex().xy;
       float depth = g_GBufferDepth[pixelCoord];
       if (depth >= 1.0f) {
           g_OutputTex[pixelCoord] = float4(0, 0, 0, 0);
           return;
       }

       float4 normRough = g_GBufferNormRough[pixelCoord];
       float3 worldNormal = normalize(normRough.xyz);
       float  roughness = normRough.w;

       // 对于过于粗糙的表面直接跳过硬件光追 (回退至探针 GI)
       if (roughness > 0.6f) {
           g_OutputTex[pixelCoord] = float4(0, 0, 0, 0);
           return;
       }

       // 计算视线方向与理想镜面反射方向
       float3 worldPos = ReconstructWorldPosition(pixelCoord, depth);
       float3 viewDir = normalize(worldPos - g_CameraWorldPos);
       float3 reflectDir = reflect(viewDir, worldNormal);

       RayDesc ray;
       ray.Origin = worldPos + worldNormal * 0.01f;
       ray.Direction = reflectDir;
       ray.TMin = 0.01f;
       ray.TMax = 1000.0f;

       RayPayload payload;
       payload.Radiance = float3(0, 0, 0);
       payload.HitDistance = -1.0f;

       // 发射光线并触发 DXR 管线状态机
       TraceRay(
           g_SceneTLAS,
           RAY_FLAG_CULL_BACK_FACING_TRIANGLES,
           0xFF,
           0, // RayContributionToHitGroupIndex (反射光线对应 HitGroup 0)
           1, // MultiplierForGeometryContributionToHitGroupIndex
           0, // MissShaderIndex (对应 Miss 0: 天空盒)
           ray,
           payload
       );

       g_OutputTex[pixelCoord] = float4(payload.Radiance, payload.HitDistance);
   }

   // -------------------------------------------------------------------------
   // Closest Hit Shader
   // -------------------------------------------------------------------------
   struct MaterialData {
       float4 BaseColor;
       float4 MaterialParams; // x: Metallic, y: Roughness
   };
   ConstantBuffer<MaterialData> g_LocalMaterial : register(b0, space1); // Local Root Signature

   [shader("closesthit")]
   void ClosestHit_PBR(inout RayPayload payload, in BuiltInTriangleIntersectionAttributes attribs) {
       float3 barycentrics = float3(1.0 - attribs.barycentrics.x - attribs.barycentrics.y, 
                                    attribs.barycentrics.x, 
                                    attribs.barycentrics.y);

       float hitT = RayTCurrent();
       payload.HitDistance = hitT;

       // 读取 Local Root Arguments 传递的该材质专有参数
       float3 albedo = g_LocalMaterial.BaseColor.rgb;
       float  metallic = g_LocalMaterial.MaterialParams.x;

       // 简化的直接光照评估
       float3 hitPos = WorldRayOrigin() + WorldRayDirection() * hitT;
       float3 directLight = EvaluateDirectLighting(hitPos, albedo, metallic);

       payload.Radiance = directLight;
   }

   // -------------------------------------------------------------------------
   // Miss Shader
   // -------------------------------------------------------------------------
   TextureCube<float4> g_SkyboxTex : register(t3, space0);
   SamplerState        g_SkySampler: register(s0, space0);

   [shader("miss")]
   void Miss_Skybox(inout RayPayload payload) {
       float3 envColor = g_SkyboxTex.SampleLevel(g_SkySampler, WorldRayDirection(), 0).rgb;
       payload.Radiance = envColor;
       payload.HitDistance = 1e5f;
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章系统解构了现代 GPU 硬件加速光线追踪的底层体系与工业级 API 编程管线：
1. **硬件求交微架构**：剖析了通用 SM 软件光追在 SIMT 分支发散与遍历栈显存溢出上的物理瓶颈，深入解构了 RT Core 专用硬件 Box Traversal 单元、Ray-Triangle 求交电路与 SER 动态重排序微架构；
2. **两级加速结构 (TLAS/BLAS)**：推导了局部模型空间 BLAS 与世界实例空间 TLAS 的拓扑关系，解析了 Scratch 临时内存、Compaction 紧凑化压缩与 Rebuild/Refit 动态更新策略；
3. **光追管线状态机**：系统解构了 RayGen、Intersection、AnyHit、ClosestHit、Miss 五大着色器阶段的职责边界与触发时机；
4. **着色器绑定表 (SBT)**：推导了 SBT 的连续内存物理对齐布局与命中索引定位数学公式，明确了 Local Root Arguments 的参数传递机制；
5. **编程范式选型**：深度对比了光线追踪管线（RTP）与光线查询（Ray Query / Inline RT）在架构、开销与场景上的本质区别；
6. **工业级落地**：交付了基于 Ray Query 的超高性能硬件硬阴影 Compute Shader 与基于 DXR 管线的镜面反射 HLSL 完整源码。

至此，**第六模块第四章（Chapter 29）完工落盘（全书已完成 29/45 节）**。

在下一章中，我们将进入现代物理渲染的终极数学基石——**蒙特卡洛积分与实时路径追踪 (Path Tracing & ReSTIR)**。我们将系统推导 **渲染方程的无偏蒙特卡洛估计、重要性采样（Importance Sampling）、多重重要性采样（MIS）、时空储层重要性重采样（ReSTIR DI / GI）算法与实时光追降噪（Denoising）架构**，敬请期待！
