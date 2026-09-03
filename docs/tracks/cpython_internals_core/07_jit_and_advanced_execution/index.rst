======================================================
第 7 模块：Python 3.13+ Copy-and-Patch JIT 与未来展望
======================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节导航

   01_tier2_ir_and_micro_ops
   02_copy_and_patch_jit_compilation
   03_jit_guard_and_deoptimization

模块概述
========

本模块探索现代 CPython 运行时最前沿的即时编译（JIT）技术架构。

全景解构 Python 3.13+ 引入的 Tier 2 优化器架构、微指令（uops）执行轨迹提取与 Trace 执行机制；剖析 Copy-and-Patch JIT 编译器的工作原理，从 Clang 生成的机器码模板与重定位（Relocation）符号表，到运行时极速机器码模板拼接（Stitching）；深入 JIT 守卫指令（Guard）的类型假设校验、失效时的去优化（Deoptimization）与解释器无缝回退机制。
