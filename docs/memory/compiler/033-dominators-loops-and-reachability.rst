第033章：Dominators, Loops, and Reachability
===========================================

核心知识点
----------

* Reachability 是第一层控制流事实：从 entry 沿 CFG 边能够到达的 block 才有当前函数中的执行机会。
* Dominance 表示必经关系：若从 entry 到 B 的每条路径都经过 A，则 A dominates B；每个可达 block 支配自己。
* Immediate dominator 是离目标最近的严格支配者；全部 ``idom`` 关系组成 dominator tree。
* CFG edge 表示“可能跳到”，dominator-tree edge 表示“最近必经”，两种边语义完全不同。
* Natural loop 通常由 ``latch -> header`` 的 backedge 识别，并要求 header 支配 latch。
* Loop header 是循环入口，latch 是把控制送回 header 的块，exit edge 是从循环区域离开的边。
* CFG 被改写后，reachability、dominator tree 和 loop info 都可能失效，必须重新计算或显式更新。

关键路径
--------

* 从 entry 开始遍历 CFG，先标记全部 reachable block，并过滤脱离主图的不可达区域。
* 对非入口 block，支配集合可理解为“所有前驱支配集合的交集，再加当前 block”。
* 从完整支配关系中选择最近严格支配者，构造 dominator tree。
* 检查每条可能回向前部的边 ``latch -> header``；若 header 支配 latch，则该边是自然循环 backedge。
* 从 latch 沿 predecessor 反向收集直到 header，可得到 natural loop 的核心区域。
* 后续 SSA、代码移动、循环优化和公共子表达式消除都依赖这些图事实判断定义覆盖与合法移动范围。

概念辨析
--------

* Reachability 与 path feasibility 不同：前者只看图上是否有路，后者还要求路径条件能够成立。
* Dominance 与源码先后不同：源码写在前面并不保证支配，支配必须由所有入口路径证明。
* Dominator tree 与 CFG 不同：CFG 描述控制转移，dominator tree 压缩必经关系。
* Backedge 与任意向后跳转不同：自然循环识别要求目标 header 支配来源 latch。
* Loop header 与 loop body 不同：header 是循环区域的统一入口证据，body 是被回边和支配关系包围的执行区域。

本章结论
--------

控制流分析应按“可达性 → 支配关系 → immediate dominator → backedge → natural loop”的顺序推进。Reachability 先确定分析对象，dominance 提供必经保证，dominator tree 压缩查询结构，回边再把重复执行区域识别为循环。
