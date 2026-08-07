第111章：Compute-Driven Rendering
================================

核心知识点
----------

Compute-Driven Rendering 把渲染决策放到 GPU
   可见性判断、LOD 选择、实例筛选、粒子更新、命令计数和 indirect argument 由 compute pass 生成，graphics pass 只消费这些结果完成光栅化。

它的主要收益是降低 CPU Traversal 与 Draw Submission
   对象数量很高时，CPU 逐对象 culling、排序和发 draw 会形成固定开销。GPU 并行筛选后，只需少量 dispatch 和 indirect draw，CPU 提交成本随对象数量增长得更慢。

收益成立的前提是场景数据已经常驻 GPU
   Bounds、transform、mesh metadata、material index、depth pyramid 等若本来就在 GPU，compute 可以直接复用。若每帧还要先上传大量对象状态，GPU-driven 的优势会被 upload 抵消。

GPU Scene Data 应按消费方组织
   Culling 只需要 bounds/transform，LOD 需要 bounds/mesh metadata，draw generation 才需要 mesh/material range。将所有字段塞进一个巨大结构会放大不必要带宽。

Visibility Buffer 在这里指“当前帧可见对象列表”
   Compute 先对对象做 frustum/occlusion/LOD 判断，再输出 object id、LOD id、mesh id、material id 等记录。它和 Deferred 中按像素记录 primitive/material 的 visibility buffer 不是同一概念。

Compaction 把稀疏结果变成紧凑工作集
   Culling 后只有少量对象有效。Atomic append 实现简单，scan/prefix-sum 更适合高吞吐和稳定布局。后续 pass 应只遍历 compacted list，而不是再次扫描所有对象。

Indirect Command 是 Compute 与 Graphics 的正式接口
   DrawIndexedIndirect 等记录必须严格匹配目标 API 的字段、stride、对齐和 count 规则。``firstInstance`` 或同类字段常用于让 shader 找回 visible object/material 数据。

GPU 生成 Draw 参数不等于自动解决状态切换
   如果材质、pipeline、descriptor 仍极度碎片化，graphics pass 仍需要分 bin 或使用 bindless/material table。Compute-driven 路径通常还要生成 material/pipeline bin 或按 mesh/material 聚合命令。

Barrier 是 Compute → Indirect/Graphics 的关键边
   Compute 写 visible list、draw count 和 indirect buffer 后，graphics 必须在读取前看到完整写入。Vulkan/D3D12/Metal/WebGPU 的状态名不同，但本质都是 producer write → consumer indirect/vertex/shader read。

最稳妥的第一版使用同一 Queue 顺序执行
   Compute culling → barrier → indirect raster 易于验证。只有在存在真实重叠空间后，再把部分 simulation、远景更新、light list 或粒子工作迁入 async compute。

Async Compute 的价值来自真实 Overlap
   如果当前帧主相机 culling 的结果马上被 raster 消费，它几乎处在关键路径上，重叠空间有限。允许上一帧结果、延迟消费或和 graphics 使用不同热点资源的任务更适合异步。

关键路径与可延迟路径应分开
   主相机 culling/indirect draw 通常要求同帧；粒子、远景 impostor、部分阴影级联、统计等可以分帧或延迟。这样可以减少主 raster 前的大量硬同步。

Fallback 必须保留 CPU/简化提交路径
   平台可能缺少 indirect count、bindless 或高效 UAV 写；低端 GPU 也可能不适合复杂 compaction。可退回 CPU culling、固定最大 draw count、instancing 或分批 indirect。

性能评估必须同时算收益和新增成本
   收益看 CPU traversal、draw submit、readback/upload 减少；新增成本看 bounds/depth pyramid 读取、compaction、atomic/scan、barrier、indirect buffer、额外显存和调试复杂度。

对象数量与剔除比例决定收益曲线
   小场景中 compute+barrier+indirect 的固定成本可能高于 CPU 直接提交；对象几十万且大部分不可见时，GPU culling/compaction 更容易覆盖新增成本。

关键路径
--------

GPU-Driven Frame：

::

   CPU updates camera/global constants
   → GPU scene buffers
   → compute frustum/occlusion culling
   → LOD selection
   → compaction
   → material/mesh binning
   → build indirect commands + count
   → barrier
   → graphics indirect draws
   → color/depth

调试路径：

::

   expected visible object count
   → visible counter
   → visible object records
   → LOD/material/mesh ids
   → indirect command fields
   → barrier/resource state
   → draw event + firstInstance/object lookup
   → final image

性能评估：

::

   CPU traversal/submit before
   → compute culling time
   → compaction/command generation time
   → barrier/queue idle
   → indirect raster time
   → memory footprint
   → compare total frame + P95/P99

概念辨析
--------

* **GPU Culling 与 Indirect Draw**：前者决定哪些对象可见，后者让 GPU buffer 中的参数直接驱动 draw；二者可独立存在。
* **Visible List 与 Draw Command Buffer**：visible list 保存对象/LOD 等语义，command buffer 保存 API 可执行的绘制参数。
* **Atomic Append 与 Prefix-Sum Compaction**：前者简单但可能竞争，后者阶段更多但更适合大规模紧凑输出。
* **Compute-Driven 与 Mesh Shader**：前者以 compute+indirect 驱动传统 graphics pipeline，mesh shader 把 meshlet culling/生成进一步移入几何前端。
* **Async Compute 与 GPU-Driven**：GPU-driven 描述谁产生渲染决策，async compute 描述队列调度方式，不是同一概念。
* **CPU Bottleneck 与 GPU-Driven 收益**：只有 CPU 对象遍历/提交真的占预算时，把工作迁到 GPU 才有明确收益来源。

本章结论
--------

Compute-Driven Rendering 应按“GPU Scene Data—Culling—LOD—Compaction—Indirect Contract—Barrier—Raster”理解。对象缺失先查 visible list 与 command buffer，随机 draw 错误查字段布局、资源版本和 barrier；性能优化则必须比较 CPU 节省与 compute/带宽/同步新增成本。GPU-driven 的核心不是让 GPU 做更多工作，而是让高频对象级决策和命令数据在 GPU 内形成闭环。