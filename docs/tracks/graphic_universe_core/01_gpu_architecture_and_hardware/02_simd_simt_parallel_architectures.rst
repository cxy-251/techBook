========================================================================
Chapter 2: 并行架构剖析：SIMD 与 SIMT 机制
========================================================================

.. note:: 前置背景与认知承接
   上一章解构了 GPU 计算单元的物理拓扑、寄存器堆与显存层次。本章将观察尺度聚焦至单条着色器指令在计算单元内部的并发推进过程，深入剖析 SIMD 与 SIMT 的概念分界、硬件线程束（Warp / Wavefront）调度状态机、控制流分支发散（Branch Divergence）的底层掩码切换机制，以及高吞吐 Shader 代码的编写准则。

------------------------------------------------------------------------
2.1 SIMD 与 SIMT 执行模型的本质区别
------------------------------------------------------------------------

在并行计算架构体系中，SIMD（Single Instruction, Multiple Data）与 SIMT（Single Instruction, Multiple Threads）分别代表了不同抽象层级的并行设计哲学：

- **SIMD（单指令多数据流）**：属于 Flynn 分类法中的经典硬件向量化模型。在 SIMD 架构（如 CPU 的 AVX-512 或 GPU 内部的专用向量指令）中，程序员或向量化编译器显式操作宽位宽向量寄存器（如 512-bit 寄存器被划分为 16 个 32-bit 单精度浮点槽位）。一条向量加法指令直接驱动一组硬件计算通路（Lanes），同时对这 16 个数据槽位执行加法。其控制流、指令发射与寄存器寻址均以整个向量为单一实体。
- **SIMT（单指令多线程）**：是现代 GPU 面向通用可编程着色器（Programmable Shaders / Compute Kernels）构建的硬件编程模型。在 SIMT 模型下，程序员编写的代码呈现为纯粹的标量执行流——每个着色器调用实例（Shader Invocation / Thread）拥有独立的逻辑程序计数器（PC）、私有局部变量与内置几何/像素坐标。底层硬件在执行时，自动将一组同构的标量线程（NVIDIA 称 Warp，AMD 称 Wavefront，Metal 称 SIMDgroup）组织在一起，由单个硬件指令发射单元驱动一组物理 Lane 同步步进。

.. list-table:: SIMD 与 SIMT 架构特征对比矩阵
   :widths: 20 40 40
   :header-rows: 1
   :class: tight-table

   * - 比较维度
     - SIMD (向量化执行模型)
     - SIMT (多线程标量映射模型)
   * - 编程视角
     - 显式向量类型操作（如 `float32x4_t`, `__m512`）
     - 纯标量代码编写（每个 Invocation 操作标量变量）
   * - 寄存器组织
     - 单个宽位宽向量寄存器划分多个数据通道
     - 每个线程分配独立的标量通用物理寄存器（VGPR）
   * - 控制流机制
     - 显式向量位掩码运算（Vector Masking）
     - 硬件自动维护活动掩码（Active Mask）与分支栈
   * - 线程独立性
     - 无独立线程上下文，仅存在单线程内部的数据通道
     - 逻辑上具备独立线程状态、私有堆栈与局部变量
   * - 硬件调度粒度
     - 单条向量指令
     - 线程束 / 波前（Warp: 32 线程 / Wavefront: 32/64 线程）

为了深入追踪 SIMT 的微架构执行过程，我们以一个全屏图像后处理着色器（Post-Processing Fragment Shader）作为贯穿全章的观察用例。在 1920×1080 分辨率下，管线需要处理 2,073,600 个像素点。在代码编写层面，着色器仅描述单个像素的计算逻辑：

.. code-block:: wgsl

   // 全屏图像色彩校正与高光提亮着色器 (WGSL 规范)
   @group(0) @binding(0) var sceneColorTexture: texture_2d<f32>;
   @group(0) @binding(1) var maskTexture: texture_2d<f32>;
   @group(0) @binding(2) var textureSampler: sampler;

   struct ColorGradingParams {
       exposure: f32,
       contrast: f32,
       highlightGain: f32,
       threshold: f32,
   };
   @group(0) @binding(3) var<uniform> params: ColorGradingParams;

   @fragment
   fn mainPostProcess(@builtin(position) fragCoord: vec4<f32>) -> @location(0) vec4<f32> {
       let uv = fragCoord.xy / vec2<f32>(1920.0, 1080.0);
       var color = textureSample(sceneColorTexture, textureSampler, uv);
       let maskVal = textureSample(maskTexture, textureSampler, uv).r;

       // 基础曝光调整 (所有线程必定执行的规整数据流)
       color = vec4<f32>(color.rgb * params.exposure, color.a);

       // 条件高光增益 (引发控制流分支发散的判定点)
       if (maskVal > params.threshold) {
           color = vec4<f32>(color.rgb * params.highlightGain, color.a);
       }

       return color;
   }

