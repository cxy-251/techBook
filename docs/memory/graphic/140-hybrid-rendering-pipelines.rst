第140章：混合渲染管线
====================

核心知识点
----------

Hybrid Rendering 的设计单位是 Frame Graph，而不是单个算法
   Raster、ray tracing、neural inference、denoise、upscale、post-process 和 fallback 必须共享同一组资源、时间关系和帧预算。任何一个 pass 单独正确，都不能保证组合后正确。

Raster Pass 负责提供稳定几何与材质约束
   Base color、depth、normal、roughness、material id、motion vector 等 G-buffer/feature 是 ray tracing、denoising 和 upscaling 的共同输入。它们的 camera、jitter、resolution、space 与 encoding 必须一致。

Ray Tracing 适合补充高价值、难用 Raster 准确解决的效果
   Reflection、shadow、GI、AO 等可按预算选择性追踪。Hybrid 管线通常不会让 ray tracing 替代全部 raster，而是把 ray budget 放在视觉收益最高的位置。

Neural Pass 的输入质量由 Classical Pass 决定
   Denoiser/upscaler 依赖 depth、normal、motion、roughness、exposure、reactive mask 与 history。模型无法自动修正错误 motion vector 或失配的 G-buffer，它只会把错误带入重建。

History Buffer 是混合管线最敏感的跨帧资源
   Reflection history、color history、feature history 都需要 motion reprojection、depth/normal/material validation 与 disocclusion 处理。Camera cut、resize、render-scale change、model change 都可能要求 reset。

Cache 与 History 的有效性必须有证据
   上一帧数据能否复用，取决于当前像素是否仍属于同一表面和同一材质语义。History 不能因为“有上一帧 texture”就默认有效。

Denoising 负责随机采样噪声，Upscaling 负责像素预算
   两者常都使用 temporal history，因此顺序与输入语义必须明确。Denoiser 输出通常先参与 lighting/composite，再由 upscaler 重建目标分辨率。

Reactive/Disocclusion Mask 是 Temporal 重建的重要控制输入
   透明、粒子、动画纹理、快速反射和新暴露区域需要减少 history 权重。Mask 错误会同时放大 denoiser 和 upscaler 的拖影。

资源生命周期必须覆盖 Neural Temporary Tensor
   Model weights、intermediate tensor、history feature 与传统 RT/G-buffer 同时占用显存。Frame graph 应明确 transient、persistent、aliasable 与跨帧资源，才能控制 peak memory。

Fallback Path 应与高端路径共用输出契约
   RT reflection 可降为半分辨率、低 ray count、SSR/probe；neural denoiser 可降为轻量模型或传统 filter；upscaler 可降档或切传统 temporal upscale。Fallback 不应迫使后续 post-process 重写接口。

质量降级要有梯度而不是单一开关
   一般先降低高成本局部效果，再降低模型档位，再降低主分辨率。降级顺序应依据用户能否感知、对交互是否关键以及每一步能节省多少毫秒。

每个 Pass 都应声明 Input、Output 与 Evidence
   Input 决定它能做什么，output 决定下游依赖，evidence 决定调试方式。没有 marker、timestamp、resource name、history id 的高级 pass 很难维护。

Performance 需要拆成真实 GPU 时间线
   至少分别测 raster base、AS/update、ray tracing、denoiser、composite、upscaler、post-process 与 present wait。平均 FPS 无法告诉你是哪一段超预算。

Inference Cost 不只包含模型执行
   Feature preparation、layout conversion、resource barrier、queue sync、temporary allocation、model cache miss 都属于 neural path 成本。推理本体 1ms 不代表整个神经阶段只花 1ms。

Memory Footprint 是独立约束
   RT acceleration structure、G-buffer、history、模型权重和 tensor 可能一起制造显存峰值。性能稳定但显存压力导致 eviction/stutter，同样属于混合管线失败。

Latency 与 Frame Time 需要同时观察
   游戏和交互工具还要关注输入到显示的延迟。Queue 过深、异步 pass 交接和 heavy refine 即使不显著降低平均 FPS，也可能增加交互迟滞。

质量指标必须与具体效果匹配
   Reflection 检查边缘、粗糙表面、动态遮挡与 temporal stability；upscaling 检查细线、透明、运动和 UI；denoising 检查残余噪声、overblur 与 ghosting。单一图像指标不能覆盖全部故障。

调优应记录“成本收益表”
   每次改动都要说明哪个 pass 变了、节省多少 GPU/内存、引入哪些质量风险、在哪些平台触发 fallback。否则高级技术叠加后会失去维护依据。

不同应用的优先级不同
   游戏优先稳定帧预算和输入响应；影视/设计预览优先尽快得到可判断的渐进结果；云渲染还要加入编码、网络和端到端 latency。Hybrid 架构必须围绕最终产品的关键路径调度。

关键路径
--------

典型 Hybrid Frame：

::

   scene + camera
   → raster base
   → G-buffer / low-res color
   → acceleration structure / ray effect
   → noisy radiance
   → neural or traditional denoise
   → lighting composite
   → neural / temporal upscale
   → tone map / post / UI
   → present
   → write histories for next frame

History 验证：

::

   previous history
   → motion reprojection
   → depth / normal / material check
   → disocclusion / reactive mask
   → confidence
   → accept, clamp, or reject history

性能调优：

::

   capture fixed scene
   → timestamp every pass
   → measure peak memory + sync
   → locate longest degradable stage
   → lower ray/model/resolution quality
   → compare visual failure
   → record threshold and fallback

概念辨析
--------

* **Hybrid Rendering 与 Full Ray Tracing**：前者有意组合多种方法，后者把更多主路径交给 ray tracing。
* **Classical Constraint 与 Neural Reconstruction**：传统 pass 提供几何/运动事实，神经 pass 根据这些事实恢复缺失信息。
* **History Buffer 与 Cache**：history 专门连接帧间重建，cache 更泛化地复用数据或结果。
* **Denoising 与 Upscaling**：前者主要解决采样方差，后者主要解决空间分辨率；二者可能共享 temporal feature。
* **Quality Fallback 与 Error Recovery**：fallback 是受控性能/能力降级，error recovery 是执行失败后的恢复路径。
* **Pass Time 与 End-to-End Latency**：pass time 是局部 GPU 成本，端到端延迟还包含 CPU、queue、present 和显示。

本章结论
--------

混合渲染应按“Classical Constraints—Ray Effect—Neural Reconstruction—History—Composite—Upscale—Present—Fallback”理解。稳定架构的关键是让所有高级 pass 使用同一套 camera、resource、motion 与时间语义，并用 frame graph 明确依赖和生命周期。优化时只接受能被 GPU 时间线、显存峰值和质量指标共同证明的改动，并始终保留可控降级路径。