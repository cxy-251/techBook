====================================================================================
第 9 模块：现代多层编译体系、MLIR 与微型编译器实战 (09_modern_mlir_and_mini_compiler)
====================================================================================

.. note:: 模块导读与架构定位
   本模块是全书的终局收官与综合实践篇章。在系统剖析了词法语法、语义分析、中间表示、控制流图、SSA 构造、数据流分析、目标机代码生成、寄存器分配、链接加载以及运行时 JIT 虚拟机的完整链路之后，本模块将视野跃升至工业级编译器基础设施与现代多层中间表示架构。
   我们将首先拆解 LLVM New Pass Manager 的基础设施工程、PreservedAnalyses 缓存拓扑与 opt/FileCheck 测试体系；随后深入 MLIR 的 Dialect 扩展哲学、Operation/Region/Block 拓扑与渐进降级（Progressive Lowering）机制；进一步探索领域特定编译器（GPU/SPIR-V 与 AI 计算图融合）；最后，我们将融会贯通全书理论，从零手写构建一个端到端完备、自包含、可运行的微型编译器（Mini-Compiler），完成从前端词法解析到后端原生汇编代码生成的终极闭环。

.. toctree::
   :maxdepth: 2
   :caption: 模块章节清单

   01_llvm_pass_manager_and_infrastructure_engineering.rst
   02_mlir_dialects_and_progressive_lowering.rst
   03_domain_specific_compilers_gpu_and_ai_graphs.rst
   04_building_a_mini_compiler_frontend_and_ir.rst
   05_building_a_mini_compiler_backend_and_codegen.rst
