========================================================================
模块 09：图层合成与 GPU 光栅化 (Rendering & GPU Pipeline)
========================================================================

本模块深入 Flutter 3.32 渲染管线与底层引擎图形子系统源码，系统解构 PipelineOwner 五大刷新阶段 (flushLayout/flushPaint)、RepaintBoundary 重绘边界与 LayerTree 图层合成、SceneBuilder 场景打包与 GPU 光栅化提交、以及 BinaryMessenger 二进制跨语言零拷贝通信机制。

.. toctree::
   :maxdepth: 2

   01_pipeline_owner_flush
   02_repaint_boundary_and_layers
   03_scene_builder_and_gpu_raster
   04_platform_channels_binary_messenger
