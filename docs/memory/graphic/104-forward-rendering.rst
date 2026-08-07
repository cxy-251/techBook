第104章：Forward Rendering
=========================

核心知识点
----------

Forward Rendering 在 Draw 时直接完成材质与光照
   每个可见物体进入自己的 material pipeline，vertex shader 处理几何，fragment shader 读取 material、light list、shadow、environment 和 object data，直接写入 color/depth target。最终颜色在物体 draw 内形成。

Forward 的主要优势是数据路径短
   Mesh→Material→Light/Shadow→Fragment→Color 的关系直接，工具中容易从具体 draw 追踪 shader、纹理、灯光和 render target。透明材质、粒子、玻璃和 MSAA 也更自然地接入同一条路径。

Light List 决定 Forward 的扩展性
   让 fragment shader 遍历所有全局灯光会快速放大 ALU、shadow sampling 和分支成本。稳定实现应把灯光收敛到 object、tile 或 cluster 级列表，让每个片元只处理局部相关光源。

方向光与局部光适合分层管理
   少量主方向光可作为全局输入；点光、聚光等局部光进入 tiled/clustered 或 object light list。工程指标应记录平均/最大 light count、异常 cluster、阴影灯数量和 light buffer 带宽。

Material Parameter 与 Shader Variant 必须分开
   Base color、roughness、metallic 等数值属于运行时数据；skinning、alpha test、transparent、normal map、receive shadow 等真正改变 shader/PSO 结构的条件才进入 variant。否则 Forward 很容易产生 permutation 爆炸。

Shadow 成本会乘到有效光源上
   Forward shader 的 light loop 内若每盏灯都做 shadow lookup，成本会随灯光数量和过滤质量直接增长。动态阴影应只给主光或高价值灯，其他灯使用无阴影、烘焙或简化路径。

Depth Prepass 是可选优化，不是固定步骤
   它先写不透明深度，帮助昂贵 fragment shader 利用 early depth，适合高分辨率、overdraw 高、pixel shader 重的场景；顶点成本高或 overdraw 低时，它可能只增加额外 draw 和 vertex work。

不透明排序和透明排序目标不同
   Opaque 通常优先减少 pipeline/material 切换并利用深度；Transparent 通常必须服从距离、blend 语义和特殊材质规则。统一按材质排序透明物体会破坏视觉正确性。

MSAA 是 Forward 的典型优势
   Forward 可以直接把材质着色写入 multisample color/depth target，几何边缘质量好，尤其适合 VR 和需要稳定几何抗锯齿的场景。代价是 sample storage、resolve、sample shading 和透明特殊路径。

Forward+ / Clustered Forward 是灯光扩展手段
   它们保留 Forward 的材质直接着色路径，只把 light assignment 前移到 compute/tile/cluster 阶段。这样能支持更多动态灯，同时避免 Deferred 的大规模 G-buffer。

Transparent Pass 常是 Forward 的独立性能热点
   透明物体依赖 blend、深度读取、排序，通常不能依靠早期深度完全消除 overdraw。粒子、玻璃和大面积半透明覆盖会让 fragment 与 blend bandwidth 成为主要瓶颈。

移动端与 VR 是 Forward 的典型适用场景
   Tile-based GPU 对多 render target 和外部内存带宽敏感，Forward 可减少中间 attachment；VR 需要高刷新率和 MSAA，透明比例也常较高。成立前提仍是 light list、shadow 和 shader variant 被严格预算。

Forward 性能应按 Pass→Light→Shader→Bandwidth 分析
   先看 CPU draw/PSO switch，再看 depth prepass 和 opaque GPU 时间，然后检查 light list、shadow sampling、texture/ALU，最后看 transparent overdraw、MSAA resolve 和 postprocess。

Frame Profile 应把架构约束显式化
   目标分辨率、刷新率、MSAA、最大局部灯数量、最大阴影灯、透明策略、材质 feature 上限、平台能力和 fallback 应成为可配置 profile，而不是散落在 shader 和 pass 中。

关键路径
--------

Forward Frame：

::

   scene culling
   → build light lists
   → sort opaque / transparent
   → shadow passes
   → optional depth prepass
   → opaque forward pass
   → MSAA color + depth
   → transparent forward pass
   → resolve
   → post process
   → present

单个 Draw：

::

   mesh + object constants
   → material variant
   → material resources
   → local light list
   → shadow data
   → vertex shader
   → fragment BRDF/light loop
   → depth/blend
   → color target

性能定位：

::

   CPU draw count / pipeline switches
   → depth prepass benefit
   → opaque GPU time
   → average/max light list length
   → shadow samples / material texture samples
   → transparent overdraw
   → MSAA resolve / postprocess

概念辨析
--------

* **Forward 与 Forward+**：Forward+ 仍是前向着色，只是通过 tile/cluster 预先生成局部 light list。
* **Material 与 Pipeline Variant**：材质包含大量运行时参数，variant 只描述会改变 shader/pipeline 结构的有限开关。
* **Depth Prepass 与 Early-Z**：prepass 主动先写深度，early-Z 是 GPU 在后续 draw 中利用已有深度提前拒绝片元的机制。
* **MSAA 与 Supersampling**：MSAA 重点提高几何覆盖采样，不等于整套 shader 在更高完整分辨率执行。
* **Opaque Sorting 与 Transparent Sorting**：前者偏向状态和深度效率，后者首先服从视觉混合顺序。
* **灯光数量 与 实际 Light Loop 长度**：全场景灯数量不是直接成本，局部 light list 长度才更接近当前片元的实际光照工作量。

本章结论
--------

Forward Rendering 应按“Visibility—Light Assignment—Material Variant—Draw—Fragment Lighting—Color/Depth”理解。灯光多时先收敛 light list，像素重时再判断 depth prepass，透明重时检查 overdraw，VR/移动端则同时预算 MSAA 与带宽。Forward 的价值来自直接、透明友好和较少中间资源；它是否高效，取决于灯光、阴影、variant、透明和 sample 成本是否被明确限制。