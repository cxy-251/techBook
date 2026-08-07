第123章：框架集成策略
====================

核心知识点
----------

统一框架的目标是让一帧跨模块可追踪
   Platform、RHI、Backend、Render Graph、Resource System、Shader Compiler、Pipeline Cache、Debug/Profiling 共同完成 frame。集成质量取决于这些模块是否共享同一套 resource、pipeline、capability 和 diagnostic 契约。

Platform Layer 与 GPU 执行层应分离
   Platform 负责窗口、surface、输入、文件、线程和平台扩展入口；RHI/Backend 负责 device、queue、swapchain、resource、pipeline、command、barrier 与 present。Resize、surface loss 等平台事件通过统一 surface/frame context 进入渲染层。

RHI Frontend 是最稳定的框架边界
   功能代码只使用 ``RhiDevice``、``TextureHandle``、``PipelineHandle``、``CommandList``、``Fence`` 等抽象对象；VkImage、ID3D12Resource、MTLTexture、GPUTexture 等原生对象只存在于 backend。

Render Graph 负责一帧的依赖组织
   Pass declaration 形成资源读写图，graph compile 推导执行顺序、transient lifetime、barrier、aliasing 和可选 pass culling。它输出的是统一 transition plan，不直接写 Vulkan/D3D/Metal 原生命令。

Resource System 负责生命周期与状态
   Texture/buffer 创建、view、owner、state、frame lifetime、release fence、memory report 都应进入 resource tracker。Render Graph 和 Debug/Profiling 都读取同一份资源记录。

Shader Compiler 是资源绑定翻译器
   Source、entry、variant、reflection、binding layout 和 diagnostics 最终影响 pipeline layout、descriptor/root signature、argument buffer/bind group。Shader 与 resource system 必须共享统一 binding schema。

Pipeline Cache Key 必须覆盖 Shader 与固定状态
   Shader binary、reflection/layout、render target format、depth/blend/raster、sample count、backend capability 等改变时，pipeline cache 都需要生成不同 key。Cache miss 应被统计并可追踪到具体 pass/variant。

Debug/Profiling 必须从框架初期接入
   Resource name、pipeline name、pass marker、GPU timestamp、barrier count、memory usage、cache hit、validation message 等元数据应随对象和 command 流动。后补工具系统通常无法反查匿名对象和合并后的 pass。

Backend Plugin 是 RHI 契约的具体实现包
   一个 backend 至少包含 adapter/device、swapchain、allocator、command encoder、pipeline builder、binding/descriptor、barrier translator、shader loader 和 diagnostics。Plugin registry 决定当前平台使用哪个实现。

Capability Query 应发生在 Device 创建和路径选择前
   Compute、storage texture、timestamp、descriptor indexing、async compute、MSAA、RT、mesh shader 等都应形成结构化 capability table。Shader compiler、render graph、resource system 和 quality system 必须读取同一份事实。

Capability 需要区分三层来源
   Hardware/driver capability、API/backend capability、project policy 不应混成一个布尔值。某功能关闭必须能解释是设备不支持、后端未实现，还是产品策略主动禁用。

Extension Point 应传框架语义而非原生对象
   Backend registration、shader include resolver、resource allocator policy、render-pass injection、statistics exporter、capture hook 等扩展应优先接收统一 handle/context。真正需要 native handle 时，通过受控 query 暴露，并明确 backend 与生命周期。

Fallback Contract 必须可测试
   Bloom 可有 compute、fragment 和 disabled 三条路径；每条 path 都应对应 capability 条件、资源 contract、shader variant、golden image 和性能预算。运行时选择结果写入 frame statistics。

测试矩阵应覆盖“会改变数据路径”的分支
   Platform、backend、adapter class、shader target、swapchain format、MSAA、compute、timestamp、fallback、capture tool 等构成最小矩阵。目标不是穷举设备，而是覆盖不同资源/同步/绑定路径。

资源、管线和工具应通过统一 ID 协作
   某个 G-buffer normal 错误应能从 lighting pass marker → input view → resource handle → writer pass → barrier → shader binding → backend descriptor 逐级反查。

统一统计应服务瓶颈归因
   CPU submit、GPU pass time、draw/dispatch、barrier、descriptor update、pipeline cache hit/miss、transient peak、persistent memory、swapchain latency、fallback path 等指标应按 frame id 汇总。

多设备支持必须进入调度模型
   每个 pass 需要 device affinity、queue requirement、resource ownership 和 presentation dependency。跨 GPU copy、queue sync、frame pacing 与 output merge 都应在 graph/scheduler 中显式表达。

Multi-Device 是受控优化路径，不是默认复杂度
   缺少 async compute、跨设备传输过贵、ownership 无法证明时，应在 graph compile 阶段退回单 queue/单 device，并记录 diagnostics，而不是在 command recording 阶段临时补救。

成熟框架的共同特征是协作面稳定
   Backend 负责 API 映射，Shader 负责源码/变体/反射，Resource 负责生命周期和状态，Pass/Graph 负责一帧组织，Tooling 负责证据。任一边界断裂，所谓统一框架都会退化成隐藏复杂度的包装层。

关键路径
--------

框架 Frame：

::

   application/platform event
   → surface/frame context
   → render graph pass declarations
   → resource allocation + shader/pipeline lookup
   → RHI frontend commands
   → backend mapping
   → graphics/compute/copy queues
   → present
   → debug/profiling statistics

Backend 选择与降级：

::

   enumerate adapters/backends
   → query hardware/API capabilities
   → apply project policy
   → choose BackendPlugin
   → compile feature profile
   → choose render/shader/resource paths
   → record fallback path
   → execute test matrix

故障定位：

::

   visual/performance symptom
   → pass marker
   → shader/pipeline id
   → resource/view id
   → render graph dependency/barrier
   → backend object/validation
   → frame statistics + capture
   → fix owning module

概念辨析
--------

* **Platform Layer 与 Backend**：Platform 管窗口/系统服务，Backend 管具体图形 API 实现。
* **RHI Frontend 与 Render Graph**：RHI 提供 GPU 对象与命令，Render Graph 组织 pass 和资源依赖。
* **Capability 与 Policy**：Capability 是设备/API 事实，Policy 是项目是否选择使用该能力。
* **Backend Plugin 与 Extension Point**：Plugin 实现整套 API backend，extension point 允许局部模块插入策略或工具。
* **Pipeline Cache 与 Shader Cache**：Shader cache 保存编译产物，pipeline cache 保存 shader + layout + fixed state 的可执行组合。
* **Multi-Backend 与 Multi-Device**：前者是同一框架支持多个 API，后者是一帧可能同时使用多个设备。

本章结论
--------

跨 API 框架应按“Platform—Render Graph—RHI—Backend—Resource—Shader/Pipeline—Capability/Fallback—Tooling”理解。真正成熟的集成不是模块越多，而是每个 pass、resource、shader、pipeline 和 backend 都共享稳定 identity、能力事实、生命周期和诊断路径。这样新增平台、后端或高级功能时，改动才能集中在明确边界内，而不是扩散到整条渲染功能代码。