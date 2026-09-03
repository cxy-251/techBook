===========================================
Part 6: 全局光照与光线追踪体系
===========================================

本模块系统解构现代实时与离线全局光照（Global Illumination）与硬件加速光线追踪技术，涵盖屏幕空间环境光遮蔽（SSAO / HBAO / GTAO）、屏幕空间反射（SSR / Hi-Z 步进）、光照探针与体素辐射度（Irradiance Probes / VXGI）、硬件光线追踪核心架构（RT Core / DXR / Vulkan RT 管线），以及基于蒙特卡洛积分与时空重要性重采样的路径追踪（Path Tracing / ReSTIR）。

.. toctree::
   :maxdepth: 1
   :caption: 模块章节

   01_screen_space_ambient_occlusion
   02_screen_space_reflections
   03_light_probes_and_voxel_gi
   04_hardware_ray_tracing_dxr_vulkan
   05_path_tracing_and_restir
