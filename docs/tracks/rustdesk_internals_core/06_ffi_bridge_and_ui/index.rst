====================================================
模块 06：Rust-Flutter FFI 桥接与跨平台渲染
====================================================

本模块剖析 RustDesk 在客户端 UI 层的跨语言架构：flutter_rust_bridge 代码生成、StreamSink 异步事件流分发，以及 GPU Texture 纹理共享渲染流水线。

.. toctree::
   :maxdepth: 2
   :numbered:

   01_flutter_rust_bridge_codegen
   02_streamsink_and_event_loops
   03_texture_rendering_backend
