===========================================
Part 5: 阴影算法与空间加速结构
===========================================

本模块系统剖析实时阴影技术与空间加速层次结构，深入标准 Shadow Mapping 几何原理、自阴影粉刺 (Acne) 与 Peter Panning 瑕疵的斜率偏差消除、级联阴影贴图 (CSM) 视锥体分割稳定对齐、软阴影 PCF/PCSS/VSM 滤波算法，以及 GPU 视锥体/遮挡剔除与 BVH 空间加速结构。

.. toctree::
   :maxdepth: 1
   :caption: 模块章节

   01_shadow_mapping_and_biasing
   02_cascaded_shadow_maps
   03_soft_shadows_pcf_pcss_vsm
   04_visibility_culling_and_hi_z
   05_bvh_construction_and_traversal
