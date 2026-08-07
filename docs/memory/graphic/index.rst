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

阅读方式
--------

每章依次保留“核心知识点”“关键路径”“概念辨析”和“本章结论”。阅读时先确定材质输入、光照方向、能量路径、颜色空间与资源阶段，再沿关键路径复盘直接光、反射、散射、阴影和材质分层，最后用概念边界检查光照判断是否准确。
