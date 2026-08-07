第039章：Forward vs Backward Data Flow Analysis
===============================================

核心知识点
----------

* 数据流分析首先要确定两个独立维度：事实传播方向，以及路径合流后事实代表 may 还是 must。
* Forward analysis 从 predecessor 向 successor 传播，适合回答“此前发生的定义、计算或状态变化能否影响当前点”。Reaching definitions、available expressions、constant propagation 都属于这一类。
* Forward analysis 通常先合并 predecessor 的 ``OUT`` 得到当前 ``IN``，再应用 transfer function 生成新的 ``OUT``。
* Backward analysis 从 successor 向 predecessor 传播，适合回答“未来哪些 use、return、branch 或资源需求要求当前点保留什么”。Liveness 是典型例子。
* Backward analysis 通常先合并 successor 的 ``IN`` 得到当前 ``OUT``，再反向穿过当前 block 计算 ``IN``。
* May analysis 表示“至少存在一条路径使事实成立”；must analysis 表示“所有相关路径都使事实成立”。方向和 may/must 互不等价。
* Reaching definitions 是 forward may：任一路径到达的定义都要保留，合流常用 union。
* Live variables 是 backward may：任一未来路径可能读取的值都要保留，合流常用 union。
* Available expressions 是 forward must：只有所有前驱路径都已经计算且没有破坏的表达式才能视为可用，合流常用 intersection。
* Very busy expressions 是 backward must：只有所有后继路径都会在操作数被改写前计算的表达式才能保留，合流常用 intersection。
* Meet/join operator 的本质是路径事实合并规则。具体教材可能因 lattice 排序使用不同术语，工程判断应回到“合流后保留并集还是共同事实”。
* 初始化值必须与分析语义匹配。May 与 must、union 与 intersection、top 与 bottom 的选择共同决定 fixed-point 迭代是否得到正确结果。
* 循环会让 forward 与 backward 分析都产生递归依赖，因此两种方向都通常需要 worklist 求 fixed point，而不是简单按文本方向扫描一次。
* 把 may 事实误当 must 证据会产生错误优化；把 must 问题过度保守地按 may 处理通常不会破坏正确性，但会损失优化机会。

关键路径
--------

选择分析方向：

::

   define target fact
   → ask whether fact depends on past causes or future needs
   → past causes: forward
   → future needs: backward
   → define transfer function

选择合流语义：

::

   ask whether one path is enough or every path is required
   → one path enough: may
   → every path required: must
   → choose union/intersection or equivalent lattice operator
   → verify conservative meaning

通用 fixed-point 框架：

::

   initialize facts
   → merge neighbors in chosen direction
   → apply transfer
   → detect change
   → enqueue affected CFG neighbors
   → converge

概念辨析
--------

* **Forward 与 may**：forward 只描述传播方向，不代表一定是 may；available expressions 就是 forward must。
* **Backward 与 must**：backward 只描述依赖未来，不代表一定是 must；liveness 是 backward may。
* **Union 与 may**：集合分析中常对应 may，但在不同 lattice 排序下术语可能变化，应以事实语义为准。
* **Intersection 与 must**：它保留所有路径共有事实，适合需要“必然成立”证据的优化。
* **Path existence 与 proof strength**：存在一条路径只能支撑可能性；安全代码移动和复用通常需要更强的全路径证明。

本章结论
--------

数据流分析应先回答“事实来自过去还是未来”，再回答“任一路径成立是否足够”。Forward/backward 决定传播方向，may/must 与合流规则决定证明强度；这两个维度组合后，编译器才能把 CFG 上的多路径状态压缩成可用于优化的安全事实。