===========================================
Part 8: 现代底层 API 演进与驱动架构
===========================================

本模块解构现代显式图形 API（Direct3D 12 / Vulkan / Metal）的设计哲学与驱动核心机理，深入资源屏障与虚拟显存分页、无绑定（Bindless）架构与描述符索引、多硬件队列异步计算调度，以及跨平台渲染硬件接口（RHI）架构设计。

.. toctree::
   :maxdepth: 1
   :caption: 模块章节

   01_explicit_apis_and_resource_model
   02_memory_management_and_barriers
   03_descriptors_and_bindless_architecture
   04_async_compute_and_multi_queue
   05_engine_rhi_abstraction_design
