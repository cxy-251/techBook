========================================================================
《图形渲染全栈与GPU架构内核全景深度剖析》全书架构与执行路线图
========================================================================

:书名: 图形渲染全栈与GPU架构内核全景深度剖析 (Graphic Universe Core)
:定位: 工业级 3D 图形渲染、现代 GPU 硬件微架构、Shader 编译系统与物理渲染引擎底层全景专著
:标准规范: 遵循 Sphinx / reStructuredText 工业级排版规范与底层硬件事实推导
:当前完成度: 45 / 45 节 (100.0%) - 全书全量完工 [x]

------------------------------------------------------------------------
模块总览与推进状态表
------------------------------------------------------------------------

.. list-table:: 专著 9 大核心模块推进全景
   :widths: 10 35 15 15 25
   :header-rows: 1
   :class: tight-table

   * - 模块编号
     - 模块全称 (Directory / Module)
     - 规划章节数
     - 已完成章节
     - 当前推进状态
   * - **Part 1**
     - GPU 硬件架构与执行模型 (01_gpu_hardware_and_execution_model)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 2**
     - 图形数学与几何拓扑基础 (02_graphics_math_and_geometry)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 3**
     - 光栅化流水线与着色器系统 (03_rasterization_and_shaders)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 4**
     - 光照理论与物理材质系统 (04_lighting_and_material_systems)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 5**
     - 阴影算法与空间加速结构 (05_shadows_and_spatial_acceleration)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 6**
     - 全局光照与光线追踪体系 (06_global_illumination_and_ray_tracing)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 7**
     - 后处理、抗锯齿与图像重构 (07_post_processing_aa_and_reconstruction)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 8**
     - 现代底层 API 演进与驱动架构 (08_modern_graphics_apis_and_drivers)
     - 5
     - 5
     - **全量完工 [x]**
   * - **Part 9**
     - 前沿工业渲染管线与性能调优 (09_modern_render_pipelines_and_profiling)
     - 5
     - 5
     - **全量完工 [x]**
   * - **全书总计**
     - **9 大模块 (Part 1 ~ Part 9)**
     - **45 节**
     - **45 节**
     - **全书 45 节全量完工 [x] (100.0%)**

------------------------------------------------------------------------
详细章节清单与完成状态
------------------------------------------------------------------------

Part 1: GPU 硬件架构与执行模型 (01_gpu_hardware_and_execution_model) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 01. 现代 GPU 硬件微架构演进：从固定管线到统一着色器架构 (`01_evolution_to_unified_shaders.rst`)
- [x] 02. GPU 物理层拓扑与执行实体：GPC、TPC、SM/CU 与 SIMT 模型 (`02_gpu_topology_sm_simt.rst`)
- [x] 03. 硬件线程束与调度机制：Warp/Wavefront、Scoreboard 与延迟隐藏 (`03_warp_scheduler_and_latency_hiding.rst`)
- [x] 04. GPU 存储层级与带宽瓶颈：寄存器堆、共享内存、L1/L2 Cache 与 HBM/GDDR (`04_gpu_memory_hierarchy_bandwidth.rst`)
- [x] 05. 指令发射与执行单元：ALU、SFU、Tensor Core 与 Ray Tracing Core (`05_execution_units_alu_tensor_rt_cores.rst`)

Part 2: 图形数学与几何拓扑基础 (02_graphics_math_and_geometry) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 06. 齐次坐标与仿射变换：变换矩阵、左/右手系与逆转置矩阵的数学因果 (`01_homogeneous_coordinates_and_transforms.rst`)
- [x] 07. 投影矩阵推导全解：正交投影、透视投影、NDC 深度非线性与逆 Z 缓冲 (`02_projection_matrices_and_reverse_z.rst`)
- [x] 08. 三维旋转与空间朝向：欧拉角万向锁、四元数代数与旋转插值 (`03_euler_angles_and_quaternions.rst`)
- [x] 09. 切线空间与法线拓扑：TBN 矩阵构建、Gram-Schmidt 正交化与法线贴图解算 (`04_tangent_space_tbn_and_normal_mapping.rst`)
- [x] 10. 空间包围体与相交测试：AABB、OBB、包围球、BVH 树与视锥体裁剪数学 (`05_bounding_volumes_and_culling.rst`)

