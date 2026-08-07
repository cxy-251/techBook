第147章：AI 加速渲染
===================

核心知识点
----------

AI Accelerated Rendering 的工程本质是用推理替代一部分昂贵渲染成本
   模型可以用于超分、降噪、帧生成、材质生成、动画辅助、场景重建和内容压缩。判断价值时要明确它替代了哪一段传统计算、节省了多少成本，并比较新增 inference、history、memory 和同步开销。

AI 模块首先是 Frame Graph 中的一个 Pass
   它必须有明确的输入 buffer、输出资源、颜色空间、分辨率、时间语义和资源状态。模型名称和离线指标不能替代运行时契约。

超分的收益来自降低前半帧像素成本
   主渲染、G-buffer、lighting、ray tracing 等可以在较低 internal resolution 下执行，再由模型结合 color、depth、motion、jitter、exposure、history 重建目标分辨率。收益成立的前提是节省的主渲染时间大于 inference 与同步成本。

AI Denoiser 用学习重建换取更低 Sample Count
   Noisy radiance、albedo、normal、depth、roughness、motion、history 等 feature 共同约束输出。Guide 或 history 错位会把随机噪声转成 ghosting、漏光和过度平滑。

Frame Generation 提高的是 Displayed FPS，不是 Simulation FPS
   生成帧通常根据真实帧、motion vector、optical flow 或引擎运动信息插入中间显示帧。真实输入采样、模拟 tick 与主渲染更新频率不会因此自动提高，因此必须单独评估输入延迟、HUD/UI、透明和遮挡变化。

内容生成模型进入生产管线后要落到稳定资产
   材质生成应输出可验证 PBR/SVBRDF 数据；场景重建应输出可用 geometry/radiance representation；动画模型应遵守 skeleton/retarget contract；压缩模型必须满足 runtime decode、LOD、filtering 和平台要求。

Feature Buffer 是 AI 与图形管线协同的关键
   Depth、normal、roughness、albedo、motion、reactive/transparency mask、exposure 等提供几何、运动和材质语义。模型依赖这些信息越多，引擎越应把它们作为正式资源管理，而不是临时调试输出。

Temporal Input 带来稳定性，也带来历史污染风险
   超分、降噪与帧生成都可能读取 history。Camera cut、disocclusion、render-scale change、exposure jump、UI/particle、透明边界和模型切换必须触发相应的 history invalidation 或 reset。

Offline Training 与 Runtime Inference 是两个不同约束域
   训练阶段决定模型见过什么分布，运行时决定一帧内实际能提供哪些 buffer、精度和时间预算。训练覆盖不代表运行时输入一定符合分布，runtime contract 必须把训练假设显式化。

模型契约必须固定输入输出语义
   至少包括 tensor 尺寸、format、color space、normalization、depth convention、motion unit、history count、precision、output range、temporary memory 与版本。契约不清会让“模型问题”和“图形输入问题”无法区分。

Inference Runtime 决定模型能否进入 Critical Path
   Compute shader、tensor/matrix unit、NPU 或平台 ML runtime 的吞吐不同，也可能需要 layout conversion、queue ownership、resource copy 和 fence。推理本体很快，不代表整个 AI stage 很快。

Fallback 是 AI 集成的正式组成部分
   模型加载失败、硬件不支持、输入缺失、memory 超限、quality probe 失败或 latency 超预算时，应能切到传统 TAAU、传统 denoiser、原生渲染、较低模型档位或关闭 frame generation。

Capability Tier 应屏蔽厂商差异
   不同 GPU/平台可能提供不同超分、denoiser、frame generation、ML runtime 和矩阵硬件。引擎应把这些能力映射成内部 tier，而不是让主渲染逻辑直接依赖厂商名称。

性能评估必须同时计算收益与新增成本
   需要记录 native path、traditional reconstruction、AI path 三组基线，并比较 CPU/GPU frame、inference latency、memory、history footprint、queue wait、present pacing、功耗和最终质量。

Temporal Stability 是 AI 渲染的核心质量指标
   单帧 PSNR/SSIM 好并不代表动态画面可用。细线、粒子、透明、反射、disocclusion、快速相机和 UI 是最容易暴露 ghosting、flicker、lag 和 hallucination 的区域。

帧生成需要报告两套帧率
   Real rendered FPS 与 displayed/generated FPS 必须分开，同时记录 input-to-photon、generated-frame latency、掉帧恢复和 UI composition。只报更高显示帧率会掩盖交互成本。

AI 渲染的长期趋势是从单一 Upscaler 走向一组 Neural Runtime Contracts
   超分、ray reconstruction、denoising、frame generation、neural material、radiance cache 会共享 motion、depth、history、feature 和 capability 管理。渲染器需要统一管理这些神经 pass，而不是逐个 SDK 拼接。

关键路径
--------

运行时 AI Pass：

::

   low-cost render / noisy signal
   → feature buffers
   → history validation
   → model input packing
   → inference runtime
   → reconstructed output
   → quality probe
   → post-process / present
   → update history

集成流程：

::

   define model contract
   → map frame graph resources
   → select inference backend
   → allocate weights/temp/history
   → schedule pass and synchronization
   → install fallback
   → validate quality scenes
   → profile end-to-end cost

性能比较：

::

   native high-quality path
   → traditional reconstruction baseline
   → AI reconstruction path
   → compare GPU saved time
   → subtract inference/sync/memory cost
   → inspect temporal artifacts and latency
   → choose capability tier

概念辨析
--------

* **AI Acceleration 与 AI Image Generation**：前者服务明确的实时渲染输入输出，后者可以独立生成图像。
* **Displayed FPS 与 Rendered FPS**：帧生成能提高显示帧数，主模拟和真实渲染频率仍需单独观察。
* **Model Latency 与 AI Stage Latency**：后者还包含 feature preparation、layout conversion、copy 与 synchronization。
* **Training Quality 与 Runtime Quality**：训练指标只覆盖数据集，运行时还受引擎输入、history 和平台路径影响。
* **Feature Buffer 与 Ground Truth**：feature 是运行时辅助输入，ground truth 是训练/验证参考。
* **Vendor SDK 与 Engine Capability Tier**：SDK 是具体实现，tier 是引擎用来统一选择和降级的内部能力模型。

本章结论
--------

AI 加速渲染应按“Traditional Cost—Feature/History—Model Contract—Inference Runtime—Output Validation—Latency/Memory—Fallback”理解。有效的 AI pass 必须证明它真正缩短整帧关键路径，而不是只展示模型输出；同时要让输入语义、历史有效性、平台能力和降级策略可观察、可验证、可替换。