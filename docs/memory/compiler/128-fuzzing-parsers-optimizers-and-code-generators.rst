第128章：Fuzzing Parsers, Optimizers, and Code Generators
=========================================================

核心知识点
----------

* Fuzzing 的核心不是“随机输入”本身，而是自动探索人工测试难以覆盖的编译器状态，并用 coverage、verifier、sanitizer、timeout、行为差异等 oracle 判断异常。
* 一个完整 fuzzer 至少包含 seed/corpus、generator 或 mutator、compiler entry、feedback、failure oracle 与 reducer。
* Fuzz 入口决定覆盖范围和定位精度。源码入口覆盖 lexer/parser/sema/IR/backend，覆盖广但归因长；IR 或 backend 入口更窄，更适合定位 optimizer/codegen 问题。
* Parser/frontend fuzzing 可以接受大量非法源码，因此“产生诊断”通常是正常行为。真正异常包括 crash、hang、栈溢出、越界 source range、非法 AST 与恢复状态矛盾。
* 字节级 frontend fuzzing 适合错误恢复与 lexer/parser 边界；结构化源码生成更容易穿过 parser，深入 type checker、template/generic 与 lowering 路径。
* Optimizer fuzzing 应尽量生成 verifier 可接受的合法 IR，否则大部分覆盖会停留在 IR parser/verifier，而不是目标 pass。
* Optimizer oracle 包括 crash/assert、sanitizer、timeout、verifier failure，以及优化前后可观察语义不一致。
* Codegen fuzzing 可以固定 IR，改变 target triple、CPU features、vector type、calling convention、instruction pattern 等后端约束，探索 instruction selection、register allocation 与 emission 边界。
* Fuzzer 发现 failure 后，必须保存输入、工具版本、target、pass pipeline、随机 seed、命令行和 stderr；没有这些材料的 crash 很难转成可修复 bug。
* Coverage-guided fuzzing 会把触发新路径/新特征的输入加入 corpus，再围绕它继续变异，因此 corpus 质量直接影响长期探索能力。
* Fuzzing 的价值在于覆盖“合法但罕见”“接近合法”“目标组合异常”等状态，不应把它理解成替代 unit/regression test。
* 每个 fuzz failure 都应经过 reduction，最终转成最小、稳定、可自动复现的 regression test，才能真正进入编译器质量体系。

关键路径
--------

Fuzzing 主循环：

::

   seed corpus
   → mutate/generate input
   → compiler entry at source/IR/backend layer
   → execute target stages
   → collect coverage + verifier/sanitizer/runtime evidence
   → new coverage: retain in corpus
   → failure: save reproducer
   → reduce testcase
   → regression test

分阶段 fuzzing：

::

   source bytes → lexer/parser/sema oracle
   structured source → deeper frontend/lowering oracle
   valid IR → optimizer + verifier oracle
   machine/target IR → instruction selection/regalloc/codegen oracle

概念辨析
--------

* **Random testing 与 fuzzing**：fuzzing 通常包含反馈、corpus 演化、failure oracle 和自动 reduction，不只是一次性随机输入。
* **Byte-level 与 structured fuzzing**：前者更容易破坏语法，后者更容易生成可深入后续阶段的有效结构。
* **Invalid IR 与 optimizer bug**：若输入本来违反 IR 规则，失败可能属于 verifier/输入边界；测试 optimizer 时应优先保证输入在其契约内合法。
* **Coverage 与 correctness oracle**：覆盖率告诉系统“走到了新状态”，不能独自证明状态正确；verifier、行为比较等才判断异常。
* **Fuzzer finding 与 regression test**：前者可能巨大、随机、难读；后者必须最小化、稳定化并长期保存。

本章结论
--------

编译器 fuzzing 的稳定模型是 ``Generate/Mutate → Enter a Specific Representation Layer → Observe Invariants → Reduce Failure``。真正有效的 fuzzing 会明确输入在哪一层、该层必须保持什么不变量、什么证据算失败，并把自动发现的罕见状态最终沉淀成可长期维护的测试。
