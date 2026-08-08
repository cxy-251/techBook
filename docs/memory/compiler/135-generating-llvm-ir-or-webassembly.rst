第135章：Generating LLVM IR or WebAssembly
===========================================

核心知识点
----------

* 小语言完成 bytecode VM 后，已经形成闭环；生成 LLVM IR 或 WebAssembly 的意义，是把后端优化、链接、运行时和平台执行交给成熟外部工具链。
* 外部后端接入的第一步是固定 value representation：语言中的 number、bool、string、function、local variable 必须映射成 LLVM/Wasm 可验证的类型与存储形式。
* LLVM IR 强调 typed SSA/basic-block 结构；Wasm 强调 validated module、typed operand stack、structured control flow、locals 和 linear memory。
* Mutable local 在 LLVM 中可以先降低为 ``alloca/load/store``，再交给优化器提升为 SSA；在 Wasm 中通常直接映射到 mutable local。
* LLVM 的每个 basic block 必须以 terminator 结束；分支、循环和 merge point 都要形成合法 CFG，phi incoming edge 必须与前驱关系一致。
* Wasm 不要求前端显式构造传统 basic-block/phi 形式；``block``、``loop``、``if``、``br``、``br_if`` 与 local/operand stack 共同表达结构化控制流。
* 函数调用 lowering 必须保持参数求值顺序、类型、返回值数量和调用契约。LLVM 通过函数类型与 ``call`` 表达，Wasm 通过 function type/index 与 stack 参数表达。
* String 是最早暴露 runtime boundary 的对象之一。LLVM 常把字符串放入 module 全局常量并向 helper 传 ``ptr/len``；Wasm 常把 UTF-8 字节放入 linear memory data segment并传 offset/length。
* Core LLVM/Wasm 都不会自动提供语言层 ``print``、heap、字符串对象或文件系统。前端必须定义 runtime helper、libc/WASI 或 host import contract。
* LLVM route 的主链是 ``emit IR → verify → optimize → lower/codegen → object → link → execute``；每层都有独立可观察产物。
* Wasm route 的主链是 ``emit module/WAT → validate → encode Wasm → instantiate with imports → execute/export``。
* Verifier/validator 是外部后端接入的第一道正确性门槛：结构合法不等于语义一定正确，但非法类型、控制流、stack/phi 关系应尽早被拒绝。
* 观察工具很重要：LLVM IR、optimized IR、assembly、object/disassembly，以及 WAT/Wasm disassembly、imports/exports、runtime trace 都能定位 lowering 错在哪一层。
* 生成 LLVM IR 或 Wasm 后，小语言不再只运行在自制 VM 中，而是成为真实优化器、链接器、runtime 和平台生态的参与者。

关键路径
--------

LLVM 后端：

::

   typed AST / simple IR
   → map language types to LLVM types
   → generate functions/basic blocks/instructions
   → lower mutable locals to slots or SSA
   → lower branches/loops/calls
   → declare runtime helpers
   → LLVM verifier
   → optimizer
   → target codegen
   → object + linker
   → executable/runtime behavior

WebAssembly 后端：

::

   typed AST / simple IR
   → map values to Wasm types/locals/memory
   → generate module + function signatures
   → structured block/loop/if lowering
   → encode calls/imports/exports
   → place strings/data in linear memory
   → validate module
   → instantiate with host/WASI capabilities
   → execute exports

概念辨析
--------

* **Language type 与 target type**：前者属于源语言语义，后者是 LLVM/Wasm 中用于验证和执行的具体表示。
* **LLVM IR 与 GPU/CPU machine code**：LLVM IR 仍是中间表示，后端还要继续做 target-specific lowering 和 code generation。
* **Wasm module 与 native binary**：Wasm 是可移植执行格式，不是特定 CPU 的最终机器码，runtime 仍可解释/JIT/AOT。
* **LLVM basic blocks/phi 与 Wasm structured control flow**：两者都表达控制和数据合流，但结构模型不同，不能机械一一翻译。
* **Core backend 与 runtime services**：LLVM/Wasm 负责计算表示和执行约束，I/O、string runtime、allocation、OS 能力需要额外 helper/import/ABI 契约。

本章结论
--------

外部后端接入的稳定模型是 ``Language Semantics → Target Value/Control Representation → Verification → Runtime/Toolchain Integration``。LLVM IR 与 Wasm 让小编译器把自定义语言语义接入成熟后端，但真正正确的接入仍依赖清晰类型映射、控制流 lowering、runtime boundary 和逐层可验证产物。