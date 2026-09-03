========================================================================
模块 08：帧生命周期与 VSync 硬件对齐 (Frame Pipeline & VSync)
========================================================================

本模块深入 Flutter C++ 引擎与底层调度管道，系统解构 C++ Embedder 宿主工程架构、Platform/UI/Raster/IO 四大多线程并发模型与 TaskRunner 消息分发机制、PlatformDispatcher 原生事件管道与 Multi-View 视口管理、WidgetsFlutterBinding 七大底层 Mixin 拓扑、以及硬件 VSync 信号驱动与 SchedulerBinding 四大帧阶段（Animate / Build / Layout / Paint）。

.. toctree::
   :maxdepth: 2

   01_embedder_and_threads
   02_platform_dispatcher_pipeline
   03_widgets_flutter_binding_mixins
   04_scheduler_vsync_phases
