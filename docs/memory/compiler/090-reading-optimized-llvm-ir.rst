第090章：Reading Optimized LLVM IR
===================================

核心知识点
----------

* 优化后的 LLVM IR 应当被当作“优化器已经证明了什么”的结果来读，而不是当作源码的逐行翻译。
* 比较优化前后 IR 时，先固定编译器版本、target triple、优化等级和关键 flags；不同目标、``-fwrapv``、``-ffast-math``、sanitizer、debug 选项都可能改变可用语义前提和最终 IR。
* 优化前 IR 常保留更多 ``alloca/load/store``、源码变量槽位、直接分支和 debug-friendly 结构；优化后 IR 更倾向于 SSA values、简化 CFG 和更少的中间对象。
* Constant folding 把编译期已知表达式直接变成常量；阅读时要确认运算在当前 IR semantics 下确实可确定，包括 overflow、floating-point 和 target-specific 约束。
* ``instcombine`` 等 canonicalization pass 常把等价表达式改写成 LLVM 更偏好的规范形式，例如 ``x + 0 → x``，为后续优化创造更简单的模式。
* Dead Code Elimination 删除“结果无人使用且无可观察副作用”的计算。判断 dead 不能只看 use count，还要检查 store、volatile、atomic、call、exception、I/O 等 effects。
* ``mem2reg`` 把可提升的 stack slots 转成 SSA values；跨分支合流时可能引入 ``phi``。看到 ``alloca/load/store`` 消失，通常表示局部变量已经不再需要真实内存身份。
* ``simplifycfg`` 会删除不可达边、合并 blocks、消除空跳转和恒定分支。阅读控制流优化时，先画优化前后 CFG，比逐行追 pass 名更可靠。
* Inlining 让 callee body 进入 caller，函数边界和部分 ``call`` 消失，同时暴露更多常量、类型和 alias 事实给后续 pass。
* Loop optimization 可能移动 invariant、规范 induction variable、展开循环、向量化或改变 block 结构。分析时应先定位 header/latch/exit 和 loop-carried dependencies。
* 多个优化通常串联产生结果。Constant propagation 可以让 branch 恒定，随后 simplifycfg 删除路径，DCE 再清理失效值，instcombine 最后收敛表达式。
* 源码变量、临时表达式和结构化 ``if/for`` 消失并不表示语义丢失；它们可能已经被压缩成 SSA data flow、CFG 和更直接的运算。
* Source shape 与 execution shape 是两个层级。优化器保留的是语言允许的 observable behavior，而不是变量名、语句顺序或函数边界本身。
* ``nsw``、``nuw``、``exact``、fast-math flags、function attributes 等是优化证明的重要输入。看到强优化时，应回查这些 semantic flags，而不是只从源码直觉判断合法性。
* Debug metadata 尝试把优化后的 instruction/value/location 映回 source line、variable 和 inline stack，但优化可能让某些变量没有稳定 location 或只在部分范围可观察。
* ``-g`` 不意味着优化 IR 保留源码形态；debug info 的职责是尽量维护映射，而不是阻止合法优化。
* 阅读 optimized IR 的有效方法是做 controlled experiment：同一输入比较 ``-O0``、``-O2``，或用 ``opt -passes=...`` 一次只运行小 pipeline，逐步定位变化来源。
* 如果怀疑 miscompilation，应从“哪一步 IR 首次偏离预期语义”入手，保存 pass 前后 IR、缩小 pipeline，并让 verifier/执行测试共同提供证据。

关键路径
--------

前后对比：

::

   same source + same target/options
   → unoptimized IR
   → optimized IR
   → compare function signature/attributes
   → compare CFG/basic blocks
   → compare memory ops
   → compare SSA/value graph
   → identify semantic facts enabling changes

常见优化链：

::

   constant/value fact discovered
   → constant folding / propagation
   → branch becomes constant
   → simplifycfg removes dead edge/block
   → DCE removes unused instructions
   → instcombine canonicalizes remainder

源码可观察性：

::

   source variable/expression
   → frontend IR + debug metadata
   → optimizer merges/moves/removes values
   → optimized instruction locations
   → debug metadata tracks surviving relation
   → debugger reconstructs best-effort source view

概念辨析
--------

* **Optimized IR 与 source code**：前者表达优化器证明后的程序，后者表达程序员写下的结构；两者不要求形状一致。
* **Code disappears 与 behavior disappears**：中间计算或分支消失可以是合法证明结果，只要可观察语义保持。
* **mem2reg 与 register allocation**：mem2reg 是中端把内存槽提升为 SSA values；真正物理寄存器分配发生在后端。
* **Debug metadata 与 execution semantics**：debug metadata 服务源码映射，不决定程序核心执行语义。
* **Pass name 与 proof**：知道“这是 instcombine”不够；应继续确认它依赖的具体 IR facts 和 semantic flags。

本章结论
--------

读 optimized LLVM IR 的稳定方法是 ``Before/After Diff → CFG → SSA/Memory → Semantic Flags → Pass Proof Chain → Debug Mapping``。优化后的 IR 是一份压缩后的证明产物：源码形态可以大幅消失，真正必须保留的是 LLVM IR 语义允许的可观察行为。