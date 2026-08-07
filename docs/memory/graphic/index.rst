Graphic 必背课本
================

本目录与 AIBook 的 ``docs/Graphic`` 一一对应。AIBook 保留完整讲解、案例、代码、图示与练习，这里只保留每章稳定、必须掌握、可以直接复习的知识模型。

Part 1：GPU 架构与硬件
----------------------

* `第001章：GPU 硬件基础 <001-gpu-hardware-fundamentals.rst>`_；
* `第002章：SIMD 与 SIMT 并行架构 <002-parallel-architectures-simd-simt.rst>`_；
* `第003章：GPU 内存层级与缓存 <003-memory-hierarchy-and-caches.rst>`_；
* `第004章：GPU 命令处理与调度 <004-command-processing-and-scheduling.rst>`_；
* `第005章：GPU 性能约束 <005-gpu-performance-constraints.rst>`_。

Part 2：图形学数学基础
---------------------

* `第006章：线性代数基础 <006-linear-algebra-essentials.rst>`_；
* `第007章：坐标系与变换 <007-coordinate-systems-and-transformations.rst>`_；
* `第008章：几何与向量分析 <008-geometry-and-vector-calculus.rst>`_；
* `第009章：数值方法与精度 <009-numerical-methods-and-precision.rst>`_；
* `第010章：插值与采样 <010-interpolation-and-sampling.rst>`_。

Part 3：几何表示与处理
---------------------

* `第011章：网格拓扑与数据结构 <011-mesh-topology-and-data-structures.rst>`_；
* `第012章：曲线与曲面表示 <012-surface-and-curve-representations.rst>`_；
* `第013章：网格属性与格式 <013-mesh-attributes-and-formats.rst>`_；
* `第014章：细节层次与网格简化 <014-level-of-detail-and-simplification.rst>`_；
* `第015章：程序化几何 <015-procedural-geometry.rst>`_；
* `第016章：GPU 并行程序化生成 <016-gpu-parallel-procedural-generation.rst>`_。

Part 4：光栅化管线
-----------------

* `第017章：顶点处理 <017-vertex-processing.rst>`_；
* `第018章：基元装配 <018-primitive-assembly.rst>`_；
* `第019章：裁剪与剔除 <019-clipping-and-culling.rst>`_；
* `第020章：光栅化算法 <020-raster-algorithms.rst>`_。

Part 5：Shader 系统与编程
------------------------

* `第021章：Shader Model 演进 <021-shader-model-evolution.rst>`_；
* `第022章：Vertex Shader 深入 <022-vertex-shaders-in-depth.rst>`_；
* `第023章：Fragment 与 Pixel Shader <023-fragment-and-pixel-shaders.rst>`_；
* `第024章：Geometry 与 Tessellation Shader <024-geometry-and-tessellation-shaders.rst>`_；
* `第025章：Compute Shader <025-compute-shaders.rst>`_；
* `第026章：动态 Shader 生成与热更新 <026-dynamic-shader-generation-and-hot-reloading.rst>`_。

Part 6：光照与材质模型
---------------------

* `第027章：局部光照模型 <027-local-illumination-models.rst>`_；
* `第028章：BRDF 与材质系统 <028-brdf-and-material-systems.rst>`_；
* `第029章：反射与 Fresnel <029-reflection-and-fresnel.rst>`_；
* `第030章：次表面散射 <030-subsurface-scattering.rst>`_；
* `第031章：阴影技术 <031-shadowing-techniques.rst>`_；
* `第032章：高级材质模型与微表面 BRDF <032-advanced-material-models-and-microfacet-brdf.rst>`_。

Part 7：Ray Tracing 与真实感渲染
-------------------------------

* `第033章：Ray Casting 基础 <033-ray-casting-fundamentals.rst>`_；
* `第034章：基础 Ray Tracing 算法 <034-basic-ray-tracing-algorithms.rst>`_；
* `第035章：递归反射与折射 <035-recursive-reflection-and-refraction.rst>`_；
* `第036章：Monte Carlo 积分 <036-monte-carlo-integration.rst>`_；
* `第037章：Ray Tracing 优化 <037-ray-tracing-optimization.rst>`_。

Part 8：全局光照技术
-------------------

* `第038章：Radiosity 方法 <038-radiosity-methods.rst>`_；
* `第039章：Path Tracing <039-path-tracing.rst>`_；
* `第040章：Photon Mapping <040-photon-mapping.rst>`_；
* `第041章：双向渲染技术 <041-bidirectional-techniques.rst>`_；
* `第042章：Irradiance Caching <042-irradiance-caching.rst>`_。

Part 9：纹理映射与采样
---------------------

