第040章：Data Flow as the Basis of Optimization
===============================================

核心知识点
----------

* 优化表面是删指令、替换值、折叠分支和复用计算，真正的前提是数据流事实：值从哪里来、流向哪里、在哪些路径成立、是否仍 live、是否有副作用。
* Dead Code Elimination 的基本条件是“结果无后续用途 + 指令无可观察副作用”。Liveness/def-use 能证明结果 dead，effect model 决定指令是否可安全删除。
* ``store``、I/O、volatile、atomic、同步、可能抛异常或未知调用即使返回值无人使用，也不能仅凭 dead value 删除。
* Constant propagation 把已证明恒定的值沿 use-def/def-use 关系传播；constant folding 再把全常量 operation 直接求值。两者常连续触发更多优化。
* 跨分支传播常量时，合流点必须检查所有可达 incoming paths。只有每条路径都给出同一个常量，合流 value 才能获得 must-constant 事实。
* Common Subexpression Elimination 依赖 availability：等价表达式此前已经计算，且从旧计算到当前点之间操作数、内存状态和相关语义没有被破坏。
* 文本相同不是 CSE 的证明。整数/浮点语义、overflow flags、NaN、memory load、调用副作用、volatile 与 alias 都可能使两个看似相同表达式不可交换或不可复用。
* 控制流优化依赖值事实。常量条件可删除不可达分支；多个分支若产生同一合流值，diamond CFG 可能折叠成单一路径或 value selection。
* 一个优化产生的新事实会成为下一轮优化的输入。常量传播可能暴露死分支，CSE 可能产生 unused value，CFG 简化又可能提高后续分析精度，因此优化通常是 pass pipeline 而不是单次改写。
* Conservative approximation 是优化安全线。别名不清、调用 effect 未知、路径条件无法证明或值语义不完整时，应保留原计算而不是猜测等价。
* 优化证据通常来自多种分析组合：CFG/reachability、dominance、liveness、use-def、constant/range facts、alias/effect information 和 language/IR semantic flags。
* 数据流结果有生命周期。CFG 或 IR 被改写后，旧 reaching/liveness/availability 可能失效；pass 必须更新、重新计算或明确 invalidation。
* 优化正确性衡量的是可观察语义保持，而不是源码形状保持。局部变量、block、branch 和中间 value 都可以消失，只要返回值、副作用、异常和其它语言可观察行为仍等价。

关键路径
--------

Dead code elimination：

::

   root observable effects / return values
   → propagate liveness backward
   → find unused definitions
   → check side-effect and exception model
   → delete safe dead instructions
   → repeat because new dead values may appear

Constant propagation：

::

   discover constant fact
   → propagate through def-use graph
   → merge across CFG paths
   → fold constant operations
   → simplify branch / phi / select
   → rerun reachability and DCE

CSE / reuse：

::

   candidate expression
   → find dominating previous equivalent computation
   → prove operands unchanged
   → prove memory/effects compatible
   → replace new computation with old value
   → remove redundant instruction if now dead

概念辨析
--------

* **Dead value 与 dead instruction**：值没人用只是第一步；指令仍可能有副作用，因此不一定能删除。
* **Constant propagation 与 constant folding**：前者传播已知常量事实，后者执行可以在编译期求值的具体 operation。
* **CSE 与 textual deduplication**：CSE 需要值语义、支配和副作用证明，不是搜索重复源码字符串。
* **Optimization opportunity 与 optimization proof**：看起来可以简化只是候选，真正改写必须由分析事实证明安全。
* **Conservative failure 与 compiler bug**：证据不足而放弃优化只是损失性能；没有证据却改写则可能破坏程序语义。

本章结论
--------

现代优化应按“Data-Flow Fact—Control Path—Value Relation—Effect/Alias—Proof—Rewrite—Reanalysis”理解。大多数优化并不是先决定怎么改代码，再寻找理由；而是先通过数据流分析证明某个值、路径或表达式关系成立，然后才进行最小、语义保持的重写。