第037章：Ray Tracing 优化
========================

核心知识点
----------

Ray Tracing 优化应以完整 ray path 为成本单位
   一条 ray 从 generation、TLAS/BLAS traversal、AABB/primitive intersection、hit/miss shader、次级 ray 生成到最终写回，都可能成为瓶颈。只统计 ray 数量或只看 shader 指令都不足以解释完整帧时间。

帧成本可以拆成 ray 数、traversal、shading 与 AS build/update
   近似模型可以写成 ``rayCount × traversalCost + hitCount × hitShaderCost + missCost + buildUpdateCost``。Half-resolution 会直接降低 rayCount；更好 BVH 改 traversal；精简 closest hit 改 shader cost；动态角色 BLAS refit/rebuild 属于 build/update。

BVH 的核心价值是减少 primitive candidate
   Ray 先与 node AABB 相交，再进入可能命中的 child/leaf。树质量由 node overlap、leaf primitive 数、树深、bounds 紧致度与 child ordering 决定。好的 BVH 不是“树越深越好”，而是让常见 ray 尽快排除无关空间。

SAH 用空间概率近似遍历成本
   Surface Area Heuristic 用包围盒表面积与 primitive 数估算 split 后的期望成本。高质量 SAH build 通常构建更慢但 trace 更快；LBVH 等快速构建适合动态或短生命周期对象。构建策略应按对象生命周期和真实 traversal 统计选择。

BLAS/TLAS 把几何更新与场景实例管理分开
   BLAS 组织 mesh/procedural geometry，TLAS 组织 instance、transform、mask 与 BLAS 引用。静态建筑可高质量 build + compaction，动态角色可 refit/周期性 rebuild，TLAS 则按实例变化更新。

Refit 快，但会逐渐损失树质量
   Refit 保持拓扑，仅更新 bounds。大幅骨骼形变后 node overlap 会增加，ray 访问更多 child。工程上应监控 refit 后的 traversal node/primitive tests，在超过阈值时 rebuild，而不是永久 refit。

Ray coherence 决定 GPU 并行效率
   相邻 camera ray 通常相干；粗糙 reflection ray 会快速发散；shadow ray 面向同一光源时可能较相干。Traversal divergence 与 shader divergence 都会让同一 wave 内 lane 走不同路径，降低吞吐。

Wavefront 通过队列把 traversal 与 shading 分开
   生成 ray、trace、compact hit、shade、生成 shadow/next bounce 可以拆为多个队列阶段。这样每个阶段处理更相似的工作，降低深递归、材质分支和 ray type 混杂带来的 divergence，代价是 queue buffer、compaction 和多次 dispatch。

数据布局决定 traversal 与 hit shader 的 cache 行为
   BVH node 应紧凑，leaf triangle 按空间或访问顺序排列；material table 先存常用小字段，再按类型读取扩展数据；texture 使用合理 LOD/压缩。Ray tracing 的访问顺序由空间路径决定，比传统 draw 更随机，因此布局尤其重要。

Any Hit 是透明植被和毛发的高成本热点
   Alpha-test geometry 可能让 shadow/reflection ray 触发大量 any-hit 与纹理采样。可以通过 instance mask、RT LOD、简化代理、专用 shadow 几何或硬件透明度加速机制减少开销。关闭植被后 trace 时间显著下降时，应先查这条路径。

硬件 RT 主要加速 traversal/intersection，不会自动解决所有成本
   BLAS/TLAS、专用 intersection hardware 能降低一部分求交开销，但 ray 数、payload、closest-hit BRDF、any-hit、texture、denoiser 与同步仍由引擎负责。4K 大量粗糙 reflection 仍可能完全 shader/bandwidth-bound。

SBT 与 payload 都是调度成本的一部分
   Shader Binding Table 决定 ray 命中后选择哪类 hit group；过细材质 hit group 会增加跳转和缓存压力。Payload 越大，寄存器压力越高。Shadow ray 只需可见性，应该使用比 reflection/GI 更小的数据结构和更激进 ray flags。

Fallback 必须和硬件 RT 一起设计
   高端平台可以使用 hardware RT reflection/shadow，中端可使用 half-resolution + denoise，低端回退 SSR、probe、shadow map 或 compute BVH。能力 profile 应同时定义分辨率、bounce、透明参与和 denoiser，而不是只判断“是否支持 RTX”。

关键路径
--------

Hybrid reflection pass：

::

   raster G-buffer
   → ray generation
   → TLAS traversal
   → instance / BLAS traversal
   → primitive intersection
   → miss: environment
   → hit: closest-hit material
   → 可选 shadow ray
   → 可选 reflection bounce
   → output
   → denoise / temporal accumulation
   → composite

BVH 生命周期：

::

   primitive bounds
   → 判断 static / dynamic / instanced
   → static: high-quality build
   → dynamic: fast build 或 refit
   → 可选 compaction
   → TLAS build/update
   → trace
   → 收集 node / primitive / any-hit 统计
   → 必要时 rebuild 或调整 LOD/mask

性能排查：

::

   分离 AS build/update 与 trace time
   → 按 ray type 统计数量
   → 统计平均 bounce / miss / hit
   → 统计 BVH node 与 primitive candidate
   → 检查 any-hit 次数
   → 检查 closest-hit shader / texture / payload
   → 检查 ray coherence 与 divergence
   → 检查 denoiser / composite
   → 最后才做微小 ALU 优化

概念辨析
--------

* **BLAS 与 TLAS**：BLAS 管底层几何，TLAS 管实例与变换；二级结构让几何更新和场景实例更新拥有不同预算。
* **Build 与 refit**：build 重新决定树拓扑，成本高但质量可恢复；refit 只更新 bounds，快但长期可能增加 overlap。
* **BVH quality 与 ray count**：前者决定每条 ray 访问多少结构，后者决定总共发多少 ray；两项相乘共同决定 traversal 规模。
* **Traversal divergence 与 shader divergence**：前者是 ray 访问不同树节点，后者是命中后执行不同材质/分支；优化手段不同。
* **Ray packet 与 wavefront**：packet 强调把相干 ray 一起处理；wavefront 强调把路径阶段拆成队列，二者都服务执行一致性。
* **Closest hit 与 any hit**：closest hit 负责最终命中材质；any hit 可过滤候选，alpha-test 场景中调用频率可能非常高。
* **SBT 与 material buffer**：SBT 选择 shader 记录，material buffer 提供数据。把每个材质都拆成独立 hit group 通常不是唯一方案。
* **Hardware RT 与完整 renderer**：硬件加速的是部分 traversal/intersection，完整 RT 效果仍包含 shader、采样、降噪、资源同步和 fallback。
* **Half-resolution RT 与降质**：降低 ray 分辨率减少的是 ray 数量，最终质量可通过 temporal/spatial denoise 补偿；它是预算策略，不等于简单缩小最终画面。

本章结论
--------

Ray Tracing 优化应先建立“ray 数量—BVH traversal—hit shader—AS 更新—denoiser”的分段证据，再选择动作。静态/动态对象用不同 BLAS 策略，refit 需要用 traversal 统计约束，ray type 要分预算与队列，透明 any-hit 和随机材质访问要单独处理。硬件 RT 只解决部分遍历问题；真正稳定的高性能路径来自 ray budget、加速结构质量、执行一致性、数据布局和跨平台 fallback 的共同设计。