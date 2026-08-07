第148章：GPU 硬件路线图
======================

核心知识点
----------

GPU Roadmap 的工程意义是把硬件变化映射到 Frame Path
   Shader core、RT unit、AI unit、memory hierarchy、chiplet、copy/video/display engine 和 power limit 都不是孤立卖点。判断一项新能力时先问它改变哪个 pass、哪类 resource、哪段 queue/sync，再看是否真正缩短关键路径。

通用 Shader Core 仍是图形系统的基础执行资源
   Vertex/pixel/compute/mesh shader、GPU culling、lighting、post-process、visibility resolve 等都依赖 shader core。未来改进通常体现在 wave 效率、寄存器、cache、低精度数据类型与调度能力。

专用 RT 单元只解决 Ray Path 的一部分
   Traversal 与 intersection 加速后，AS build/update、material shading、memory access、denoising 和 history 仍可能成为瓶颈。因此 RT 性能提升必须放回完整 ray effect 路径评估。

AI/Tensor 单元正在成为实时图形执行资源
   Upscaling、denoising、frame generation、neural texture/material 和 radiance cache 会把 feature/history 送入矩阵密集推理。渲染器应把 inference 当作可选 pass，并明确 backend、precision、temp memory 与 fallback。

Memory Hierarchy 决定新单元能否持续发挥作用
   4K G-buffer、AS、history、texture、material table 和 neural tensor 会共同竞争 cache/VRAM bandwidth。更高理论算力若被随机访问、cache miss 或显存压力限制，实际 frame 收益会很小。

Chiplet 的应用侧影响主要表现为数据局部性
   应用通常不会直接调度某个 die，但跨 chip/cache/内存分区的数据移动可能放大随机访问代价。Meshlet、material table、instance、light list 与 AS update 都应尽量按空间或工作集分组。

Power Limit 是跨平台算法选择的硬约束
   桌面独显、主机 APU、移动 SoC、XR 与云 GPU 的持续功耗不同。峰值 TFLOPS/TOPS 不能直接代表长期稳定性能，必须同时看频率、内存功耗、display/video、thermal 与 shared power budget。

异构 GPU 由多类执行单元共同完成一帧
   Graphics queue、async compute、RT、AI、copy、video encode、display engine 都可能在同一 frame 中协作。优化的核心不是“开启更多单元”，而是让 resource ready time、queue overlap 和 synchronization 真正减少 critical path。

Copy Engine 是 Streaming 与 GPU-Driven Pipeline 的关键支撑
   Texture/mesh streaming、readback、AS compaction、upload 都依赖 DMA/copy。每帧应有明确 upload budget、延迟生效规则和 fence/barrier，避免资源传输制造不可预测 stall。

Video 与 Display Engine 也是图形能力域
   Cloud streaming、录制、HDR、VRR、高刷新、多显示器和 XR compositor 都依赖 encoder/display。Capability table 应独立记录 codec、bit depth、HDR、refresh、DSC 等能力，而不是只记录 3D 性能。

Async Compute 只有在有可重叠空隙时才有收益
   Denoiser、histogram、light culling、particle 等 compute pass 可以与 graphics overlap；若共享资源导致额外 barrier、queue wait 或带宽竞争，异步反而可能延长整帧。

未来兼容设计应采用 Capability Tier
   不应按 GPU 型号硬编码路径。Backend 负责把 D3D/Vulkan/Metal/WebGPU 的 features、limits、formats、queues、memory budget 等映射为引擎内部几何、RT、neural、memory、presentation 等能力等级。

Feature Tier 必须同时绑定 Fallback
   Mesh shader 可回退 compute culling+indirect draw；RT 可回退 raster/compute；neural pass 可回退 TAAU/传统 denoiser；高端 presentation 可回退 SDR/低刷新。能力选择与降级必须成对设计。

测试矩阵是硬件兼容的最终证据
   至少覆盖 API backend、vendor、driver、OS、resolution、display mode、quality tier、feature combination 与 fallback。每项记录 visual result、GPU time、VRAM、queue overlap、frame pacing 与 artifact。

新硬件应先进入实验 Tier
   驱动、工具与引擎支持往往滞后于硬件发布。新 feature 应先通过自动画面对比、稳定性、性能阈值和可关闭开关，再成为默认路径。

Mesh Shading 的关键是资产与运行时共同采用 Meshlet
   导入阶段生成 cluster/meshlet 与 bounds，运行时做 cluster culling、LOD、compaction，再由 mesh shader 或 compute+indirect 执行。硬件能力会改变执行方式，但数据组织是更稳定的长期资产。

Work Graph/GPU-Driven 的趋势是把细粒度调度移到 GPU
   CPU 提供高层 scene metadata，GPU 负责可见性、LOD、draw compaction、material classification 和更多工作生成。收益是减少 CPU submission，代价是调试对象从 CPU draw call 转向 counter、indirect args、append buffer、barrier 和 GPU-generated work。

Ray/Neural/GPU-Driven 的共同趋势是 Frame Dataflow
   未来图形系统越来越像数据流：CPU 设置资源边界，GPU 分类、生成、追踪、推理、重建并输出。硬件路线的价值应由“数据流更短、同步更少、局部性更好、画质更稳定”证明。

硬件能力只有进入生态后才可交付
   API、驱动、capture/profiler、引擎、资产工具和内容规范都要支持，某项能力才从硬件规格变成生产能力。只有硬件宣传而缺少工具/驱动证据时，不应成为默认架构假设。

关键路径
--------

硬件能力评估：

::

   identify frame bottleneck
   → map to shader / RT / AI / memory / copy / display
   → query API capability
   → verify driver/tool support
   → enable engine feature tier
   → capture frame
   → confirm bottleneck moved or critical path shortened

跨平台能力设计：

::

   backend feature query
   → normalize capability fields
   → choose geometry/RT/neural/memory/presentation tier
   → select fallback for every optional feature
   → run compatibility matrix
   → promote stable tier to default

GPU-Driven 数据流：

::

   scene metadata
   → GPU culling/LOD/classification
   → generated work / indirect commands
   → raster/RT/neural passes
   → history/post/present
   → debug counters + capture evidence

概念辨析
--------

* **Peak Compute 与 Sustained Frame Performance**：峰值算力是理论上限，持续帧性能还受功耗、带宽、同步和资源驻留限制。
* **Specialized Unit 与 Independent Pipeline**：专用单元加速某段工作，仍需与 shader、memory 和 queue 协作。
* **Feature Detection 与 GPU Name Check**：前者查询真实能力，后者依赖型号假设，无法稳健跨代。
* **Async Compute 与 Free Performance**：异步只有在资源依赖与带宽允许重叠时才有效。
* **Hardware Support 与 Production Readiness**：硬件存在某能力不代表驱动、工具、引擎和资产链已经可交付。
* **GPU-Driven 与 CPU-Free**：CPU 仍负责高层状态和资源管理，细粒度可见性与工作生成更多转移到 GPU。

本章结论
--------

GPU 硬件路线应按“Frame Bottleneck—Execution Unit—Memory/Queue—API Capability—Engine Tier—Fallback—Tool/Test Evidence”理解。面向未来的渲染器不预测某一代硬件，而是把能力设计成可查询、可组合、可降级、可验证的数据流，使 shader、RT、AI、copy、display 与 GPU-driven 算法都能在新架构上平稳吸收收益。