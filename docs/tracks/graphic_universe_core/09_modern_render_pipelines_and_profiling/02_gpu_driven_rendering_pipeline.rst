========================================================================
Chapter 42: GPU-Driven 渲染管线深度演进：间接绘制 (Indirect Draw)、Hi-Z 剔除与两阶段遮挡
========================================================================

.. note:: 前置背景与认知承接
   在 Chapter 41 中，我们深入解构了现代渲染管线从传统前向（Forward）、经典延迟着色（Deferred Shading），演进至分块前向（Forward+）与分簇光照着色（Clustered Shading）的微架构全景。通过在三维对数空间中建立紧凑连续的光照索引网格（Cluster Grid），现代渲染管线成功将光照解算的空间复杂度与几何物体的多边形数量彻底解耦，使场景能够无压力承载数以万计的局部动态光源。

   然而，在光照计算瓶颈被攻克之后，图形系统遭遇了更为底层的物理天花板：**传统的 CPU-Driven 绘制提交模式**。在包含数十万甚至数百万个独立 Mesh 实例的超大规模开放世界中，若继续依赖 CPU 在每一帧执行场景图遍历、包围盒视锥裁剪、LOD 选择、绘制常量打包以及海量 Draw Call 录制下发，CPU 核心将不可避免地陷入饱和瘫痪，PCIe 总线因频繁的命令与小数据传输而阻塞，GPU 强大的硬件计算阵列（SM/CU）则因饥饿（Starvation）而被迫处于空转状态。

   为了粉碎 CPU 侧的提交流水线瓶颈，现代图形架构迈向了终极演进方向——**GPU-Driven 渲染管线（GPU-Driven Rendering Pipeline）**。其核心哲学是：**将场景可见性判断、LOD 选择、资源索引绑定以及绘制指令生成的全链条控制权，从 CPU 全面移交至 GPU Compute Shader，CPU 仅需在帧初触发单次间接调度，由 GPU 自行决定“画什么、画多少、怎么画”**。本章将从间接绘制底层硬件机制出发，系统推导 GPU-Driven 流水线的数据结构组织、层次化深度（Hi-Z）遮挡剔除、两阶段无伪影遮挡架构，并提供工业级 Compute Shader 核心工程实现。

------------------------------------------------------------------------
42.1 传统 CPU-Driven 渲染管线的物理天花板
------------------------------------------------------------------------

CPU 绘制调度的线性开销瓶颈
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在传统的 CPU-Driven 模式下，渲染引擎在每一帧的主线程或渲染线程中必须按序执行如下任务链条：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  传统 CPU-Driven 渲染流水线的端到端执行链路               |
   +-------------------------------------------------------------------------+

   [ CPU 游戏逻辑 / 物理模拟 ]
                 |
                 v
   [ CPU 视锥体与遮挡裁剪 (Culling) ] ---> 单核遍历数万个 AABB 包围盒 (耗时严重)
                 |
                 v
   [ CPU LOD 计算与排序 ] --------------> 依据距离计算 LOD，按 PSO/材质排序减少状态切换
                 |
                 v
   [ CPU 逐实例常量与描述符更新 ] -------> 频繁通过内存写合并 (Write-Combined) 拷贝至 GPU 显存
                 |
                 v
   [ CPU 录制并下发 API Draw Calls ] ---> 调用 vkCmdDrawIndexed / DrawIndexedInstanced (数万次)
                 |
                 v
   [ 显卡驱动与 UMD/KMD 转换 ] ----------> 参数校验、Ring Buffer 锁争用、上下文切换开销
                 |
                 v (PCIe 总线传输命令数据包)
   [ GPU 前端命令处理器 (CP) ] ----------> 解包指令，驱动计算单元 (遭遇前端饥饿)

设场景中包含 $N_{	ext{mesh}}$ 个独立网格部件，平均每个部件在 CPU 侧执行剔除、LOD、状态判定与 API 提交的平均开销为 $t_{	ext{cpu}}$。若 $N_{	ext{mesh}} = 100,000$，$t_{	ext{cpu}} \approx 1.5\,\mu	ext{s}$，则仅 CPU 侧构建渲染命令的总耗时就高达：

.. math::

   T_{	ext{CPU}} = 100,000 	imes 1.5\,\mu	ext{s} = 150\,	ext{ms}

