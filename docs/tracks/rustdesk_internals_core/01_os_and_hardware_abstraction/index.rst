====================================================
模块 01：操作系统与硬件底层交互原语
====================================================

本模块剖析 RustDesk 在 Windows、macOS 与 Linux 三大主流操作系统上的底层硬件与内核交互实现，包括屏幕像素捕获、键鼠事件模拟注入、低延迟音频捕获以及虚拟显示驱动架构。

.. toctree::
   :maxdepth: 2
   :numbered:

   01_screen_capture_primitives
   02_input_injection_engine
   03_audio_capture_pipeline
   04_virtual_display_drivers
