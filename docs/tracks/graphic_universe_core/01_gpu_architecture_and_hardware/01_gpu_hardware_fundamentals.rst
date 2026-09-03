========================================================================
Chapter 1: GPU 硬件底层体系与执行模型
========================================================================

.. note:: 前置背景与认知锚点
   本章作为全书开篇，直接下潜至 GPU 芯片物理层级。通过剖析流水线硬件单元、单指令多线程调度逻辑、寄存器堆管理以及显存控制器拓扑，建立硬件微架构事实与图形 API / Shader 编译指令之间的直接映射关系。

------------------------------------------------------------------------
1.1 GPU 高吞吐执行模型与硬件定位
------------------------------------------------------------------------

现代图形处理器（GPU）在物理芯片层面的晶体管分配策略与通用处理器（CPU）存在本质差异。CPU 设计专注于降低单线程指令序列的执行延迟，将芯片面积大量分配给深层分支预测器、超标量乱序执行逻辑（Out-of-Order Execution Engine）以及多级大容量 SRAM 缓存（L1/L2/L3 Cache）。GPU 则将绝大部分晶体管面积分配给算术逻辑单元（ALU 阵列）与超大容量物理寄存器堆（Physical Register File），其核心设计目标是通过高并发线程吞吐量隐藏访存与运算延迟。

.. list-table:: CPU 与 GPU 物理资源分配与执行模型对比
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 硬件维度
     - CPU (延迟优化型)
     - GPU (吞吐优化型)
   * - 晶体管主要去向
     - 控制逻辑（分支预测、乱序调度）、大容量 L2/L3 缓存
     - 高密度 ALU 运算阵列、大规模寄存器堆
   * - 核心并发粒度
     - 少量（4~128）高主频、深流水线物理核心
     - 数千至数万个并发硬件线程槽位（Threads / Lanes）
   * - 延迟隐藏机制
     - 硬件预取（Prefetching）、投机执行、缓存命中
     - 零开销多线程束上下文切换（Zero-overhead Warp/Wave Context Switching）
   * - 典型工作负载
     - 强依赖分支预测、强因果依赖、低并发逻辑控制
     - 数据并行度高、控制流规整的大规模张量/网格/像素处理

为了具象化 GPU 硬件的运转流程，我们以一个标准的实时粒子渲染通道（Particle Render Pass）作为物理追踪对象：

1. **Host 端命令录制与装载**：CPU 驱动层构建绘制命令（`DrawIndexedInstanced` 或 `DrawIndirect`），将包含粒子空间坐标、初速度与生命周期的顶点缓冲区（Vertex Buffer）、纹理采样句柄及常量缓冲区（Constant Buffer / Push Constants）装配至命令缓冲区（Command Buffer），并写入位于系统内存或 PCIe BAR 空间的环形命令队列（Ring Buffer）。
2. **GPU 前端引擎拾取与解包**：GPU 命令处理器（Command Processor / Front-End）通过 DMA 读取命令，完成状态寄存器设置，并将图元装配任务交由硬件工作分发器（Work Distributor / Primitive Distributor）。
3. **计算单元网格化调度**：分发器根据管线配置，将百万级粒子顶点计算划分为固定宽度的线程束（NVIDIA Warp 为 32 线程，AMD Wavefront 为 32 或 64 线程），分派至各计算单元（SM / CU）。
4. **管线阶段数据流转**：顶点着色器（Vertex Shader）在 ALU 矩阵上并发执行矩阵变换；结果通过内部片上跨线交叉开关（Crossbar Switch）流向硬件光栅化器（Rasterizer）；生成的图元覆盖碎片（Fragments）再次被打包为像素着色器（Fragment Shader）线程束执行纹理采样与光照解算；最终经由输出合并单元（ROP / Color Management Unit）写入帧缓冲区（Render Target）。

------------------------------------------------------------------------
1.2 计算单元核心微架构拆解
------------------------------------------------------------------------

