第045章：SSA as the Language of Modern Optimizers
=================================================

核心知识点
----------

* 现代优化型 IR 通常把程序组织成 operation、typed SSA value、control-flow edge 和 memory/effect relation 的组合图。
* SSA 的根本价值是让每个寄存器式 value 拥有唯一 producer，使 use-def/def-use、常量事实、range、ownership 等属性可以直接附着在 value graph 上传播。
* Operation 消费 operands 并产生 results；type 约束 operation 的合法输入输出。优化器改写 value 时必须同时满足类型、支配关系、region/CFG 和 operation semantics。
* ``phi``、block argument 或等价机制把路径相关值重新变成单一 SSA identity，使后续优化无需反复模拟源码变量在不同路径上的赋值历史。
* SSA 优化关注的是 value，而非源码变量名字。源码变量可能消失、拆成多个 values、被折叠成常量或只保留 debug mapping。
* Memory 是纯 SSA value graph 的主要边界。``store`` 修改地址背后的状态，``load`` 读到什么取决于别名、控制流、调用副作用、volatile/atomic 与语言内存模型。
* 局部、不逃逸、别名关系简单的内存槽位可以提升为 SSA；一般内存则需要 MemorySSA、alias analysis、dependence/effect model 等补充关系。
* 同一套 SSA 思想可以出现在 LLVM、MLIR、Swift SIL、GCC SSA 等不同系统中，但 value merging、ownership、regions、memory modeling 和 verifier 规则会有工程差异。
* 高层 IR 可以保留 tensor、ownership、region 等强语义，低层 IR 则逐渐暴露 pointer、machine register 和 ABI 约束；SSA 可以跨多个 lowering 层继续存在。
* 优化 pass 的典型安全检查顺序是：definition/use → type → dominance → side effects/memory → control reachability → language/IR flags → verifier。
* SSA 并不是机器执行模型。最终后端仍要把 values 映射到物理寄存器、栈槽、内存和 move 指令，并落实调用约定与目标 ISA。
* 现代优化器“用 value 思考”的含义是：先证明一个 value 的来源、属性、用途和路径条件，再决定是否传播、替换、移动或删除产生它的 operation。

关键路径
--------

现代 SSA IR：

::

   source semantics
   → operations + typed SSA values
   → explicit CFG / regions
   → phi or block arguments at joins
   → analysis facts on values
   → optimization graph rewrites
   → lower toward machine constraints

纯 value 优化：

::

   value definition
   → inspect operands and type
   → propagate fact through users
   → prove dominance / reachability
   → replace or fold operation

触及内存时：

::

   load/store/call
   → identify addresses and effects
   → alias / memory-version analysis
   → control and ordering constraints
   → prove safe transformation
   → preserve observable behavior

概念辨析
--------

* **SSA value 与 memory state**：SSA value 通常有唯一 producer；内存状态由一系列可能别名的读写共同决定。
* **Operation 与 source statement**：operation 是 IR 中可验证、可改写的语义单元，不要求与某一行源码一一对应。
* **SSA 与 specific compiler**：SSA 是通用 IR 思想，不属于 LLVM 独有；不同生态可用不同合流和 effect 表示。
* **High-level SSA 与 machine SSA**：两者都可保持单定义性质，但承载的类型、operation 和约束层级不同。
* **Optimizer view 与 machine execution**：优化器围绕 values 和 dependencies 工作，机器最终执行的是指令、寄存器、内存和控制转移。

本章结论
--------

SSA 已成为现代优化器的通用工作语言，因为它把程序从“变量不断改变”重构成“operations 产生 values，values 沿控制与数据关系流动”。这让大量优化可以局部证明和图式改写；真正的复杂度随后集中到 memory、effects、control-flow 和最终机器资源映射上。