这远远突破了 60 FPS 所允许的 $16.6\,	ext{ms}$ 全帧总预算（其中分配给渲染提交的预算通常不足 $4\,	ext{ms}$）。尽管通过多线程并行录制命令列表（Command List / Command Buffer）能够在一定程度上分摊负载，但多线程依然面临同步互斥锁、内存分配碎片以及驱动层命令拼接的次级开销，无法从根本上消除 $O(N)$ 复杂度的数量级压制。

硬件利用率塌陷与 PCIe 总线带宽受限
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
CPU-Driven 模式还对 GPU 硬件流水线造成了严重的微架构反噬：

1. **GPU 前端饥饿与流水线气泡 (Pipeline Bubbles)**：当 Draw Call 颗粒度过细、每次绘制包含的多边形不足几十个时，GPU 前端命令处理器（Command Processor）从 Ring Buffer 读取并解码参数的速度，赶不上底层 SM/CU 硬件光栅化执行的速度，导致大量 SIMT 算力单元在等待新指令下发中空转；
2. **状态切换与驱动验证惩罚**：即使在现代显式 API 中，频繁切换根签名、描述符表或管线状态，依然会导致硬件流水线排空（Pipeline Drain）与缓存颠簸；
3. **回读延迟困境 (Readback Latency Dilemma)**：传统硬件遮挡查询（Occlusion Query）在 GPU 上执行测试后，其结果存储于显存中。若 CPU 试图读取查询结果以决定下一帧是否剔除物体，就必须忍受 $2 \sim 3$ 帧的 CPU-GPU 异步回读延迟，这不仅在镜头剧烈旋转时产生刺眼的遮挡穿帮（Popping Artifacts），更导致遮挡裁决逻辑完全无法应对高速动态场景。

------------------------------------------------------------------------
42.2 间接绘制 (Indirect Draw) 硬件机制与内存契约
------------------------------------------------------------------------

直接绘制与间接绘制的本质差异
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
打破 CPU 霸权的物理基石，是现代图形硬件提供的**间接绘制（Indirect Draw）能力**：

- **直接绘制 (Direct Draw)**：`vkCmdDrawIndexed` 或 `DrawIndexedInstanced`。绘制所需的图元顶点数、实例数、起始偏移等关键参数，均由 CPU 作为即时参数硬编码写入驱动的命令包中。GPU 只能无条件执行 CPU 下达的固定命令；
- **间接绘制 (Indirect Draw)**：`vkCmdDrawIndexedIndirect` 或 `ExecuteIndirect`。CPU 仅仅下达一条“去指定的 GPU 缓冲区地址读取绘制参数并执行绘制”的高级元指令。**绘制参数的实际数值驻留在 GPU 显存缓冲区（Indirect Argument Buffer）中，完全由 GPU 自身运行的 Compute Shader 在运行时计算并直接写入！**

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                  直接绘制 vs 间接绘制命令分发拓扑对比                   |
   +-------------------------------------------------------------------------+

   [ 直接绘制 Direct Draw ]
     CPU (计算数量) ===> [ 参数硬编码进 Command Stream: Count=100 ] ===> GPU 执行

   [ 间接绘制 Indirect Draw ]
     CPU ============> [ 调度元指令: 读取 Buffer 0x7FFF0000 处的参数 ] ===> GPU
                                      ^
                                      | (直接在显存内原地写入参数)
                       GPU Compute Shader (并发视锥剔除并写入可见数量)

间接绘制参数内存布局契约
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在 Direct3D 12 与 Vulkan 规范中，索引化间接绘制命令在显存中的二进制布局必须严格对齐硬件契约。在 Vulkan 中对应 `VkDrawIndexedIndirectCommand`，在 D3D12 中对应 `D3D12_DRAW_INDEXED_ARGUMENTS`：