无论底层硬件厂商如何命名，GPU 的核心计算单元（NVIDIA 称 Streaming Multiprocessor - SM，AMD 称 Compute Unit - CU / Workgroup Processor - WGP，Apple 称 GPU Core）内部均包含一组高内聚的微架构组件。

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                        Compute Unit / SM 核心架构                        |
   |                                                                         |
   |  +-------------------------------------------------------------------+  |
   |  |                      Instruction Cache & Buffer                   |  |
   |  +-------------------------------------------------------------------+  |
   |  |                   Warp / Wavefront Scheduler                      |  |
   |  |                   Dispatch Unit (Dual-Issue)                      |  |
   |  +-------------------------------------------------------------------+  |
   |                                                                         |
   |  +-------------------------------------------------------------------+  |
   |  |               Large Physical Register File (e.g. 64K x 32-bit)    |  |
   |  +-------------------------------------------------------------------+  |
   |                                                                         |
   |  +---------------------+ +---------------------+ +--------------------+  |
   |  |  FP32 / INT32 ALUs  | |     SFU Units       | |    Tensor / Matrix |  |
   |  |  (Vector Lanes)     | |  (Sin/Cos/Rsqrt)    | |    Accelerators    |  |
   |  +---------------------+ +---------------------+ +--------------------+  |
   |                                                                         |
   |  +-------------------------------------------------------------------+  |
   |  |        Shared Memory / Local Data Share (LDS) / L1 Cache          |  |
   |  +-------------------------------------------------------------------+  |
   |  |                   Texture Processing Unit (TMU)                   |  |
   |  +-------------------------------------------------------------------+  |
   +-------------------------------------------------------------------------+

执行通道与向量运算单元 (ALU / Vector Lanes)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

计算单元的核心执行实体为物理 Lane。以 32 宽度的硬件单元为例，当执行指令 ``v_add_f32 v0, v1, v2`` 时，32 个 Lane 在同一时钟周期（或背靠背流水周期）内，同时读取各自线程的私有寄存器并执行加法运算。Lane 的硬件设计通常区分为单精度浮点（FP32）、双精度浮点（FP64）、32 位整型（INT32）及低精度整型/浮点（INT8/FP16）。

物理寄存器堆与占用率约束 (Register File & Occupancy)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

物理寄存器堆是计算单元内速度最快、面积占比极大的 SRAM 存储结构。每个 SM/CU 通常配备 64KB 至 256KB 的寄存器空间。在硬件层面上，寄存器并非在线程结束后动态申请与释放，而是在线程束派发（Dispatch）时根据编译期确定的每个线程需求量（VGPR - Vector General Purpose Register）进行静态块划分。

当单个着色器线程使用的寄存器数量增加时，SM 所能同时驻留（Resident）的线程束总数将受物理寄存器总容量硬性限制而下降，导致硬件占用率（Occupancy）降低。占用率下降直接削弱了调度器通过切换未阻塞线程束来覆盖全局显存读取延迟（典型开销为 200~800 时钟周期）的能力。

硬件线程束调度器 (Warp / Wavefront Scheduler)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

调度器每时钟周期检查所有驻留在当前计算单元内的线程束状态寄存器。一旦某个线程束的指令操作数准备就绪（无数据依赖且未在等待内存数据返回），调度器立即向 ALU 发射指令指针所指向的机器码。当一个线程束因执行全局显存加载指令 ``global_load`` 进入等待状态时，调度器在下一个时钟周期无缝切换至另一个就绪的线程束，实现流水线气泡（Stall Bubbles）的消除。

片上共享内存与一级数据缓存 (Shared Memory / LDS / L1 Cache)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Shared Memory（NVIDIA 称 Shared Memory，AMD 称 Local Data Share - LDS，Metal 称 Threadgroup Memory）是集成在计算单元内部的低延迟（15~30 时钟周期）可编程片上 SRAM。它由多个独立的物理存储体（Banks，通常为 32 个）构成。当同一线程束内的不同线程访问不同 Bank 时，可实现单周期全并发读写；若多个线程同时访问同一 Bank 内的不同地址，则会触发硬件存储体冲突（Bank Conflict），导致内存请求串行化。

专用硬件单元 (SFU / TMU / ROP)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **特殊函数单元 (SFU)**：专用硬件逼近电路，用于高速解算倒数平方根（`rsqrt`）、正弦（`sin`）、余弦（`cos`）及以 2 为底的指数（`exp2`）等非线性数学指令。
- **纹理处理单元 (TMU)**：独立于主 ALU 的固定硬件，负责解包压缩纹理格式（BCn/ASTC/ETC）、执行双线性/三线性插值过滤以及计算各向异性采样足迹。
- **光栅化与输出合并单元 (ROP)**：负责执行早期/晚期深度测试（Early-Z / Late-Z）、模板测试、多重采样抗锯齿（MSAA）覆盖率合成以及向显存写入颜色数据时的无损压缩（Color Compression）。

------------------------------------------------------------------------
1.3 主流 GPU 架构对比分析（NVIDIA / AMD / Apple）
------------------------------------------------------------------------

对主流硬件体系的工程选型与性能调优，需建立在统一的物理参数与内存拓扑维度上：