Part 3: 光栅化流水线与着色器系统 (03_rasterization_and_shaders) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 11. 顶点处理与图元装配：Vertex Shader 语义、透视除法与硬件裁剪规则 (`01_vertex_processing_and_primitive_assembly.rst`)
- [x] 12. 光栅化与片段生成：DDA 算法、重心坐标插值、Early-Z 与保守光栅化 (`02_rasterization_algorithms_and_coverage.rst`)
- [x] 13. 着色器模型与字节码编译：Shader Model 演进、DXIL/SPIR-V 与驱动 JIT ISA (`03_shader_model_evolution_and_bytecode.rst`)
- [x] 14. 进阶可编程阶段：几何着色器、曲面细分 (Tessellation) 与网格着色器 (Mesh Shader) (`04_advanced_programmable_stages.rst`)
- [x] 15. 动态着色器生成与变体管理：宏组合、PSO 缓存与爆炸控制 (`05_dynamic_shader_generation_and_variants.rst`)

Part 4: 光照理论与物理材质系统 (04_lighting_and_material_systems) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 16. 局部光照与辐射度量学基础：辐射通量、发光强度、辐照度与 BRDF 能量守恒定律 (`01_radiometry_and_photometric_units.rst`)
- [x] 17. 经典经验光照模型：Lambert 漫反射、Phong 高光与 Blinn-Phong 近似误差推导 (`02_phong_and_blinn_phong_models.rst`)
- [x] 18. 基于物理的渲染 (PBR) 微表面理论：Cook-Torrance 框架与微面法线分布函数 (`03_cook_torrance_and_microfacet_theory.rst`)
- [x] 19. 菲涅尔反射与几何遮蔽项：Schlick 经验近似、Smith 遮蔽函数与多重散射能量补偿 (`04_fresnel_and_geometric_shadowing.rst`)
- [x] 20. 进阶材质表达与着色：Disney Principled BRDF、次表面散射 (BSSRDF) 与各向异性材质 (`05_disney_principled_and_advanced_materials.rst`)

Part 5: 阴影算法与空间加速结构 (05_shadows_and_spatial_acceleration) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 21. 阴影映射核心原理与瑕疵：Shadow Map、自阴影粉刺 (Acne)、Peter Panning 与斜率偏差 (`01_shadow_mapping_and_biasing.rst`)
- [x] 22. 级联阴影贴图 (CSM)：视锥体分割、稳定对齐与边界平滑过渡 (`02_cascaded_shadow_maps.rst`)
- [x] 23. 软阴影过滤技术：PCF、PCSS 与指数阴影贴图 (ESM/VSM) (`03_soft_shadows_pcf_pcss_vsm.rst`)
- [x] 24. 全局可见性剔除：视锥体裁剪、遮挡查询 (Occlusion Query) 与软件光栅化剔除 (`04_visibility_culling_and_hi_z.rst`)
- [x] 25. 空间加速层次结构：BVH 动态重构、SAH 启发式分割与 GPU 遍历栈优化 (`05_bvh_construction_and_traversal.rst`)