.. list-table:: 索引化间接绘制参数 (Indexed Indirect Argument) 内存布局标准
   :widths: 22 18 20 40
   :header-rows: 1
   :class: tight-table

   * - 字段名称
     - 字节偏移 (Offset)
     - 物理类型
     - 硬件语义说明
   * - **indexCount**
     - `+0x00`
     - `uint32_t`
     - 本次 Draw 需要读取渲染的索引顶点总数
   * - **instanceCount**
     - `+0x04`
     - `uint32_t`
     - **绘制实例数量。若物体被剔除，GPU 将此值直接写 0**
   * - **firstIndex**
     - `+0x08`
     - `uint32_t`
     - 索引缓冲区（Index Buffer）内的起始读取位置偏移
   * - **vertexOffset**
     - `+0x0C`
     - `int32_t`
     - 顶点属性流读取时的基准顶点偏移量 (Base Vertex)
   * - **firstInstance**
     - `+0x10`
     - `uint32_t`
     - 实例 ID 的起始基准值，用于寻址该批次的首个实例数据
   * - **结构体总大小**
     - **20 字节**
     - `uint32_t[5]`
     - 硬件严格要求 4 字节自然对齐（在多命令数组中通常按 20 或对齐至 32 字节步进）

GPU 在执行间接绘制时，硬件微引擎直接通过 DMA 读取显存缓冲区对应偏移处的 20 字节数据。**最为关键的微架构特性在于：当 GPU Compute Shader 将 `instanceCount` 写入为 `0` 时，硬件前端会自动以近乎零时钟周期的代价跳过该绘制命令，完全不产生任何管线状态开销与片元生成！**

多重间接绘制与计数缓冲区 (Multi-Draw Indirect with Count)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
当场景中存在数万个不同网格时，如果为每个物体调用一次间接绘制，CPU 端依然需要提交大量指令。为此，现代硬件演进出了 **Multi-Draw Indirect with Count** 机制（Vulkan 的 `vkCmdDrawIndexedIndirectCountKHR`，D3D12 的 `ExecuteIndirect` 搭配 `pCountBuffer`）：

.. math::

   	ext{Command Count} = \min\left(	ext{maxDrawCount}, \quad 	ext{CountBuffer.Load}(	ext{offset})\right)

CPU 仅在帧初向 GPU 派发一条指令：*“请根据 `pCountBuffer` 中 GPU 自己计算出的实际活跃绘制总数，执行最多 `maxDrawCount` 个连续的间接绘制命令”*。这一指令彻底将 CPU 从每帧循环中解放出来，渲染一帧的 CPU 绘制调用从数万次急剧缩减为 **个位数**！

------------------------------------------------------------------------
42.3 纯 GPU-Driven 场景表示与无绑定 (Bindless) 架构
------------------------------------------------------------------------

场景资源的扁平化内存池设计
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
要实现纯 GPU-Driven 管线，所有原本离散分散在 CPU 内存中的网格元数据、变换矩阵、材质参数，必须全部重构为扁平化、全局驻留（Globally Resident）的大型 GPU 结构化缓冲区（Structured Buffer / ByteAddressBuffer）：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                GPU-Driven 场景全量驻留显存缓冲区拓扑设计                |
   +-------------------------------------------------------------------------+

   1. [ Scene Instance Buffer (全局实例缓冲) ]
      - InstanceID 0: { ModelMatrix, AABB_Min, AABB_Max, MeshID, MaterialID }
      - InstanceID 1: { ModelMatrix, AABB_Min, AABB_Max, MeshID, MaterialID }
      - ... (容纳全场景数十万个动态/静态物体的最新几何状态)

   2. [ Scene Mesh Pool (全局网格元数据池) ]
      - MeshID 0: { IndexOffset, IndexCount, BaseVertex, LodOffsets[4] }
      - MeshID 1: { IndexOffset, IndexCount, BaseVertex, LodOffsets[4] }

   3. [ Global Geometry Buffers (大一统几何显存池) ]
      - Mega-VertexBuffer: 全场景所有网格顶点属性交错合并存储于单一巨大 Buffer
      - Mega-IndexBuffer: 全场景所有三角形索引连续合并存储于单一巨大 Buffer

   4. [ Material & Texture Bindless Heap (无绑定全局材质堆) ]
      - 全局描述符索引数组: Texture2D g_Textures[] : register(t0, space1)
      - Material 结构体仅存储 TextureID (uint) 索引，着色器直接根据索引动态采样