在 Host 提交绘制命令后，GPU 驱动与硬件工作分发器（Work Distributor）将 200 余万个片段划分为数万个 32 宽度的 Warp。每个 Warp 覆盖屏幕上一块 8×4 或 4×8 像素的连续空间区域。当 SM 拾取并执行该着色器指令时，虽然源代码为标量逻辑，但硬件通过 32 个物理 Lane 同时推进 32 个相邻像素的色彩解算。

------------------------------------------------------------------------
2.2 线程束（Warp / Wavefront）微架构与硬件调度行为
------------------------------------------------------------------------

线程束（Warp / Wavefront）是 GPU 计算单元指令发射与上下文切换的最小不可分割物理调度单元。

硬件调度器状态机与指令流水线
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

计算单元内的硬件线程束调度器维护着一组处于不同生命周期阶段的 Warp 状态槽位。单个 Warp 的完整指令推进流水线由以下状态构成：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                       Warp 硬件调度状态机流转图                          |
   +-------------------------------------------------------------------------+
        |
        v
   [ 1. 处于就绪队列 (Eligible / Ready) ]
        |  * 指令指针 (PC) 有效，所有输入操作数已在寄存器中就绪
        |  * 无未完成的数据依赖与显存屏障
        |
        +---> (调度器选中并执行多路发射 Issue)
        |
        v
   [ 2. 算术执行阶段 (ALU Pipeline Execution) ]
        |  * 32 个 Lane 同步执行单精度浮点/整型运算
        |  * 计算结果在流水线结束周期直接写回物理寄存器 (Writeback)
        |
        +---> (遇到显存加载指令: global_load / image_sample)
        |
        v
   [ 3. 访存阻塞阶段 (Memory Stall / Wait State) ]
        |  * 向显存子系统发出 Texture Fetch / Buffer Read 异步请求
        |  * 延迟周期：200 ~ 800 个时钟周期
        |  * 调度器立即切换至另一个 Ready 状态的 Warp (Zero-overhead Switch)
        |
        +---> (数据从 L1/L2 缓存或 DRAM 返回，计分板 Scoreboard 置位)
        |
        v
   [ 4. 重新激活阶段 (Re-activated to Ready Pool) ]

零开销上下文切换物理基础
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

CPU 在执行线程上下文切换时，必须由操作系统内核陷入中断，将当前核心的通用寄存器、栈指针及控制状态保存至主存，再加载新线程的寄存器上下文，产生数千个时钟周期的开销。

GPU 计算单元则完全通过硬件静态分配实现**零开销切换**：

1. 当一个 Warp 被分派至 SM 时，其所需的全量物理寄存器（VGPR）与架构状态被一次性锁定在物理寄存器堆的独立物理扇区中。
2. 调度器仅需切换内部的选择指针（Warp Slot Index），即可在下一个时钟周期将发射端口切换至另一个已就绪的 Warp，无需进行任何物理寄存器的溢出与转储操作。
3. 只要 SM 内部驻留的活跃 Warp 数量足够多，访存挂起的时间将被完全覆盖在其他 Warp 的 ALU 计算周期之中。

寄存器分配与 Occupancy 物理数学关系
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

计算单元的硬件占用率（Occupancy）定义为：当前驻留在计算单元内的活跃线程束数量与硬件所支持的最大理论线程束容量之比。

.. math::

   	ext{Occupancy} = \frac{	ext{Active Warps per SM}}{	ext{Maximum Supported Warps per SM}}

假设某 GPU 微架构单 SM 具备 65,536 个 32-bit 物理寄存器（256 KB），单个 SM 理论最大支持驻留 48 个 Warp（1,536 线程）。每个 Warp 包含 32 个线程：

.. list-table:: 着色器寄存器占用对 SM 硬件占用率的影响推导
   :widths: 25 25 25 25
   :header-rows: 1
   :class: tight-table

   * - 单线程寄存器数 (VGPR)
     - 单 Warp 寄存器消耗
     - SM 最大驻留 Warp 数量
     - 最终硬件 Occupancy
   * - 32 VGPRs
     - 1,024 寄存器
     - 48 Warps (满载)
     - 100.0%
   * - 40 VGPRs
     - 1,280 寄存器
     - 48 Warps (受限于槽位)
     - 100.0%
   * - 64 VGPRs
     - 2,048 寄存器
     - 32 Warps
     - 66.7%
   * - 128 VGPRs
     - 4,096 寄存器
     - 16 Warps
     - 33.3%

