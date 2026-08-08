第086章：LLVM as a Modular Compiler Infrastructure
====================================================

核心知识点
----------

* LLVM 更准确的定位是 compiler infrastructure，而不是单一“编译器程序”。它提供 IR、优化框架、后端、链接器、调试/分析工具和可复用库，让不同语言与不同目标围绕共同表示协作。
* Clang、``opt``、``llc``、``lld``、``llvm-objdump`` 分别位于不同阶段。理解 LLVM 时应先问“输入是什么表示、输出是什么表示”，而不是先记命令选项。
* Frontend 负责理解源语言并生成 LLVM IR；middle-end 在 IR 上做 analysis/transform；backend 把 IR 降低到 target-specific machine representation；linker 处理 object/symbol/relocation；tooling 提供各阶段证据。
* LLVM IR 是前端与后端的主要集成点。前端把语言特定语义 lower 到 IR，优化器与目标后端只依赖 IR 中明确保存的 type、control flow、memory、attribute 和 metadata 事实。
* “Language-independent IR” 不表示没有语义，而是语义已经从 C/C++/Rust 等源码形式转换成 LLVM 自己的操作、类型、SSA、CFG 和 memory model。
* 前端在 lowering 时必须正确保留优化所需事实，例如 overflow flags、alias 信息、calling convention、debug metadata、exception semantics。事实丢失会减少优化机会，错误事实会直接导致错误优化。
* IR 文本形式、bitcode 和 in-memory IR 是同一语义层的不同载体：文本便于观察，bitcode 便于传输/缓存，内存对象供 pass 直接操作。
* Static compilation 是常见路径：source → IR → optimized IR → machine/object → link → executable。
* JIT 复用 LLVM IR、优化和 codegen，只是把 code generation 与 linking 的时间点移动到运行时，并可能利用当前 CPU、进程和 profile 信息。
* LTO 保留 IR 或等价高层信息到链接阶段，使优化器能跨 translation unit 看到调用图、全局变量和函数体，突破普通 separate compilation 的边界。
* Cross-compilation 的关键不是换一条编译器，而是让相同 IR pipeline 使用不同 target triple、data layout、CPU/features、ABI 和 sysroot/runtime 约束。
* LLVM 的模块化价值来自职责拆分：一个 frontend 不需要自己实现所有 CPU backend，一个 backend 也不需要理解所有源语言。
* 工具输出只能证明对应层级的事实。IR 正确不自动证明 machine code 正确；assembly 正确也不自动证明 link/runtime contract 正确。
* 排查 LLVM 工具链问题时，应沿 source/frontend → IR → pass pipeline → backend → object/link → runtime 分层定位第一个异常表示。

关键路径
--------

标准静态编译：

::

   source language
   → frontend (Clang / other frontend)
   → LLVM IR module
   → analysis + transform passes
   → optimized LLVM IR
   → target backend / codegen
   → assembly or object file
   → linker
   → executable/shared library

模块化复用：

::

   many source languages
   → lower to LLVM IR
   → shared optimizer
   → shared target-independent analyses
   → target backend selected by triple/features
   → many hardware targets

LTO/JIT：

::

   keep IR beyond normal frontend boundary
   → gain later/global/runtime facts
   → run LLVM optimization/codegen later
   → emit or install target machine code

概念辨析
--------

* **LLVM 与 Clang**：LLVM 是基础设施；Clang 是 C-family frontend/tool driver 之一。
* **Frontend 与 optimizer**：frontend 负责源语言语义，optimizer 主要消费 LLVM IR 语义。
* **LLVM IR 与 machine IR**：LLVM IR 仍相对 target-independent；Machine IR 已进入目标指令、寄存器和后端约束。
* **Static compilation 与 LTO**：普通静态编译较早按 translation unit 分离；LTO 把跨模块优化窗口推迟到链接阶段。
* **JIT 与 AOT**：两者都可复用 LLVM optimizer/backend；区别主要是编译成本支付时间和可获得的运行时事实。

本章结论
--------

LLVM 的稳定模型是 ``Frontend → LLVM IR → Pass Pipeline → Backend → Object/Link/Runtime``。真正理解 LLVM，应围绕“表示边界与可复用基础设施”建立心智模型：每个组件只理解自己所在层的表示，通过 LLVM IR 和二进制契约把多个语言、优化器与目标平台连接起来。