无绑定材质解析 (Bindless Material Addressing)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
在传统的 CPU 渲染管线中，不同材质的物体不能合并在同一个 Multi-Draw Indirect 中，因为每个材质需要绑定不同的纹理资源。而借助 Chapter 38 所解构的 **Bindless（无绑定）架构**，着色器不再依赖外部绑定的插槽，而是通过材质索引直接在全局资源数组中寻址：

.. code-block:: hlsl

   // 在顶点或像素着色器中依据实例属性动态拉取材质
   struct InstanceData {
       float4x4 worldMatrix;
       uint materialIndex;
       uint meshIndex;
   };

   Texture2D g_BindlessTextures[] : register(t0, space1);
   SamplerState g_LinearSampler   : register(s0);

   float4 PS_Main(VSOutput input) : SV_Target {
       MaterialData mat = g_Materials[input.materialIndex];
       
       // 无需 CPU 切换状态，GPU 自身依据材质内的索引解包采样
       float4 albedo = g_BindlessTextures[mat.albedoTextureId].Sample(g_LinearSampler, input.uv);
       float4 normal = g_BindlessTextures[mat.normalTextureId].Sample(g_LinearSampler, input.uv);
       
       return EvaluatePBR(albedo, normal, ...);
   }

通过将几何缓冲、实例缓冲与材质纹理全部“池化与无绑定化”，GPU 获得了完全自主调度任何物体的物理自由度，彻底消除了由于“状态切换”而导致的批处理割裂。

------------------------------------------------------------------------
42.4 层次化深度缓冲 (Hi-Z) 硬件加速与构建算法
------------------------------------------------------------------------

Hi-Z 物理微架构与遮挡裁决原理
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
光栅化流水线虽然具备硬件 Early-Z 单元，但 Early-Z 只能在三角形像素光栅化阶段逐片元执行剔除，无法阻止顶点着色器（VS）与图元装配硬件的巨大吞吐开销。若能在 **物体绘制之前（即在网格甚至实例级别）** 就直接判断其是否完全被前景遮挡，几何前端的算力浪费将被彻底阻断。

现代 GPU 普遍在片上集成 **层次化 Z 缓存（Hierarchical Z / Hi-Z）硬件模块**。在 GPU-Driven 管线中，我们更倾向于在 Compute Shader 中构建自己的 **软件 Hi-Z 金字塔（Hi-Z Depth Pyramid）**，用于快速执行物体包围盒的保守遮挡测试：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                Hi-Z 层次化深度金字塔多级降采样下推拓扑                    |
   +-------------------------------------------------------------------------+

   Level 0 (1920x1080)  [ 原生硬件深度缓冲区 (Full Resolution Depth) ]
          |
          v (2x2 像素区域做 Conservative Reduction: 取深度最保守值)
   Level 1 (960x540)    [ 保留每个 2x2 区域离相机最近/最浅的深度值 ]
          |
          v
   Level 2 (480x270)
          |
          v
   ...
          v
   Level N (1x1)        [ 全屏离视点最近的绝对深度极值 ]

在采用 **Reversed-Z 规范（近平面为 1.0，远平面为 0.0）** 的现代图形引擎中，“距离相机更近”意味着深度值更大。因此，在构建 Hi-Z 金字塔时，每个上层纹素必须严格取下层对应 $2 	imes 2$ 区域四个深度采样点的 **最小值（Min-Reduction）**：

.. math::

   D_{	ext{parent}}(x, y) = \min_{u, v \in \{0, 1\}} D_{	ext{child}}(2x + u, 2y + v)

*物理保守性保证*：如果在某一 Mip 层级上，一个物体的最近深度值（在 Reversed-Z 下为最大深度 $Z_{	ext{box\_max}}$）都比该区域 Hi-Z 记录的深度极值还要小（即距离相机更远），则该物体必定被前景物体完全遮挡，可以被 **100% 绝对安全地剔除**！

Compute Shader 单通道/多通道 Hi-Z 金字塔生成
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
构建完整的 Hi-Z 纹理链通常有两种工业级实现方案：
1. **多通道驱动分派 (Multi-Pass Dispatch)**：通过渲染图（FrameGraph）连续派发 $\log_2(\max(W, H))$ 个微型 Compute Dispatch，第 $k$ 级读取第 $k-1$ 级并写入；
2. **单通道单着色器构建 (Single-Pass SPD / AMD FidelityFX SPD)**：利用原子操作协调全局计数器与 LDS 缓存，在一个 Compute Shader 内流式完成全级 Mipmap 生成，彻底省去跨 Pass 的显存往返刷新。