* `第043章：纹理坐标、Texel 与采样数据 <043-texture-coordinates-texels-and-sampling-data.rst>`_；
* `第044章：过滤与 Mipmapping <044-filtering-and-mipmapping.rst>`_；
* `第045章：纹理压缩 <045-texture-compression.rst>`_；
* `第046章：高级纹理技术 <046-advanced-texture-techniques.rst>`_。

Part 10：可见性与剔除算法
------------------------

* `第047章：视锥体剔除 <047-view-frustum-culling.rst>`_；
* `第048章：Occlusion Query <048-occlusion-queries.rst>`_；
* `第049章：Portal 与 Cell 剔除 <049-portal-and-cell-culling.rst>`_；
* `第050章：硬件遮挡剔除 <050-hardware-occlusion.rst>`_。

Part 11：图像处理与视觉感知
--------------------------

* `第051章：色彩理论与色彩空间 <051-color-theory-and-color-spaces.rst>`_；
* `第052章：图像过滤与重建 <052-image-filtering-and-reconstruction.rst>`_；
* `第053章：Tone Mapping、HDR 与曝光控制 <053-tone-mapping-hdr-and-exposure-control.rst>`_；
* `第054章：感知指标、Gamma 与显示校准 <054-perceptual-metrics-gamma-and-display-calibration.rst>`_；
* `第055章：后处理管线与图像质量调试 <055-post-processing-pipeline-and-image-quality-debugging.rst>`_。

Part 12：空间数据结构
--------------------

* `第056章：Bounding Volume Hierarchy <056-bounding-volume-hierarchies.rst>`_；
* `第057章：KD-Tree <057-kd-trees.rst>`_；
* `第058章：Octree 与 Grid 结构 <058-octree-and-grid-structures.rst>`_；
* `第059章：Scene Graph <059-scene-graphs.rst>`_；
* `第060章：空间加速策略对比 <060-acceleration-strategy-comparison.rst>`_。

Part 13：高级渲染算法
--------------------

* `第061章：屏幕空间效果 <061-screen-space-effects.rst>`_；
* `第062章：体积渲染 <062-volumetric-rendering.rst>`_；
* `第063章：粒子系统 <063-particle-systems.rst>`_；
* `第064章：Hair、Fur 与 Cloth 渲染 <064-hair-fur-cloth-rendering.rst>`_；
* `第065章：后处理管线 <065-post-processing-pipelines.rst>`_。

Part 14：图形物理模拟
--------------------

* `第066章：刚体模拟 <066-rigid-body-simulation.rst>`_；
* `第067章：软体动力学 <067-soft-body-dynamics.rst>`_；
* `第068章：流体模拟 <068-fluid-simulation.rst>`_；
* `第069章：碰撞检测 <069-collision-detection.rst>`_；
* `第070章：模拟驱动渲染 <070-simulation-driven-rendering.rst>`_。

Part 15：离线渲染与生产管线
--------------------------

* `第071章：Render Farm 架构 <071-render-farm-architecture.rst>`_；
* `第072章：高质量渲染器 <072-high-quality-renderers.rst>`_；
* `第073章：去噪与重建 <073-denoising-and-reconstruction.rst>`_；
* `第074章：色彩管理 <074-color-management.rst>`_；
* `第075章：生产工作流集成 <075-production-workflow-integration.rst>`_。

Part 16：动画与运动系统
----------------------

* `第076章：运动学与 Rig 基础 <076-kinematics-and-rigging-fundamentals.rst>`_；
* `第077章：动画混合与状态机 <077-animation-blending-and-state-machines.rst>`_；
* `第078章：物理驱动动画集成 <078-physics-driven-animation-integration.rst>`_；
* `第079章：骨骼动画数据路径与 GPU Skinning <079-skeletal-animation-data-path-and-gpu-skinning.rst>`_；
* `第080章：动画压缩、重定向与运行时流式加载 <080-animation-compression-retargeting-and-runtime-streaming.rst>`_。

Part 17：OpenGL 图形 API 生态
----------------------------

* `第081章：OpenGL 状态机与 Context 生命周期 <081-opengl-state-machine-and-context-lifecycle.rst>`_；
* `第082章：OpenGL Pipeline 到 Workflow 的映射 <082-pipeline-mapping-to-workflow.rst>`_；
* `第083章：OpenGL 状态管理与 Context <083-state-management-and-contexts.rst>`_；
* `第084章：OpenGL Buffer 与 Texture <084-buffers-and-textures.rst>`_；
* `第085章：OpenGL 调试与扩展 <085-debugging-and-extensions.rst>`_。