当着色器由于复杂的局部数学公式或过多临时变量导致编译器分配 128 个寄存器时，Occupancy 骤降至 33.3%。此时 SM 内仅有 16 个 Warp 可供调度。一旦这 16 个 Warp 同时向显存发起纹理采样，SM 内部将无可用 Warp 执行计算，ALU 阵列陷入空转，帧耗时显著拉长。

------------------------------------------------------------------------
2.3 控制流分支发散（Branch Divergence）的底层硬件机制
------------------------------------------------------------------------

在 SIMT 执行架构中，同一个 Warp 内的 32 个 Lane 必须共享完全相同的硬件程序计数器（PC）。当着色器代码中出现基于数据条件的动态分支结构时，便会触发控制流分支发散。

硬件执行掩码 (Active Mask) 栈机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

GPU 硬件通过一个 32 位的执行掩码寄存器（Active Mask Register）控制每个 Lane 的使能状态：

- 当 Active Mask 的第 $i$ 位为 `1` 时，Lane $i$ 正常执行指令并写入寄存器目标地址。
- 当 Active Mask 的第 $i$ 位为 `0` 时，Lane $i$ 被硬件屏蔽（Clock Gated 或取消写回使能），其计算结果直接作废，不产生任何副作用。

考察全屏后处理着色器中的分支：

.. code-block:: wgsl

   if (maskVal > params.threshold) {
       // Path A: 高光增益路径
       color = color * params.highlightGain;
   } else {
       // Path B: 普通直通路径
       color = color * 1.0;
   }

假设某 Warp 覆盖高光与阴影交界处，其中 Lane 0~15 对应的像素 `maskVal > threshold`（条件为真），Lane 16~31 的像素 `maskVal <= threshold`（条件为假）。硬件执行流程如下：

.. code-block:: text

   +-------------------------------------------------------------------------+
   |                     分支发散串行化执行与掩码压栈流程                    |
   +-------------------------------------------------------------------------+

   [ 初始状态: 全员活跃 ]
   PC: 0x0040 (分支判定指令: cmp_gt_f32)
   Active Mask: 0xFFFFFFFF (32 个 Lane 全开)
        |
        v
   [ 阶段 1: 压栈汇合点 PC 与当前掩码，生成分支掩码 ]
   硬件分支栈压入 Reconvergence PC (0x0080)
   Path A Mask = 0x0000FFFF (低 16 位激活)
   Path B Mask = 0xFFFF0000 (高 16 位激活)
        |
        v
   [ 阶段 2: 串行执行 Path A ]
   PC: 0x0048 (mul_f32 color, color, highlightGain)
   Active Mask: 0x0000FFFF
   * Lane 0~15  执行浮点乘法计算并写回寄存器 (有效利用率 50%)
   * Lane 16~31 处于物理空转挂起状态
        |
        v
   [ 阶段 3: 翻转掩码，串行执行 Path B ]
   PC: 0x0060 (Path B 指令段)
   Active Mask: 0xFFFF0000
   * Lane 0~15  处于物理空转挂起状态
   * Lane 16~31 执行直通赋值并写回寄存器 (有效利用率 50%)
        |
        v
   [ 阶段 4: 路径重聚 (Reconvergence Point) ]
   PC: 0x0080 (弹栈恢复统一执行)
   Active Mask 恢复为 0xFFFFFFFF

分支发散对性能的量化损耗
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当发散发生时，该 Warp 的总执行时间为各独立分支路径耗时的**算术叠加**：

.. math::

   T_{	ext{warp}} = T_{	ext{Path A}} + T_{	ext{Path B}}

在此期间，ALU 的实际硬件吞吐效率直接腰斩。若存在深层嵌套的 `if-else` 或循环次数不一致的分支，Warp 将在内部依次串行遍历所有被命中的子路径，导致计算单元吞吐量呈指数级衰减。

------------------------------------------------------------------------
2.4 着色器分支开销优化与工程设计准则
------------------------------------------------------------------------

在着色器架构设计中，控制流优化的核心目标是：保持 Warp 内部执行方向的高度空间一致性，或在发散发生时将浪费的物理资源降至最低。

