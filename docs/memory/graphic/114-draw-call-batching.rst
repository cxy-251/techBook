第114章：Draw Call Batching
===========================

核心知识点
----------

Draw Call 的成本不只在“画一次”
   一条 draw 依赖当前 pipeline、vertex/index buffer、descriptor/bind group、constant、texture、render target、viewport、blend、depth/stencil 等状态。大量短 draw 会放大 CPU 命令组织、状态切换和驱动/runtime 工作。

先确认瓶颈是否真的在 Submit
   高 draw count 只有在 CPU render thread、command recording、validation、resource binding 或 pipeline switch 明显占用预算时，batching 才是优先优化。若 GPU 已被 fragment、overdraw 或带宽压满，减少 draw 的收益可能有限。

Batching 的目标是增大一次提交承载的工作量
   静态合并、动态批处理、instancing、multi-draw/indirect 和状态排序都在减少命令数量或重状态切换，但它们改变的资源、culling 粒度和数据更新成本不同。

静态批处理适合长期稳定对象
   在导入/加载阶段合并 mesh 可以减少 draw 与状态切换，代价是 culling 粒度变粗、局部更新困难和额外顶点副本。远景建筑块、固定装饰更适合这种策略。

动态批处理用 CPU 数据整理换 Draw 数
   每帧把小几何写入 transient buffer 能减少提交，但增加 CPU transform、buffer update 和同步。顶点多或对象变化复杂时，合并成本可能高于节省的 draw 成本。

Instancing 适合同 Mesh/同 Pipeline 的重复对象
   一次 draw 用 ``instanceCount`` 绘制多个实例，transform、颜色、material index 等差异通过 instance buffer 提供。路灯、草、石头、重复道具是典型目标。

Per-Instance Data 要保持紧凑与可流式更新
   Instance buffer 应按当前 shader 实际需要保存 transform/index/少量参数，使用 ring/persistent upload 等稳定路径，避免每帧分配和 CPU-GPU 冲突。

Instancing 不等于自动解决材质碎片
   实例若使用完全不同的纹理、shader variant、blend/depth state，仍无法形成单一兼容 batch。可通过 texture array/atlas、bindless/material table 把差异压缩为索引。

Batch Key 决定正确性与合并率
   Key 至少要覆盖 pass、pipeline、render state、material/resource layout、mesh layout 等真正影响兼容性的字段。Key 太粗会合并错误，太细则每个对象仍形成独立 bucket。

Pipeline State Sorting 是最低风险优化之一
   Opaque 可优先按 pass→pipeline→material→mesh 排序，减少 pipeline/descriptor/texture 切换并改善命令连续性。Shadow/depth pass 可使用更简化的专用排序规则。

Transparent Sorting 首先服从视觉顺序
   透明物体往往需要按深度和 blend 语义排序，只能在不破坏混合正确性的局部范围内做材质/状态聚合。不能为了减少 bind 而破坏透明顺序。

Culling Granularity 是批处理的重要代价
   一个 batch 过大时，即使只有少量实例可见，也可能提交整块几何或整组实例。批处理应和空间 chunk、GPU culling、instance compaction 等机制共同设计。

GPU-Driven/Indirect 是批处理的进一步发展
   Compute 可生成可见实例列表、draw count 和 indirect argument，让 CPU 不再逐对象发命令。它降低 CPU submit，但新增 compaction、barrier 和 indirect buffer 管理成本。

评估必须同时看 CPU、GPU、带宽和画面
   关键指标包括 draw count、pipeline/bind count、render-thread time、command recording、GPU pass time、instance buffer bytes、culling efficiency、overdraw 和最终 P95/P99。

关键路径
--------

普通提交：

::

   visible objects
   → build sort key
   → bind pipeline/resources
   → record draw
   → repeat thousands of times
   → queue submit

批处理：

::

   visible objects
   → group by compatible batch key
   → static merge / instancing / material grouping
   → compact per-instance data
   → state sort
   → few large draws or indirect draws
   → queue submit

评估：

::

   baseline draw/state counts
   → CPU render-thread time
   → apply batching
   → verify culling and transparency
   → compare GPU time / bandwidth
   → compare total frame and percentiles

概念辨析
--------

* **Batching 与 Instancing**：batching 是减少提交粒度的总策略，instancing 是同几何多实例的一种具体实现。
* **Static Batch 与 Dynamic Batch**：前者把合并成本前移到加载阶段，后者每帧重新组织数据。
* **Draw Count 与 State Change Count**：draw 少不代表状态切换少；两者都应独立统计。
* **Instancing 与 Bindless**：instancing解决几何重复，bindless/material table解决资源差异；二者常结合使用。
* **Batch Size 与 Culling Precision**：batch 越大提交越少，但独立剔除能力通常越弱。
* **Opaque Sorting 与 Transparent Sorting**：不透明优先状态/深度效率，透明首先保证混合顺序。

本章结论
--------

Draw Call Batching 应按“Submit Bottleneck—Compatibility Key—Batch/Instance Data—State Sorting—Culling—Evidence”理解。先证明 CPU 提交和状态切换是主要问题，再选择静态合并、instancing、material grouping 或 GPU-driven indirect。减少 draw 只是手段，真正目标是让 CPU 命令流更连续，同时不把成本转移成更差的 culling、带宽或视觉错误。