Part 18：Direct3D 与 HLSL 图形 API 生态
--------------------------------------

* `第086章：Direct3D 设备、管线与资源模型 <086-direct3d-device-pipeline-and-resource-model.rst>`_；
* `第087章：Direct3D Pipeline Mapping <087-pipeline-mapping.rst>`_；
* `第088章：Direct3D 资源绑定模型 <088-resource-binding-models.rst>`_；
* `第089章：HLSL Shader 系统 <089-hlsl-shader-system.rst>`_；
* `第090章：多线程渲染 <090-multi-threaded-rendering.rst>`_。

Part 19：Vulkan 与 Metal 图形 API 生态
-------------------------------------

* `第091章：Vulkan 架构 <091-vulkan-architecture.rst>`_；
* `第092章：Metal 架构 <092-metal-architecture.rst>`_；
* `第093章：显式 Pipeline 管理 <093-explicit-pipeline-management.rst>`_；
* `第094章：Descriptor Set 与资源 <094-descriptor-sets-and-resources.rst>`_；
* `第095章：同步与内存 <095-synchronization-and-memory.rst>`_；
* `第096章：高级 Pipeline 特性——Ray Tracing 与 Mesh Shading <096-advanced-pipeline-features-ray-tracing-and-mesh-shading.rst>`_。

Part 20：Web 图形 API
--------------------

* `第097章：WebGL 基础 <097-webgl-fundamentals.rst>`_；
* `第098章：WebGPU Device、Queue 与 Pipeline 模型 <098-webgpu-device-queue-and-pipeline-model.rst>`_；
* `第099章：WebGPU 高级特性 <099-webgpu-advanced-features.rst>`_；
* `第100章：将 Web API 映射到渲染 Pipeline <100-mapping-web-apis-to-pipeline.rst>`_；
* `第101章：浏览器渲染约束 <101-browser-rendering-constraints.rst>`_；
* `第102章：Web 图形性能 <102-web-performance.rst>`_。

Part 21：游戏引擎渲染架构
------------------------

* `第103章：渲染管线模式 <103-rendering-pipeline-patterns.rst>`_；
* `第104章：Forward Rendering <104-forward-rendering.rst>`_；
* `第105章：Deferred Rendering <105-deferred-rendering.rst>`_；
* `第106章：Scriptable Render Pipelines <106-scriptable-render-pipelines.rst>`_；
* `第107章：引擎集成 <107-engine-integration.rst>`_。

Part 22：GPU Compute for Graphics
---------------------------------

* `第108章：CUDA 图形计算执行模型 <108-cuda-execution-model-for-graphics-compute.rst>`_；
* `第109章：OpenCL 基础 <109-opencl-fundamentals.rst>`_；
* `第110章：Compute Shader 模式 <110-compute-shader-patterns.rst>`_；
* `第111章：Compute-Driven Rendering <111-compute-driven-rendering.rst>`_；
* `第112章：Hybrid Compute 技术 <112-hybrid-compute-techniques.rst>`_。

Part 23：优化与 GPU Profiling
----------------------------

* `第113章：CPU-GPU 成本分析 <113-cpu-gpu-cost-analysis.rst>`_；
* `第114章：Draw Call Batching <114-draw-call-batching.rst>`_；
* `第115章：内存带宽优化 <115-memory-bandwidth-optimization.rst>`_；
* `第116章：Profiling 工具与技术 <116-profiling-tools-and-techniques.rst>`_；
* `第117章：实时性能约束 <117-real-time-performance-constraints.rst>`_；
* `第118章：多 GPU 与分布式渲染优化 <118-multi-gpu-and-distributed-rendering-optimization.rst>`_。

Part 24：跨 API 抽象与统一框架
-----------------------------

* `第119章：抽象原则 <119-abstraction-principles.rst>`_；
* `第120章：API 无关渲染层 <120-api-agnostic-rendering-layer.rst>`_；
* `第121章：Shader 抽象模型 <121-shader-abstraction-models.rst>`_；
* `第122章：GPU 资源抽象与生命周期模型 <122-gpu-resource-abstraction-and-lifetime-model.rst>`_；
* `第123章：框架集成策略 <123-framework-integration-strategies.rst>`_。

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时先判断问题位于 RHI/Backend 抽象边界、resource usage/state/view、Shader source/reflection/binding/variant、GPU resource lifetime/aliasing，还是 capability/fallback 与框架模块集成，再沿 device profile、resource/pipeline handle、pass dependency、barrier/queue、shader identity、frame fence 与 backend diagnostics 寻找第一处失配，最后用 validation、frame capture、pipeline/cache statistics、GPU timestamp 和跨 backend A/B 结果验证结论。