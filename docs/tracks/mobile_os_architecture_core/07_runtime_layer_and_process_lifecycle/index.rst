===========================================
Part 7: 应用运行时与生命周期策略
===========================================

本模块解构移动应用执行环境与进程治理模型，剖析 ART 虚拟机 (DEX/JIT/AOT/CC-GC)、Zygote Copy-on-Write 孵化、应用前后台状态机、进程回收与 Apple 原生运行时 (dyld 4/ARC)。

.. toctree::
   :maxdepth: 1
   :caption: 模块章节

   01_art_interpreter_jit_aot
   02_art_concurrent_copying_gc
   03_zygote_preload_and_fork_model
   04_app_lifecycle_and_process_priority
   05_apple_dyld_and_arc