针对非 $2^n$ 偶数尺寸边界，采样算法必须引入边缘夹紧（Border Clamp）逻辑，防止空纹素引入非法零值破坏 Min-Reduction 的保守性。

------------------------------------------------------------------------
42.5 两阶段遮挡剔除架构 (Two-Phase Occlusion Culling)
------------------------------------------------------------------------

单阶段遮挡剔除的时延伪影困境
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
若仅使用单个阶段执行 Hi-Z 遮挡剔除，管线将面临不可调和的逻辑矛盾：
- *若使用上一帧（Frame $N-1$）的深度构建 Hi-Z 来剔除当前帧（Frame $N$）*：当相机快速平移或旋转时，上一帧处于视锥体外、而在当前帧新进入视口的物体，在上一帧深度缓冲中不存在深度记录，会被错误判定为“未遮挡”或误剔除；而已被上一帧遮挡的物体若因运动露出，会在当前帧出现明显的跳变延迟（1 帧延迟穿帮）；
- *若试图使用当前帧（Frame $N$）的深度*：当前帧尚未绘制任何几何体，深度缓冲区完全为空，根本无法先验执行遮挡测试。

两阶段无延迟精准遮挡流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
为了达成 **“零延迟穿帮”** 且 **“全 GPU 自动化”** 的双重目标，Ubisoft 在《刺客信条：大革命》以及业界现代 AAA 引擎中确立了经典的 **两阶段遮挡剔除架构（Two-Phase Occlusion Culling）**：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     两阶段无延迟 GPU-Driven 遮挡剔除流水线                |
   +-------------------------------------------------------------------------+

   [ 阶段 1: 第一阶段剔除与绘制 (Phase 1 Culling & Draw) ]
     1. GPU Compute Shader 读取【上一帧的历史 Hi-Z 缓冲区 (Frame N-1 Hi-Z)】
     2. 对全场景所有实例进行 视锥裁剪 + 历史 Hi-Z 遮挡测试
     3. 判定结果分流:
        - 【可见集合 A (Visible Set)】: 在上一帧本就可见的物体 (绝大多数表面)
        - 【不可见候选集 B (Hidden Candidates)】: 在上一帧被遮挡的物体，缓存其索引
     4. 立即分发【第一阶段间接绘制 (Phase 1 Indirect Draw)】: 仅渲染集合 A
                                   |
                                   v
   [ 阶段 2: 构建当前帧最新 Hi-Z (Construct Current Hi-Z) ]
     - 将阶段 1 绘制生成的最新真实深度缓冲区，通过 Compute Shader 快速生成【当前帧 Hi-Z (Frame N Hi-Z)】
                                   |
                                   v
   [ 阶段 3: 第二阶段复核剔除与补画 (Phase 2 Culling & Draw) ]
     1. GPU Compute Shader 重新提取【不可见候选集 B】
     2. 使用【当前帧最新的 Frame N Hi-Z】对候选集 B 进行二次深度遮挡测试
     3. 筛选出【漏判可见集合 C】: 上一帧被遮挡、但当前帧露出或新进入视口的边缘物体
     4. 分发【第二阶段间接绘制 (Phase 2 Indirect Draw)】: 仅补画集合 C
     5. 最终帧缓冲完整无缺，零穿帮、零延迟，且剔除效率逼近理论极限！

.. list-table:: 现代剔除方案工程特性全景横向矩阵
   :widths: 20 20 20 20 20
   :header-rows: 1
   :class: tight-table

   * - 方案名称
     - 执行硬件主体
     - CPU 提交负载
     - 遮挡裁决精度
     - 穿帮延迟缺陷
   * - **CPU 视锥体包围盒裁剪**
     - CPU 核心多线程
     - 极重 ($O(N)$ 遍历)
     - 极低 (无遮挡剔除)
     - 无延迟，但过绘制极高
   * - **硬件遮挡查询 (Query)**
     - GPU 绘制 Bounding Box
     - 重 (需多通道维护)
     - 高 (硬件精确深度)
     - **存在 1~3 帧回读穿帮**
   * - **CPU 软件光栅化 (Masked SW)**
     - CPU AVX-512 / NEON
     - 重 (抢占游戏逻辑算力)
     - 较高 (低分辨率深度)
     - 依赖多核负载平衡
   * - **GPU 单阶段 Hi-Z 剔除**
     - GPU Compute Shader
     - 极低 (单一元指令)
     - 较高 (历史帧深度)
     - **镜头移动时边缘闪烁**
   * - **GPU 两阶段 Hi-Z 剔除**
     - **GPU Compute Shader**
     - **极致 (2 次间接分发)**
     - **极高 (当前帧动态复核)**
     - **完全零穿帮、零延迟**

