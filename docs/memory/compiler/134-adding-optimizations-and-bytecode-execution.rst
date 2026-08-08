第134章：Adding Optimizations and Bytecode Execution
=====================================================

核心知识点
----------

* 优化阶段的职责是减少不必要的运行时工作，同时保持可观察语义；bytecode 阶段把剩余 IR 编码成 VM 指令；VM 再把指令解释成运行时状态变化。
* Constant folding 只应折叠操作数已知、语义固定且不会改变副作用/异常行为的计算，例如纯整数/数值常量表达式。
* Algebraic simplification 如 ``x + 0 → x``、``x * 1 → x`` 依赖语言语义；浮点、用户重载、异常与副作用都会影响规则是否合法。
* Dead Code Elimination 需要同时判断“结果无人使用”和“指令无可观察副作用”。无使用的 I/O、store、可能抛错的操作仍不能直接删除。
* Unreachable block removal 依赖 CFG 可达性。常量条件折叠后，无法从 entry 到达的 block 可以安全移除，前提是不存在异常/隐式控制边。
* 优化应围绕明确分析事实进行：constant facts、def-use、reachability、effect information。没有证据的“看起来等价”不是合法优化。
* Bytecode 是 VM 的执行格式，不再需要保留源语言全部结构。常见对象包括 opcode、operand、constant pool、local slots、jump offsets、function metadata 和 line table。
* 栈式 VM 的指令通过 operand stack 传递临时值；每个 opcode 都应定义明确的 stack effect，编译器据此计算最大栈深度并验证栈平衡。
* Chunk/function object 至少要记录 code、constants、local count、max stack、source mapping；优化后源码变量可能消失，但 line table 仍负责运行时诊断和调试锚定。
* VM frame 表示一次函数调用，通常保存当前 chunk、instruction pointer、locals/base slot、caller/return information。
* Dispatch loop 的稳定模型是 ``fetch opcode → advance ip → decode operands → mutate stack/frame → repeat/return``。
* 函数调用需要建立新 frame，返回时恢复 caller；递归只是同一函数产生多个独立 frame，不应共享局部槽位状态。
* Debug 与 optimized bytecode 可以采用不同策略：高优化版本可删除局部槽位和中间计算，调试版本可保留更多 source-level evidence。
* Bytecode VM 的价值在于把 frontend、IR、优化和 runtime 第一次闭合为一个完全可观察的执行系统。

关键路径
--------

优化到 bytecode：

::

   typed IR + CFG
   → constant propagation/folding
   → algebraic simplification
   → reachability analysis
   → remove unreachable blocks
   → def-use + effect analysis
   → dead-code elimination
   → lower remaining operations to opcodes
   → build constant pool / locals / jumps / line table
   → verify stack effects and branch targets

VM 执行：

::

   push initial frame
   → ip fetches opcode
   → decode operand
   → push/pop operand stack or read/write locals
   → branch/call updates frame state
   → RETURN pops frame and passes result to caller
   → final frame return becomes program result

概念辨析
--------

* **Constant folding 与 algebraic simplification**：前者直接计算常量，后者利用代数恒等式重写含变量表达式。
* **Unused value 与 dead instruction**：结果没人用不等于指令可删除；还必须确认没有副作用和异常语义。
* **IR 与 bytecode**：IR 更服务分析/变换，bytecode 更服务具体 VM 执行；两者抽象目标不同。
* **Operand stack 与 call frame**：operand stack 保存当前计算临时值，frame 保存一次函数调用的持久执行状态。
* **Bytecode optimization 与 VM optimization**：前者在生成前减少/改写指令，后者改善 dispatch、representation、caching 等运行时机器本身。

本章结论
--------

优化与 bytecode 执行的稳定模型是 ``Proven IR Facts → Semantics-Preserving Simplification → Compact Bytecode → Frame/Stack VM``。优化必须建立在可证明事实上，bytecode 必须有明确栈效应和控制流，VM 则把这些编译期决策转成可观察的运行时行为。