Part 6: 全局光照与光线追踪体系 (06_global_illumination_and_ray_tracing) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 26. 屏幕空间环境光遮蔽 (SSAO)：HBAO、GTAO 与弯曲法线 (Bent Normals) 积分 (`01_screen_space_ambient_occlusion.rst`)
- [x] 27. 屏幕空间反射 (SSR)：Hi-Z 层次光线步进、厚度边缘衰减与时间性滤波 (`02_screen_space_reflections.rst`)
- [x] 28. 探针与体素全局光照：辐射度着色 (Radiosity)、光照探针 (Irradiance Probes) 与 VXGI (`03_light_probes_and_voxel_gi.rst`)
- [x] 29. 硬件光线追踪核心架构：RT Core BVH 求交、D3D12 DXR / Vulkan RT 管线 (`04_hardware_ray_tracing_dxr_vulkan.rst`)
- [x] 30. 蒙特卡洛积分与路径追踪：重要性采样、多重重要性采样 (MIS) 与 ReSTIR 算法 (`05_path_tracing_and_restir.rst`)

Part 7: 后处理、抗锯齿与图像重构 (07_post_processing_aa_and_reconstruction) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 31. 高动态范围 (HDR) 与色调映射：ACES 色彩管线、Reinhard 与曝光自适应 (`01_hdr_and_tone_mapping_aces.rst`)
- [x] 32. 泛光与景深模拟：物理 Bloom (Dual-Kawase 降采样)、Circle of Confusion 景深 (`02_bloom_and_depth_of_field.rst`)
- [x] 33. 时间性抗锯齿 (TAA)：历史帧重投影、邻域色彩裁剪 (Color Clamping) 与抖动 (`03_temporal_anti_aliasing_taa.rst`)
- [x] 34. 运动模糊与体积光：速度缓冲区 (Velocity Buffer)、散射相位函数与 Raymarching (`04_motion_blur_and_volumetric_fog.rst`)
- [x] 35. 超分辨率与神经图像重构：DLSS、FSR 2/3、XeSS 架构与时域特征融合 (`05_super_resolution_dlss_fsr.rst`)

Part 8: 现代底层 API 演进与驱动架构 (08_modern_graphics_apis_and_drivers) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 36. 显式图形 API 演进哲学：从 OpenGL/D3D11 状态机到 Vulkan/D3D12/Metal 资源模型 (`01_explicit_apis_and_resource_model.rst`)
- [x] 37. 显存管理与资源屏障：虚拟显存分页、UAV 冒险、Pipeline Barriers 与内存别名 (`02_memory_management_and_barriers.rst`)
- [x] 38. 描述符与无绑定 (Bindless) 架构：Root Signature、Descriptor Indexing 与 SM6.6 (`03_descriptors_and_bindless_architecture.rst`)
- [x] 39. 异步计算与多队列调度：Graphics/Compute/Copy 并发与资源所有权转移 (`04_async_compute_and_multi_queue.rst`)
- [x] 40. 渲染硬件接口 (RHI) 引擎级抽象设计：跨平台状态缓存、命令列表池化与 Shader 变体管线 (`05_engine_rhi_abstraction_design.rst`)

Part 9: 前沿工业渲染管线与性能调优 (09_modern_render_pipelines_and_profiling) [5/5 完工]
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- [x] 41. 现代渲染管线架构：Forward+、Deferred Shading 与 Clustered Light Culling (`01_deferred_forward_plus_and_clustered.rst`)
- [x] 42. GPU-Driven 渲染管线深度演进：间接绘制 (Indirect Draw)、Hi-Z 剔除与两阶段遮挡 (`02_gpu_driven_rendering_pipeline.rst`)
- [x] 43. 几何虚拟化与无限细节：UE5 Nanite 微多边形光栅化、BVH 视锥剔除与软光栅 (`03_geometry_virtualization_nanite.rst`)
- [x] 44. 动态全局光照与无限反弹：UE5 Lumen 表面缓存 (Surface Cache) 与屏幕/硬件追踪融合 (`04_dynamic_global_illumination_lumen.rst`)
- [x] 45. 工业级 GPU 性能分析与调优：RenderDoc 抓帧、NVIDIA Nsight / AMD RGP 瓶颈定位与 Roofline 模型实战 (`05_gpu_profiling_and_roofline_optimization.rst`)
