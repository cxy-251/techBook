第055章：Optimization Under Memory Uncertainty
===============================================

核心知识点
----------

* 内存优化的首要问题不是“两个表达式看起来是否相同”，而是“中间是否存在任何可能改变目标内存位置的操作”。
* 当两个访问只有 ``MayAlias`` 结论时，优化器必须保留潜在依赖。证据不足时重复 load、保留 store 或放弃 code motion 都属于正确的保守行为。
* Load elimination 要求当前 ``load`` 与旧值来源读取同一内存版本；中间任何可能 clobber 该位置的 store、call、atomic 或未知 effect 都会阻止复用。
* Store forwarding 要求前序 ``store`` 与后序 ``load`` 访问同一地址范围，写入覆盖完整读取范围，中间没有覆盖写入，且读取不是 volatile/atomic 等特殊访问。
* ``MustAlias`` 可以提供“同一位置”的强证据，但仍要检查大小、对齐、字节范围和中间 clobber；它不会自动保证 forwarding 合法。
* ``NoAlias`` 可解除不相关 memory operation 的依赖，使 load hoisting、store sinking、LICM、vectorization 和并行化获得更多自由。
* Code motion 对内存比纯计算更严格。移动一条 ``load`` 时既要证明地址/操作数可用，还要证明移动路径上没有改变该位置的写入，也没有新增 trap、异常或可观察访问。
* 循环不变 load 只有在循环体内没有可能写入同一位置时才能 hoist。``p`` 与 ``q`` 可能别名时，循环中的 ``store *p`` 会阻止 ``load *q`` 外提。
* 把 memory operation 移到更宽执行域还要检查 speculative safety。原来只在条件分支内执行的 ``load`` 不能因为值看似不变就无条件提前。
* Memory barrier、atomic 和 fence 会建立更强顺序边界。优化器不能只依据普通 alias 关系跨越这些操作重排访问。
* 并发语义中，合法重排还受 language memory model、memory order、happens-before 和 data-race 规则约束；单线程等价不足以证明并发等价。
* MemorySSA/ModRef/alias results 等机制的价值在于缩小“可能 clobber”集合，让优化器从全局保守逐步收紧到局部可证明。
* ``restrict``、noalias、readonly/readnone、内联和过程间分析都能增强内存事实，但这些契约必须真实，否则优化器会基于错误前提产生 miscompilation。
* 内存优化的正确策略是证据驱动：强事实允许消除和重排，弱事实则保留原执行顺序。

关键路径
--------

Load elimination：

::

   current load
   → identify address/range
   → find dominating prior load/store
   → query alias for all intermediate memory defs
   → find clobbering access
   → no clobber + compatible semantics?
   → replace load or keep it

循环外提：

::

   load inside loop
   → prove address loop-invariant
   → inspect every loop memory def/call
   → prove NoAlias or non-Mod for target location
   → check speculative safety / exceptions
   → hoist to preheader

并发与顺序：

::

   candidate reordering
   → classify ordinary / volatile / atomic / fence
   → inspect memory order and synchronization edges
   → verify observable order and happens-before
   → reorder only when semantics permit

概念辨析
--------

* **MayAlias 与 optimization failure**：MayAlias 只是没有独立性证明；保留原访问是正确输出，不是分析器失效。
* **Load elimination 与 CSE**：两者都复用旧值，但 load 还依赖隐藏内存状态和 clobber 证明。
* **Store forwarding 与 constant propagation**：forwarding 使用的是已证明的前序内存写入值，不要求这个值本身是常量。
* **Loop invariance 与 hoist legality**：地址/表达式不随迭代变化只是第一步；内存位置也必须在循环中保持未被修改。
* **Compiler reordering 与 hardware reordering**：两者由不同层执行，但都必须落在语言/IR 内存模型允许的行为集合内。

本章结论
--------

内存不确定性决定优化器必须有多谨慎。Load elimination、store forwarding 和 code motion 都要求先证明访问对象、可见 memory version、中间 clobber 与顺序约束；只要 alias、effect 或并发事实仍停留在“可能”，优化器就应保留依赖，而不是把未知误判成独立。