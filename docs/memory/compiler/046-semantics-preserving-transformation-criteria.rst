第046章：Semantics Preserving Transformation Criteria
=====================================================

核心知识点
----------

* 优化是对程序表示的重写，不是对源码外观的保持。合法性标准是：对源程序所有定义良好的执行，目标表示必须保留当前语言或 IR 所要求的可观察语义。
* 每个优化都应视为 ``source pattern + preconditions -> target pattern``。模式匹配只能发现候选，真正允许改写的是前提被证明成立。
* 可观察行为是优化正确性的边界，通常包括返回值、I/O、内存副作用、``volatile``、atomic/synchronization、异常、trap、外部调用以及语言规定的其它可观察状态。
* 删除中间 SSA value、合并 basic block、重排普通算术都可以合法，只要没有改变可观察行为，也没有给原本定义良好的输入引入新 UB、异常或 trap。
* Undefined Behavior 扩大了优化器可假设的空间，但只覆盖源程序已经进入未定义域的执行。不能把某条局部路径上的 UB 前提错误提升为所有路径都成立的事实。
* ``poison``、``undef``、integer overflow flags、fast-math flags 等 IR 语义会改变代数变换是否合法。数学等式成立，不代表 IR 变换自动成立。
* ``volatile`` 访问自身具有必须保留的可观察性；atomic 和 fence 还受并发内存模型约束。普通 load/store 的移动也要考虑 alias 与调用副作用。
* 可能抛异常或产生 trap 的 operation 不能随意 speculative execute。把操作移动到更宽的执行域，需要证明新增路径上执行它仍然安全。
* 浮点优化不能默认使用实数代数律。NaN、无穷大、舍入、符号零和浮点环境都会限制重排；只有明确语义许可后才能应用更激进等价关系。
* 证据不足时保留原 IR 是优化器的正确行为。Conservative refusal 损失的是性能机会，错误证明损失的是程序正确性。
* 优化粒度可以从 basic block、function、loop 扩展到 module、LTO/whole-program。粒度越大，可用上下文越多，同时证明成本、编译时间和失效管理也越复杂。
* 任何 transform 提交后都应重新满足当前 IR verifier、不变量、dominance、CFG、type 与 effect 约束；“结果看起来更简单”不是正确性证据。

关键路径
--------

优化合法性判断：

::

   source IR
   → identify candidate rewrite
   → list observable behaviors
   → list semantic preconditions
   → query type/range/dominance/alias/effect facts
   → prove all preconditions
   → build target IR
   → verify invariants and observable equivalence

代码移动：

::

   operation at original control region
   → inspect trap/exception/effects
   → determine original execution domain
   → determine proposed execution domain
   → prove no new defined path executes unsafe behavior
   → move or conservatively keep

内存改写：

::

   load/store/call candidate
   → alias + memory-effect facts
   → volatile/atomic/order constraints
   → exception and concurrency constraints
   → prove preserved memory observations
   → transform

概念辨析
--------

* **语义保持与源码形状保持**：优化可以彻底改变源码对应结构，只需保持规定的程序含义。
* **候选优化与合法优化**：模式相似只产生候选；前提证明才产生合法改写。
* **Undefined behavior 与 compiler freedom**：UB 只让源程序未定义的执行失去保证，不能改变其它定义良好的输入。
* **数学等价与 IR 等价**：IR 还携带位宽、overflow、poison、floating-point、memory 和 effect 语义。
* **Conservative refusal 与优化失败**：缺少证据而不改写是正确策略，不是编译器错误。

本章结论
--------

优化的基本合同是“先证明，后重写”。正确的 transform 必须同时满足值等价、控制流执行域、内存与副作用、异常/UB、类型和当前 IR 不变量；只要其中一项没有可靠证据，最安全且正确的结果就是保留原表示。