------------------------------------------------------------------------
42.6 工业级 GPU 视锥体与 Hi-Z 剔除 Compute Shader 完整实现
------------------------------------------------------------------------

以下给出基于 **HLSL (Shader Model 6.0+)** 构建的工业级 GPU-Driven 剔除内核源码。该着色器在单个 Compute Dispatch 中并发处理全场景所有实例，协同完成视空间变换、视锥体 6 平面相交测试、投影屏幕空间 AABB 估算、Hi-Z 金字塔保守采样，并通过原子操作将可见物体的间接绘制参数连续压缩输出到全局命令缓冲区中：

.. code-block:: hlsl

   // =========================================================================
   // File: GPUDrivenCulling.hlsl
   // Architecture: Two-Phase GPU-Driven Frustum & Hi-Z Occlusion Culling Kernel
   // Standard: HLSL Shader Model 6.0+, Wave Intrinsics, Indirect Draw Arguments
   // =========================================================================

   #define THREADS_PER_WORKGROUP 64

   // -------------------------------------------------------------------------
   // 1. 结构化数据契约定义
   // -------------------------------------------------------------------------
   struct InstanceData {
       float4x4 worldMatrix;
       float3   aabbMin;
       float    padding0;
       float3   aabbMax;
       uint     meshId;
   };

   struct MeshMetaData {
       uint indexCount;
       uint firstIndex;
       int  vertexOffset;
       uint baseInstance;
   };

   struct IndirectDrawIndexedArgs {
       uint indexCountPerInstance;
       uint instanceCount;
       uint startIndexLocation;
       int  baseVertexLocation;
       uint startInstanceLocation;
   };

   // -------------------------------------------------------------------------
   // 2. 资源绑定 (SRV / UAV / ConstantBuffer)
   // -------------------------------------------------------------------------
   cbuffer CameraConstants : register(b0) {
       float4x4 g_ViewMatrix;
       float4x4 g_ProjectionMatrix;
       float4x4 g_ViewProjectionMatrix;
       float4   g_FrustumPlanes[6]; // 视空间 6 个裁剪平面方程 (nx, ny, nz, d)
       float2   g_HiZDimensions;     // Hi-Z Level 0 的像素宽高
       uint     g_TotalInstanceCount;
       uint     g_IsSecondPhase;     // 0: 第一阶段 (写出历史可见并收集候选集), 1: 第二阶段复核
   };

   StructuredBuffer<InstanceData>       g_AllInstances        : register(t0);
   StructuredBuffer<MeshMetaData>       g_MeshPool            : register(t1);
   Texture2D<float>                     g_HiZTexture          : register(t2);
   SamplerState                         g_PointClampSampler   : register(s0);

   RWStructuredBuffer<IndirectDrawIndexedArgs> g_RWDrawCommands      : register(u0);
   RWStructuredBuffer<uint>                    g_RWDrawCountBuffer   : register(u1);
   RWStructuredBuffer<uint>                    g_RWHiddenCandidates  : register(u2);
   RWStructuredBuffer<uint>                    g_RWHiddenCountBuffer : register(u3);

   // -------------------------------------------------------------------------
   // 3. 几何包围盒变换与视锥体相交测试 (Frustum Culling)
   // -------------------------------------------------------------------------
   bool TestFrustumAABB(float3 boxMin, float3 boxMax, float4 planes[6]) {
       [unroll]
       for (int i = 0; i < 6; ++i) {
           float3 normal = planes[i].xyz;
           float  d      = planes[i].w;

           // 寻找沿法线正方向投影的最优顶点 (Positive Vertex)
           float3 p = float3(
               (normal.x >= 0.0f) ? boxMax.x : boxMin.x,
               (normal.y >= 0.0f) ? boxMax.y : boxMin.y,
               (normal.z >= 0.0f) ? boxMax.z : boxMin.z
           );

           // 若最优顶点仍在平面负半空间，则整个 AABB 必定完全在平截头体外部
           if (dot(normal, p) + d < 0.0f) {
               return false;
           }
       }
       return true;
   }

   // -------------------------------------------------------------------------
   // 4. 计算屏幕空间投影包围矩形与 Hi-Z 遮挡测试 (Hi-Z Occlusion Test)
   // -------------------------------------------------------------------------
   bool TestHiZOcclusion(float3 boxMin, float3 boxMax, float4x4 viewProj, Texture2D<float> hiZTex) {
       // 1. 提取包围盒的 8 个三维世界顶点
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

       float minX =  1.0f; float maxX = -1.0f;
       float minY =  1.0f; float maxY = -1.0f;
       float maxDeviceDepth = 0.0f; // Reversed-Z 下越靠近相机值越大

       // 2. 变换至齐次裁剪空间并计算屏幕矩形包围盒
       [unroll]
       for (int i = 0; i < 8; ++i) {
           float4 clip = mul(viewProj, float4(corners[i], 1.0f));
           
           // 近平面背面穿透保护：若顶点位于相机后方，保守判定为不可剔除
           if (clip.w <= 0.0001f) return true;

           float3 ndc = clip.xyz / clip.w;
           minX = min(minX, ndc.x);
           maxX = max(maxX, ndc.x);
           minY = min(minY, ndc.y);
           maxY = max(maxY, ndc.y);
           maxDeviceDepth = max(maxDeviceDepth, ndc.z); // 记录物体距相机最近的深度极值
       }

       // 映射到 [0, 1] UV 空间
       float2 minUV = saturate(float2(minX, -maxY) * 0.5f + 0.5f);
       float2 maxUV = saturate(float2(maxX, -minY) * 0.5f + 0.5f);
       float2 sizeUV = (maxUV - minUV) * g_HiZDimensions;

       // 3. 计算覆盖该投影尺寸的最佳 Hi-Z Mipmap 层级 (取 log2 使单个纹素能覆盖对应脚印)
       float maxDimension = max(sizeUV.x, sizeUV.y);
       float mipLevel = clamp(ceil(log2(max(maxDimension, 1.0f))), 0.0f, 10.0f);

       // 4. 在选定 Mip 级别采样 4 个纹素执行保守深度比较
       float4 sampleDepths;
       sampleDepths.x = hiZTex.SampleLevel(g_PointClampSampler, minUV, mipLevel);
       sampleDepths.y = hiZTex.SampleLevel(g_PointClampSampler, float2(maxUV.x, minUV.y), mipLevel);
       sampleDepths.z = hiZTex.SampleLevel(g_PointClampSampler, float2(minUV.x, maxUV.y), mipLevel);
       sampleDepths.w = hiZTex.SampleLevel(g_PointClampSampler, maxUV, mipLevel);

       // 在 Reversed-Z 下，Hi-Z 存储的是 Min-Reduction (区域内最浅的深度)
       // 四点中最远的值即为这一片区域能挡住后方的最小深度屏障
       float minOccluderDepth = min(min(sampleDepths.x, sampleDepths.y), min(sampleDepths.z, sampleDepths.w));

       // 若物体的最浅深度比遮挡物的最浅深度还要小（更靠远端），则必定被完全遮蔽
       if (maxDeviceDepth <= minOccluderDepth) {
           return false; // 被完全遮挡剔除
       }

       return true; // 可见
   }

   // -------------------------------------------------------------------------
   // 5. GPU-Driven 剔除计算主入口内核
   // -------------------------------------------------------------------------
   [numthreads(THREADS_PER_WORKGROUP, 1, 1)]
   void CS_GPUDrivenCulling(uint3 dispatchThreadId : SV_DispatchThreadID) {
       uint instanceIndex = dispatchThreadId.x;
       if (instanceIndex >= g_TotalInstanceCount) return;

       InstanceData inst = g_AllInstances[instanceIndex];
       MeshMetaData mesh = g_MeshPool[inst.meshId];

       // 步骤 1: 提取世界空间 AABB 包围盒
       float3 boxMin = inst.aabbMin;
       float3 boxMax = inst.aabbMax;

       // 步骤 2: 视锥体 6 平面相交剔除
       bool isVisible = TestFrustumAABB(boxMin, boxMax, g_FrustumPlanes);

       // 步骤 3: 视锥可见前提下，执行 Hi-Z 深度遮挡测试
       if (isVisible) {
           isVisible = TestHiZOcclusion(boxMin, boxMax, g_ViewProjectionMatrix, g_HiZTexture);
       }

       // 步骤 4: 依据阶段逻辑执行紧凑间接命令写入
       if (g_IsSecondPhase == 0) {
           // [第一阶段 Phase 1]
           if (isVisible) {
               // 可见实例：原子分配全局输出槽位，并写入间接绘制参数
               uint slot;
               InterlockedAdd(g_RWDrawCountBuffer[0], 1, slot);

               IndirectDrawIndexedArgs args;
               args.indexCountPerInstance = mesh.indexCount;
               args.instanceCount          = 1;
               args.startIndexLocation     = mesh.firstIndex;
               args.baseVertexLocation     = mesh.vertexOffset;
               args.startInstanceLocation  = instanceIndex;

               g_RWDrawCommands[slot] = args;
           } else {
               // 遮挡实例：记录进第二阶段复核候选列表
               uint hiddenSlot;
               InterlockedAdd(g_RWHiddenCountBuffer[0], 1, hiddenSlot);
               g_RWHiddenCandidates[hiddenSlot] = instanceIndex;
           }
       } else {
           // [第二阶段 Phase 2]: 仅对上一阶段判为被遮挡的候选集执行当前帧 Hi-Z 复核
           if (isVisible) {
               uint slot;
               InterlockedAdd(g_RWDrawCountBuffer[0], 1, slot);

               IndirectDrawIndexedArgs args;
               args.indexCountPerInstance = mesh.indexCount;
               args.instanceCount          = 1;
               args.startIndexLocation     = mesh.firstIndex;
               args.baseVertexLocation     = mesh.vertexOffset;
               args.startInstanceLocation  = instanceIndex;

               g_RWDrawCommands[slot] = args;
           }
       }
   }

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从硬件执行模型与微架构物理瓶颈出发，深度推导了现代图形系统向 **GPU-Driven 渲染管线** 跨越的技术体系：
1. **CPU 绘制调度的物理终局**：剖析了传统 CPU-Driven 模式下线性 $O(N)$ 遍历耗时、Ring Buffer 锁争用、驱动开销与 GPU 前端饥饿现象；
2. **间接绘制硬件契约**：解构了 `IndirectDrawIndexedArgs` 的 20 字节物理对齐规范，阐明了利用 GPU Compute Shader 直接在显存内部就地修改 `instanceCount` 实现无开销条件执行的机制；
3. **全局无绑定与大一统资源池**：构建了包括全场景实例大缓冲、顶点索引合流池（Mega-Buffer）与 Bindless 全局描述符索引堆的架构范式，彻底消除了由材质状态切换引起的管线碎片化；
4. **Hi-Z 层次化遮挡判定**：推导了基于 Reversed-Z 的 Min-Reduction 保守深度金字塔下推算法，以及利用屏幕空间投影包围盒单指令定位 Mipmap 执行四点遮挡采样的微架构；
5. **两阶段遮挡剔除架构**：阐释了利用历史帧 Hi-Z 预绘制可见表面、随后利用当前帧最新深度二次复核候选物体的时序拓扑，达成了零延迟、零闪烁、极致算力收敛的工业级绘制闭环。

GPU-Driven 管线虽然彻底解决了“实例（Instance）级别”的绘制提交与可见性剔除，但面对单体包含数百万高密三角形的雕刻级网格时，传统顶点光栅化流水线仍会遭遇严重的几何前端膨胀！
在下一章（**Chapter 43: 几何虚拟化与无限细节：UE5 Nanite 微多边形光栅化、BVH 视锥剔除与软光栅**）中，我们将深入现代图形学的巅峰之作——剖析基于簇（Cluster/Meshlet）的微多边形细分、层次化层级结构（DAG）与软硬件双光栅化混合引擎。
