====================================================================
图形渲染全栈与GPU架构内核全景深度剖析
====================================================================

.. toctree::
   :maxdepth: 2
   :caption: 全书架构体系目录:
   :numbered:

   ROADMAP
   01_gpu_architecture_and_hardware/index
   02_math_and_geometry_foundations/index
   03_rasterization_and_shaders/index
   04_lighting_and_material_systems/index
   05_shadows_and_spatial_acceleration/index
   06_global_illumination_and_ray_tracing/index
   07_post_processing_aa_and_reconstruction/index
   08_modern_graphics_apis_and_drivers/index
   09_modern_render_pipelines_and_profiling/index

专著简介与架构全景
==================

本专著是一部立足于现代 GPU 硬件微架构、底层图形 API（Direct3D 12 / Vulkan / Metal / WebGPU）以及工业级渲染引擎核心机理的全景深度技术著作。

全书坚持“微架构物理事实与数学物理推导优先”原则，自底向上穿透 GPU 计算核心、物理寄存器堆、显存总线控制器与命令调度处理器，系统化解构从几何拓扑变换、光栅化流水线、可编程着色器、PBR 物理材质与阴影映射，到光线追踪、空间加速结构、现代跨平台渲染抽象层（RHI）、GPU 通用计算（GPGPU）及前沿神经渲染的全部底层实现。

核心知识模块拓扑
----------------

.. list-table:: 图形渲染全栈架构与核心知识体系映射
   :widths: 10 25 35 30
   :header-rows: 1

   * - 模块编号
     - 核心系统模块
     - 微架构关键机制与核心路径
     - 解决的核心工程问题
   * - 01
     - GPU 硬件架构与执行模型
     - SM/CU 拓扑、SIMT/Warp 调度、寄存器 Occupancy、显存多级缓存与合并访问
     - 建立硬件级并行执行心智，消除分支发散与带宽瓶颈
   * - 02
     - 图形数学与几何拓扑基础
     - 空间坐标变换流转、法线变换切线空间、半边数据结构、NURBS 与 GPU 并行几何生成
     - 建立几何数据流与坐标流水线的高精度无误差表达
   * - 03
     - 光栅化流水线与着色器系统
     - 顶点装配、边缘方程光栅化、统一着色器架构、动态变体生成与热重载
     - 深入硬件管线各阶段，控制 Draw Call 与着色器编译开销
   * - 04
     - 光照理论与物理材质系统
     - 辐射度量学物理基础、微表面 Cook-Torrance BRDF、次表面散射 (SSS) 与 Disney Principled
     - 严格遵循能量守恒实现真实感材质与高级光学解算
   * - 05
     - 阴影算法与空间加速结构
     - Shadow Map 几何流转、斜率偏差 (Slope-Scaled Bias)、级联阴影 (CSM)、软阴影 (PCSS)、Hi-Z 剔除与 BVH 树
     - 根除自阴影粉刺与 Peter Panning，实现高精度可见性与对数级光线求交加速
   * - 06
     - 全局光照与光线追踪体系
     - 屏幕空间环境光遮蔽 (SSAO/GTAO)、屏幕空间反射 (SSR)、探针/体素 GI、硬件 DXR/Vulkan RT 管线与 ReSTIR
     - 解决实时多反弹间接光照与高保真动态反射
   * - 07
     - 后处理、抗锯齿与图像重构
     - ACES 色调映射、Dual-Kawase 泛光、TAA 历史帧重投影与 DLSS/FSR 超分辨率
     - 突破物理光栅化分辨率与画质瓶颈，实现实时高动态重构
   * - 08
     - 现代底层 API 演进与驱动架构
     - D3D12/Vulkan 显式资源屏障、无绑定 (Bindless) 架构、多队列异步计算与跨平台 RHI
     - 抹平底层图形驱动差异，构建高性能高并发无锁渲染底座
   * - 09
     - 前沿工业渲染管线与性能调优
     - Forward+/Clustered 管线、GPU-Driven 间接绘制、UE5 Nanite/Lumen 与 Nsight/RGP 性能调优
     - 驱动复杂场景几何与光照无限细节，闭环全流程性能优化

索引与搜索
==========

* :ref:`genindex`
* :ref:`search`