.. list-table:: 现代主流 GPU 架构微体系特征对比矩阵
   :widths: 20 26 26 28
   :header-rows: 1
   :class: tight-table

   * - 比较维度
     - NVIDIA (Ada Lovelace / Blackwell)
     - AMD (RDNA 3 / RDNA 4)
     - Apple Silicon (M3 / M4 系列)
   * - 基础执行单元
     - Streaming Multiprocessor (SM)
     - Compute Unit (CU) / WGP
     - GPU Core
   * - 硬件调度粒度
     - 32 线程 (Warp)
     - 32 线程 (Wave32) / 64 线程 (Wave64)
     - 32 线程 (SIMDgroup)
   * - 显存物理拓扑
     - 独立高速 GDDR6X / HBM3 显存
     - 独立 GDDR6 显存 + 巨型 Infinity Cache
     - SoC 统一内存架构 (UMA)，高带宽共享 LPDDR5X
   * - 渲染架构模式
     - 立即模式渲染 (Immediate Mode IMR)
     - 立即模式渲染 (Immediate Mode IMR)
     - 贴片延迟渲染 (Tile-Based Deferred Rendering TBDR)
   * - 专用加速模块
     - Tensor Core (矩阵/AI), RT Core (求交)
     - AI Matrix Accelerator, Ray Accelerator
     - Neural Engine, Ray Tracing Acceleration Block
   * - 官方调试基础设施
     - NVIDIA Nsight Graphics / Nsight Systems
     - AMD Radeon Developer Tool Suite (RGP/RMV)
     - Xcode Metal Debugger & Instruments GPU Trace

在架构特征层面：

- **NVIDIA 架构**：强调极高的 ALU 峰值性能与成熟的专用算力单元，配合庞大的 L2 缓存（如 RTX 40 系列高达 72MB~96MB）缓解显存总线带宽压力。其内存子系统对非对齐访存具备较强的硬件合并能力。
- **AMD RDNA 架构**：采用双计算单元组合形成的 WGP 结构，支持原生 Wave32 模式以降低控制流分支开销，并通过片上 Infinity Cache 大幅降低外部 DRAM 功耗与访问延迟。
- **Apple Silicon 架构**：深度结合 TBDR 模式。GPU 核心在光栅化阶段先将屏幕划分为 16x16 或 32x32 像素的片区（Tiles），将整个片区的几何数据、深度与颜色完全保留在计算单元片上的高速 Tile Memory 中处理，仅在 Pass 结束时向系统内存写回最终像素，从而极大降低外部内存总线带宽消耗。

------------------------------------------------------------------------
1.4 GPU 性能瓶颈的物理根源与分析模型
------------------------------------------------------------------------

在渲染引擎运行过程中，帧耗时瓶颈必定收敛于某项物理资源的饱和或阻塞。建立清晰的性能归因模型，是实施定向优化的前提。

.. code-block:: text

   +-----------------------------------------------------------------------+
   |                        GPU 硬件性能瓶颈分类体系                       |
   +-----------------------------------------------------------------------+
        |
        +---> 1. 算力瓶颈 (Compute / ALU Bound)
        |        * 核心表现：ALU 管线满载，指令发射槽饱和
        |        * 诱发原因：复杂 PBR 材质解算、光线求交步进、高频数学函数循环
        |
        +---> 2. 带宽瓶颈 (Memory Bandwidth Bound)
        |        * 核心表现：外部 DRAM / VRAM 总线吞吐达 85%+ 饱和上限
        |        * 诱发原因：高分辨率未压缩 G-Buffer、大量半透明全屏 Overdraw 读写
        |
        +---> 3. 延迟与占用率瓶颈 (Latency / Occupancy Bound)
        |        * 核心表现：GPU 计算单元空转，活跃线程束不足以掩盖访存挂起
        |        * 诱发原因：着色器 VGPR 暴涨、非连续随机显存跳跃访问 (Cache Miss)
        |
        +---> 4. 控制流发散瓶颈 (Control Flow Divergence)
        |        * 核心表现：硬件执行掩码 (Execution Mask) 分裂，执行吞吐成倍下降
        |        * 诱发原因：同一 Warp 内线程命中不同动态分支路径（如 `if-else`）
        |
        +---> 5. 驱动与管线提交瓶颈 (Submission & Sync Bound)
                 * 核心表现：CPU-GPU 执行气泡、硬件队列频繁等待屏障（Pipeline Barrier）
                 * 诱发原因：过度细碎的 Draw Call、跨队列显式同步等待、频繁管线重绑定

------------------------------------------------------------------------
1.5 渲染引擎中的 GPU 能力拓扑探测与 Fallback 机制
------------------------------------------------------------------------

