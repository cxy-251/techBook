========================================================================
第 2 模块：动态显存管理与模型卸载机制 (02_vram_and_offload_management)
========================================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节目录

   01_vram_state_and_device_tracking
   02_model_lifecycle_and_loaded_models
   03_dynamic_weight_streaming_and_cast
   04_aimdo_and_memory_pressure_guard

模块架构概述
============

本模块深入剖析 ComfyUI 在有限物理显存（VRAM）约束下实现超大生成式 AI 模型（如 SDXL、SD3、Flux.1）极致吞吐的异构显存调度中枢。

ComfyUI 的显存管理机制通过 ``comfy/model_management.py`` 与 ``comfy/memory_management.py`` 实现了精细的硬件抽象：

1. **显存物理分级与设备探测**：实时感知 GPU 物理显存余量、系统内存水位，建立分级的显存预算策略（HIGHVRAM/NORMALVRAM/LOWVRAM/NO_VRAM）。
2. **LoadedModel 生命周期状态机**：追踪所有常驻显存或内存的模型实例，基于引用计数、计算依赖与使用时间维护动态 LRU 换出队列。
3. **动态权重流式换入换出**：在模型前向计算前精准释放低优先级显存，将权重即时从系统内存传输至目标计算设备，并在计算完成后优雅卸载。
4. **AIMDO 与显存压力防护**：集成显存碎片整理、跨步显存估算与 OOM 异常拦截自愈机制，杜绝显存溢出导致的进程崩溃。
