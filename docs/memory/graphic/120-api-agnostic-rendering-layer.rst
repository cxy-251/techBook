第120章：API 无关渲染层
=======================

核心知识点
----------

API-Agnostic Layer 应保留现代 GPU 的显式模型
   跨 API 层不是把所有后端退化成“画三角形”的统一函数，而是统一 device、resource、pipeline、command、barrier、presentation、validation 和 profiling 语义，再由 backend 映射到 Vulkan、D3D12、Metal、WebGPU 等原生对象。

对象分层决定维护成本
   Device 负责能力与对象创建；Resource 表达 buffer/texture/sampler；Pipeline 固化 shader 和 render state；Command 记录 draw/dispatch/copy；Barrier 表达访问依赖；Presentation 处理 acquire、backbuffer、resize 和 present。职责混合会让状态和生命周期无法追踪。

统一 Resource Contract 至少包含六项
   Description、usage flags、memory domain、view、state transition、lifetime ownership 缺一不可。资源若只记录“这是一张 texture”，后续 sampled/storage/render-target 等访问就无法提前验证。

Usage 描述资源整个生命周期允许承担的角色
   ``colorAttachment``、``sampled``、``storage``、``copySrc``、``copyDst`` 等用途通常需要在创建阶段已知。后续 pass 的实际访问必须落在已声明 usage 范围内。

Memory Domain 应从访问方向抽象
   GPU-only、CPU-to-GPU、GPU-to-CPU、transient 是稳定分类。它们可映射到 Vulkan memory type、D3D heap、Metal storage mode、WebGPU map/usage 限制，而不让上层依赖后端专有枚举。

View 是 Resource 与 Pass/Shader 的解释层
   同一 texture 可在不同 pass 中成为 render target view、sampled view、storage view 或特定 mip/slice view。View 必须独立保存 subresource range、format override、access role 和 binding identity。

资源状态应使用统一访问语义
   ``ColorAttachmentWrite``、``ShaderRead``、``StorageWrite``、``CopySrc``、``CopyDst``、``Present`` 等内部状态比直接暴露 Vulkan/D3D 枚举更稳定。Backend 再把它们转换成 layout、resource state、encoder boundary 或 validation rule。

Barrier Planner 应基于 Producer/Consumer 推导
   先确认 usage 合法，再找上一次 writer 和当前 reader/writer，确定 subresource，判断是否跨 queue，最后生成/合并 barrier。业务 pass 只声明读写，planner 负责同步细节。

Per-Subresource State 能减少过宽同步
   Bloom mip chain、array texture、cubemap、depth/stencil 常同时使用不同 mip/layer/aspect。只记录 whole-resource state 会制造不必要 barrier，压缩 GPU 调度空间。

跨 Queue 交接需要状态与时间线同时成立
   Graphics→Compute→Graphics 不只需要资源状态变化，还需要 semaphore/fence/event 或 queue ownership 转移。Barrier 描述访问可见性，队列信号描述执行完成，二者不能互相替代。

Presentation 应作为独立 Contract
   Backbuffer 通常由 swapchain/context 外部拥有，每帧 acquire 后临时作为 render target，最后进入 present 语义。Resize、surface loss、drawable 获取失败和 device lost 都应集中在 presentation/backend 层处理。

统一 Validation 应先于原生 Debug Layer
   引擎能提前发现“storage-only texture 被 sampled”“pipeline attachment format 不匹配”“resource state 与 pass 访问不一致”等错误，并输出统一类别。Backend 原生消息作为补充证据保留。

错误消息必须包含 Frame Context
   Backend、severity、pass name、resource name、pipeline、expected/actual state、source location、frame index 和 native message 应进入同一诊断结构。异步 submit 时出现的错误才能回到录制命令的真实上下文。

跨 API Statistics 是长期观察面
   Draw/dispatch/barrier count、memory usage、pipeline cache hit、descriptor update、pass GPU time、CPU submit 等应按同一字段记录，使 Vulkan、D3D12、Metal、WebGPU 可以直接 A/B 比较。

统计层不替代 Vendor Profiler
   内部统计回答结构和趋势，外部 profiler/capture 解释具体硬件 stall、cache、occupancy 和资源内容。两者通过稳定 pass/resource name 对齐。

关键路径
--------

后处理 Frame：

::

   SceneHDR color write
   → transition to shader read
   → Bloom compute reads SceneHDR
   → BloomOutput storage write
   → transition to shader read
   → Post pass samples BloomOutput
   → BackBuffer color write
   → Present

Barrier Planning：

::

   pass declares read/write
   → validate resource usage
   → locate previous access
   → choose subresource range
   → detect queue handoff
   → generate logical transition
   → backend barrier/event mapping
   → record statistics

错误定位：

::

   validation error
   → pass/command context
   → resource/view contract
   → expected vs actual usage/state
   → backend native message
   → fix declaration or mapping
   → recapture

概念辨析
--------

* **Usage 与 State**：usage 是资源允许承担的长期角色，state 是当前 pass 前后的具体访问语义。
* **Resource 与 View**：resource 是存储对象，view 定义某次访问如何解释这段存储及其 subresource。
* **Barrier 与 Queue Fence**：barrier约束资源访问，fence/semaphore约束执行时间线；跨队列通常两者都需要。
* **Validation 与 Profiling**：validation 判断是否合法，profiling 判断成本是否合理。
* **Transient Resource 与 External Resource**：前者由 frame graph 管理短生命周期，后者如 swapchain/backbuffer 由外部系统拥有。
* **Internal Statistics 与 Vendor Counter**：前者跨平台稳定，后者硬件相关且用于深入解释瓶颈。

本章结论
--------

API 无关渲染层应按“Stable Objects—Resource Contract—State/Barrier—Presentation—Validation—Statistics—Backend Mapping”理解。成功的统一层不是隐藏资源和同步，而是把它们转成跨后端一致、可验证、可统计的协议。这样同一个 frame 才能在不同 API 上得到等价资源路径、错误语义和性能证据。