工业级渲染引擎在初始化图形管线前，必须首先向操作系统与驱动层查询目标物理设备的能力拓扑结构，构建运行时硬件画像，并确立特性降级状态机。

以现代图形标准（以 WebGPU / Vulkan 为代表的显式 API）为例，能力探测遵循以下规范化流程：

.. code-block:: typescript

   // WebGPU 设备拓扑探测与管线自适应协商实现
   interface GraphicsDeviceProfile {
     adapterName: string;
     backendType: string;
     maxTextureDimension2D: number;
     maxStorageBufferBindingSize: number;
     supportsASTC: boolean;
     supportsBCn: boolean;
     supportsTimestampQuery: boolean;
     tierLevel: 'low' | 'medium' | 'high' | 'ultra';
   }

   async function probeAndInitializeGraphicsDevice(): Promise<{
     device: GPUDevice;
     profile: GraphicsDeviceProfile;
   }> {
     // 1. 请求物理适配器 (Physical Adapter)
     const adapter = await navigator.gpu?.requestAdapter({
       powerPreference: 'high-performance'
     });
     
     if (!adapter) {
       throw new Error('当前运行环境未检测到可用的现代图形适配器');
     }

     // 2. 探测可选特性标志 (Feature Bits)
     const requiredFeatures: GPUFeatureName[] = [];
     const supportsBCn = adapter.features.has('texture-compression-bc');
     const supportsASTC = adapter.features.has('texture-compression-astc');
     const supportsTimestampQuery = adapter.features.has('timestamp-query');

     if (supportsBCn) requiredFeatures.push('texture-compression-bc');
     if (supportsASTC) requiredFeatures.push('texture-compression-astc');
     if (supportsTimestampQuery) requiredFeatures.push('timestamp-query');

     // 3. 读取硬件资源硬性上限 (Limits)
     const limits = adapter.limits;
     const maxTexSize = limits.maxTextureDimension2D;
     const maxStorageSize = limits.maxStorageBufferBindingSize;

     // 4. 根据拓扑参数划分硬件能力等级 (Tier Classification)
     let tier: GraphicsDeviceProfile['tierLevel'] = 'medium';
     if (maxTexSize >= 16384 && maxStorageSize >= 1073741824 && (supportsBCn || supportsASTC)) {
       tier = 'ultra';
     } else if (maxTexSize >= 8192 && maxStorageSize >= 134217728) {
       tier = 'high';
     } else if (maxTexSize < 4096) {
       tier = 'low';
     }

     // 5. 实例化逻辑设备 (Logical Device)
     const device = await adapter.requestDevice({
       requiredFeatures,
       requiredLimits: {
         maxTextureDimension2D: maxTexSize,
         maxStorageBufferBindingSize: maxStorageSize,
       }
     });

     const profile: GraphicsDeviceProfile = {
       adapterName: (adapter as any).info?.device || 'Generic GPU',
       backendType: (adapter as any).info?.architecture || 'Generic Architecture',
       maxTextureDimension2D: maxTexSize,
       maxStorageBufferBindingSize: maxStorageSize,
       supportsASTC,
       supportsBCn,
       supportsTimestampQuery,
       tierLevel: tier,
     };

     return { device, profile };
   }

通过上述自适应探测，渲染引擎可以在底层确立清晰的 Fallback 策略：

1. **纹理格式降级**：若不支持桌面级 BCn 压缩纹理，且运行于移动端环境，管线自动切换至 ASTC 或 ETC2 格式资源；若均不支持，则退回至量化的 RGBA8 未压缩数据流。
2. **计算存储降级**：若 `maxStorageBufferBindingSize` 低于大型粒子系统所需的连续内存空间，引擎将计算着色器的全局内存连续写入模式，拆分降级为多 Pass 纹理缓存渲染（Ping-Pong Render Target 架构）。
3. **着色复杂度降级**：依据划分的硬件等级，低端设备自动屏蔽视差映射（Parallax Occlusion Mapping）与每像素局部光追步进，改用标准法线贴图与环境球谐光照。

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从硬件物理晶体管与执行模型出发，剖析了 GPU 高吞吐计算单元的构成机制、寄存器与 Occupancy 的约束因果、主流厂商架构的物理特性以及硬件能力的探测降级路径。

在建立硬件宏观认知后，下一章我们将深入计算单元内部的指令执行微结构——剖析 **SIMD（单指令多数据）与 SIMT（单指令多线程）执行模型**，推导线程束在发生控制流分支发散（Branch Divergence）时的硬件掩码切换开销，并推导编写高利用率 Shader 代码的底层规则。
