第103章：渲染管线模式
====================

核心知识点
----------

渲染管线模式解决的是“一帧如何被组织”
   固定顺序、Forward、Deferred、Render Graph、GPU-driven 与 Hybrid Ray Tracing 的差别，首先体现在 pass 边界、资源依赖、光照组织、CPU/GPU 分工和平台能力，而不是 API 名称。模式选择必须从目标画面和 frame 数据路径反推。

一帧应先被拆成 Pass 与 Resource，再讨论实现方式
   Shadow、depth、opaque、transparent、SSAO、Bloom、UI 等 pass 之间存在明确的生产者/消费者关系。资源依赖一旦确定，执行顺序、生命周期、barrier、aliasing 和 debug marker 才有稳定依据。

Forward 的核心是“物体被绘制时完成光照”
   每个 draw 读取 material、light list、shadow 和 object data，fragment shader 直接输出颜色。路径短、透明与 MSAA 友好，但灯光循环、材质 variant 与 overdraw 会随场景复杂度增长。

Deferred 的核心是“先写可见表面，再统一光照”
   G-buffer pass 保存 normal、albedo、roughness、metallic、depth 等表面属性，lighting pass 再在屏幕空间计算光照。它适合大量动态灯和屏幕空间效果，但会增加 attachment 数量、读写带宽和透明 fallback。

Render Graph 把隐式调用顺序提升成资源依赖图
   Pass 声明 reads/writes、执行类型、尺寸和格式，图构建器据此排序、推导 barrier、资源 lifetime、aliasing 与 pass culling。大型渲染器借此把“谁先执行”改成“谁依赖谁”。

GPU-Driven 把可见性与 Draw 参数生成移到 GPU
   Compute 可完成 culling、LOD、compaction 和 indirect argument 生成，CPU 只提供粗粒度场景数据和 pass 调度。它减少 CPU submit 压力，同时引入 compute→graphics 同步、indirect buffer 生命周期和更复杂的 GPU 调试。

Hybrid Ray Tracing 应作为高价值 Pass 插入主光栅路径
   Raster 继续负责主要表面，RT/ray query 负责阴影、反射、AO 或局部 GI，再输出与原 lighting/postprocess 兼容的中间资源。关键是 AS 更新、ray budget、denoise 和 fallback，不是把整条 renderer 一次性替换成 RT。

渲染系统应分成场景采集、可见性、Pass 构建、后端提交和工具观测五层
   场景采集输出 frame data；可见性生成 renderable list；pass 构建生成 frame plan；后端把逻辑状态映射到 Vulkan/D3D12/Metal/WebGPU/OpenGL；工具层记录 marker、GPU timestamp、资源尺寸、pipeline variant 和内存峰值。

Pass Interface 应以资源契约为核心
   一个 pass 至少需要名称、执行类型、读资源、写资源、pipeline key、viewport/attachment 约定和 profiling scope。Pass 内部只负责自己的 GPU 工作，不应私自修改未声明的全局资源状态。

平台差异应收敛到 Platform Profile
   Vulkan layout/access、D3D12 resource state、Metal encoder/resource usage、WebGPU usage/limit 等后端差异，应映射为引擎统一的 ``ColorAttachmentWrite``、``ShaderRead``、``StorageWrite``、``CopySrc``、``Present`` 等访问语义，而不是散落成大量平台宏。

Shader、格式和能力也应由 Profile 驱动
   HDR format、MSAA、compute queue、timestamp、RT、mesh shader、bindless、tile-based 优化等能力应在启动时归一化。Frame plan 根据 profile 选择路径，缺失能力时使用 SSR→probe、GPU culling→CPU culling 等可解释 fallback。

通用性不是免费抽象
   Render Graph 构建、资源声明、pipeline variant、后端映射和 debug instrumentation 都有 CPU/内存成本。抽象是否值得，要用 graph build time、pass/resource 数量、barrier 数量、command recording、GPU timing 和显存峰值验证。

优化应以 Frame 证据而非架构偏好为准
   小项目可能固定顺序更低成本；大型项目可能从 graph lifetime、pass culling、parallel recording 和自动同步获益。真正的选择标准是画质目标、团队维护成本、平台覆盖和实测 CPU/GPU 预算。

关键路径
--------

Frame 组织：

::

   scene systems
   → frame render input
   → visibility / LOD / sorting
   → pass declarations
   → resource dependency graph
   → physical resource allocation / barriers
   → backend command recording
   → queue submit
   → present

典型城市帧：

::

   shadow map
   → opaque/depth
   → depth + HDR/G-buffer
   → SSAO / lighting / SSR
   → transparent
   → bloom / tone mapping
   → UI / debug overlay
   → present

平台适配：

::

   query platform/device capabilities
   → build PlatformProfile
   → choose render path / formats / features
   → generate FramePlan
   → backend maps logical access to API states
   → capture timing / resource / barrier evidence
   → adjust profile or quality tier

概念辨析
--------

* **Render Pipeline 与 Graphics API**：前者决定一帧如何组织，后者提供资源、状态、命令和同步执行接口。
* **Pass 顺序 与 Resource Dependency**：顺序是执行结果，依赖才是可推导的原因；Render Graph 应以依赖为主。
* **Forward 与 Deferred**：一个在物体 draw 中完成光照，一个把表面属性与屏幕空间光照拆开。
* **Render Graph 与 Renderer Backend**：graph 描述逻辑 pass/resource，backend 负责映射到实际 API 对象和命令。
* **GPU-Driven 与 GPU-Bound**：GPU-driven 描述 CPU/GPU 分工方式，不代表程序一定受 GPU 性能限制。
* **通用抽象 与 平台专用优化**：统一模型负责正确性和可维护性，后端仍可在 profile 允许时使用 tile、async compute、vendor extension 等专用路径。

本章结论
--------

渲染架构应按“Frame Input—Visibility—Pass—Resource Graph—Backend—Evidence”理解。选择 Forward、Deferred、GPU-driven 或 Hybrid RT 前，先画出真实 pass 和资源依赖，再检查平台能力与预算。可扩展 renderer 的关键不是拥有最多模式，而是每个 pass 为什么存在、读写什么、在哪个平台启用、失败时如何降级、最终成本如何被工具证明都清晰可推导。