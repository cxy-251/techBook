第096章：高级 Pipeline 特性——Ray Tracing 与 Mesh Shading
=========================================================

核心知识点
----------

高级管线特性必须按“改动哪条数据路径”理解
   Ray Tracing 改变可见性与光线求交路径；Mesh Shading 改变几何组织和剔除路径；VRS 改变像素着色频率；bindless resource 改变材质资源绑定路径。它们的成本归属不同，不能只做一个总开关比较。

Ray Tracing 的第一类核心资源是 Acceleration Structure
   BLAS 保存 mesh/primitive 级几何加速结构，TLAS 保存实例 transform、mask、ID 与 BLAS 引用。静态 mesh 适合长期 BLAS，动态实例更常更新 TLAS；动态变形 mesh 需要在 refit/update 与 rebuild 之间权衡。

BLAS/TLAS 的更新粒度决定实时成本
   静态建筑可一次构建并长期复用；机械臂等拓扑稳定的动态对象可优先 refit/update；层次质量明显下降时才 rebuild。把整个场景每帧全部重建会让 AS build 成为主要瓶颈。

Ray Pipeline 需要同时连接 AS、Shader Program、Binding Table 与 Dispatch
   Vulkan RT 使用 acceleration structure、ray tracing pipeline、shader groups/SBT 与 trace rays；DXR 使用 AS、state object、shader table 与 DispatchRays；MetalRT 对象名称不同。跨 API 引擎应统一抽象成 TLAS、ray program set、resource table 和 dispatch domain。

Shadow Ray 是最适合打通 RT 路径的最小功能
   一条 shadow ray 只需要很小 payload，miss 表示可见，命中表示遮挡。先输出 shadow visibility texture，再让现有 deferred/forward lighting 消费它，可以把 RT 作为独立 visibility pass 插入，而不是立即替换整个渲染器。

RT 同步边界必须纳入 Frame Graph
   AS build 写结构，ray shader 随后读；visibility/reflection texture 写入后 lighting 读取。Build stage、ray stage、shader access、UAV/storage 与 image layout/resource state 都必须正确衔接。

Ray Budget 应按 Pass 分配
   Shadow ray、reflection ray、GI ray 的 payload、距离、recursion、材质 hit cost、分辨率和 denoise 成本完全不同。先控制 ray count、分辨率、roughness/importance mask 和最大距离，再谈复杂 shader。

Mesh Shading 把几何组织前移到 Meshlet
   离线把 mesh 切成小型 meshlet，并附带 bounds、normal cone、LOD、material 等 metadata；task/amplification 阶段先做 frustum/cone/LOD culling，通过后再由 mesh shader 生成顶点和 primitive。

Meshlet 的价值来自“先读轻量 Metadata，再读重顶点数据”
   传统路径通常先进入 vertex processing；mesh shading 可以在读取完整顶点属性前淘汰大量不可见 meshlet。远景城市、大量重复机械件和高 draw-count 场景收益更明显。

Meshlet 过小或过大都会损失效率
   太小会增加 task/mesh dispatch 数量和 metadata 开销；太大降低剔除精度并提高寄存器/shared memory 压力。要观察每帧 meshlet 数、cull ratio、输出 primitive、occupancy 与 front-end 时间。

Mesh Shading 与 Ray Tracing 可以共享资产但走不同派生数据
   Raster 路径使用 meshlet buffer，RT 路径使用 BLAS/TLAS。资产管线应从同一源 mesh 生成两类缓存数据，运行时根据 capability profile 和质量档位启用。

VRS 是像素着色预算控制工具
   它通过 shading-rate image/tile 或 API 对应机制让不同屏幕区域以不同频率执行像素着色。适合低对比、远处或外围区域；UI、细线、高频纹理、运动边界等区域应保持高质量率。

Bindless 把材质绑定问题变成资源索引问题
   大规模 texture/resource 放入统一表，shader 按 material index 访问。它能减少 CPU binding，但会把错误集中到 descriptor index、residency、non-uniform access、越界和生命周期管理上。

Fallback 应保持上层输出语义一致
   RT shadow 可退回 shadow map，RT reflection 可退回 SSR/probe，mesh shading 可退回 compute culling + indirect/传统 indexed draw，VRS 可退回 full-rate shading。Lighting 或后处理最好继续消费同类型 visibility/reflection/color 输出。

高级特性应分阶段启用和度量
   先打通 meshlet culling，再接 RT visibility，再加 VRS/bindless；每一步都记录 GPU timer、resource bandwidth、AS build、ray count、meshlet cull ratio 与画质。一次性打开所有功能会失去性能归因能力。

每个高级 Pass 都需要 Debug Visualization
   TLAS instance ID、BLAS build count、ray hit distance、shadow visibility、meshlet cull result、shading rate image、bindless material index 都应可视化。没有这些中间证据，错误很容易被误判为 shader 数学问题。

关键路径
--------

Ray Traced Shadow：

::

   mesh/index buffers
   → build/reuse BLAS
   → instance transforms
   → build/update TLAS
   → bind ray program + resource table
   → trace shadow rays
   → visibility texture
   → denoise/temporal if needed
   → deferred/forward lighting

Mesh Shading：

::

   source mesh
   → offline meshlet build
   → meshlet metadata + compressed vertex/index data
   → task/amplification culling
   → surviving meshlets
   → mesh shader outputs vertices/primitives
   → rasterization

Feature Selection：

::

   query capability profile
   → choose RT / ray query / raster fallback
   → choose mesh shader / indirect fallback
   → choose VRS / full-rate fallback
   → choose bindless / material-table fallback
   → build frame graph with identical semantic outputs

性能排查：

::

   AS build/update time
   → ray count / hit shader / denoiser
   → meshlet count / cull ratio / output primitives
   → shading-rate coverage
   → descriptor/bindless bandwidth
   → synchronization / queue overlap
   → final frame-time delta and quality delta

概念辨析
--------

* **BLAS 与 TLAS**：BLAS 描述几何，TLAS 描述实例及其 transform/visibility，并引用 BLAS。
* **RT Pipeline 与 Ray Query**：完整 pipeline 有 raygen/miss/hit group 与 SBT；ray query 可嵌入普通 shader/compute 中执行局部求交查询。
* **Meshlet 与 Mesh**：meshlet 是为 GPU 调度和剔除构造的小型几何块，不替代源资产语义。
* **Task/Amplification 与 Mesh Shader**：前者决定发射哪些 meshlet 工作，后者生成最终顶点和 primitive。
* **Mesh Shading 与 Indirect Draw**：前者重构几何 shader 管线，后者仍可沿传统 vertex/index 路径由 GPU 生成 draw 参数。
* **VRS 与 Dynamic Resolution**：VRS 改变局部 shading rate，动态分辨率改变整张 render target 的像素数量。
* **Bindless 与“无生命周期管理”**：bindless 只减少绑定动作，descriptor/residency/index/lifetime 仍必须严格管理。

本章结论
--------

高级管线特性应按“Capability—Derived Asset/Data—Pass—Resource Binding—Synchronization—Budget—Fallback”理解。RT 问题先查 AS、ray program 与同步；mesh shading 先查 meshlet bounds、cull 与输出数量；VRS 查 shading-rate 区域；bindless 查 index 和资源表。真正可用的高级 renderer 不是把新特性全部打开，而是让每项特性都有明确收益对象、可量化预算、独立证据和语义一致的降级路径。