准则 1：统一分支（Uniform Branch）上移与管线变体解耦
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

若分支判定条件在整个 Draw Call 或 Material 批次内保持一致（例如由 Uniform 缓冲区或 Push Constants 传入的功能开关），所有 Lane 的判定结果必定完全相同，Warp 内部 Active Mask 始终为 `0xFFFFFFFF`，不会产生任何硬件发散开销。

对于复杂的宏观功能切换（如是否启用法线贴图、是否启用阴影解算），应将控制流提升至 CPU 侧或通过着色器变体（Shader Variants / Specialization Constants）在编译期直接剥离未激活代码分支。

准则 2：短小分支的 Branchless 数据流转换
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于仅包含 1~3 条简单 ALU 运算且不涉及复杂访存的短分支，使用内置数学算子（如 WGSL 的 `select`、`mix`、`step`，或 HLSL 的 `lerp`）将控制流转换为纯粹的数据流运算：

.. code-block:: wgsl

   // 优化前：存在动态控制流分支
   fn calculateHighlight_Branch(color: vec3<f32>, mask: f32, gain: f32) -> vec3<f32> {
       var result = color;
       if (mask > 0.5) {
           result = color * gain;
       }
       return result;
   }

   // 优化后：纯数据流选择，Active Mask 保持全开，无分支栈开销
   fn calculateHighlight_Branchless(color: vec3<f32>, mask: f32, gain: f32) -> vec3<f32> {
       let condition = mask > 0.5;
       let factor = select(1.0, gain, condition);
       return color * factor;
   }

准则 3：Branchless 改造的纹理带宽陷阱
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Branchless 优化存在严格的适用边界。当分支内部包含高开销的纹理采样（Texture Fetch）或显存加载操作时，强行消除分支将导致严重的反向性能劣化：

.. code-block:: wgsl

   // 严重反模式：为了消除分支导致所有 Lane 执行昂贵的额外采样
   fn sampleDetail_AntiPattern(uv: vec2<f32>, needDetail: bool) -> vec4<f32> {
       // 无论 needDetail 是否成立，所有 32 个 Lane 均向显存总线发起 4 次高开销采样请求！
       let detailColor = textureSample(heavyDetailMap, textureSampler, uv);
       return select(vec4<f32>(0.0), detailColor, needDetail);
   }

在这种场景下，保留 `if (needDetail)` 是更优选择。虽然边缘区域可能产生分支发散，但在大量背景区域，整个 Warp 可以完全跳过纹理采样指令，从而大幅节省显存总线带宽。

着色器控制流优化决策矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table:: 着色器控制流设计与优化决策矩阵
   :widths: 20 25 25 30
   :header-rows: 1
   :class: tight-table

   * - 分支特征与条件源
     - 典型应用场景
     - 推荐工程实现方案
     - 微架构物理影响与收益
   * - 绘制级常量 (Uniform)
     - 光照模式切换、调试视图开关
     - 着色器变体 / 特化常量 (Specialization Constants)
     - 零发散开销，完全消除未激活代码的寄存器占用
   * - 屏幕空间大面积连续条件
     - 屏幕视口裁剪、天空盒判定
     - 显式 `if-else` 分支结构
     - 绝大部分 Warp 整体跳过分支，节约大量运算与带宽
   * - 像素级高频交错条件 (1~3 条 ALU)
     - 阈值色彩增益、Alpha 通道混合
     - Branchless 数学算子 (`select`, `mix`, `clamp`)
     - 消除分支栈压栈与掩码翻转开销，稳定指令流水线
   * - 包含纹理/显存读取的条件
     - 视差贴图步进、细节纹理贴片
     - 保留显式分支，控制条件空间分布
     - 保护显存总线带宽，避免无效 Lane 发起内存事务

------------------------------------------------------------------------
小结与下章导读
------------------------------------------------------------------------

本章从硬件执行层解构了 SIMD 与 SIMT 的本质差异，剖析了线程束调度器的状态推进与零开销上下文切换机制，并深入推导了分支发散时的 Active Mask 掩码压栈行为及其对有效算力吞吐的制约。

理解了指令流水线的执行开销后，下一章我们将下潜至 GPU 性能最核心的瓶颈来源——**显存层级、缓存拓扑与带宽延迟模型**，深入解构 GPU 内部从物理寄存器堆、片上 L1/Shared Memory、巨型 L2 Cache 到外部 DRAM（GDDR6/HBM/统一内存）的存取延迟与吞吐极限，并建立显存合并访问（Memory Coalescing）的底层优化模型。
