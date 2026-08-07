第036章：Program Facts and Fixed-Point Thinking
===============================================

核心知识点
----------

* Program fact 是编译器在某个程序点计算出的静态知识，例如“哪些定义可能到达这里”“哪些值未来仍会使用”“哪些表达式在所有路径上都可复用”“某变量是否已经初始化”。
* Fact 必须绑定到程序点与问题域。``block.in``、``block.out``、instruction 前后可以拥有不同事实；同一程序也可以同时运行 reaching definitions、liveness、available expressions 等不同分析。
* 数据流分析把运行时无数可能路径压缩成有限事实域。集合、布尔状态、区间或抽象 lattice 都可以成为事实表示，前提是分析能够有限收敛并保持安全近似。
* Fact 沿 CFG edge 传播。前驱的 ``OUT`` 进入后继的 ``IN``；分支合流时按分析语义使用 union、intersection 或其它 meet/join 规则合并路径事实。
* Transfer function 描述当前 block 如何把入口事实改写成出口事实。经典 reaching definitions 可写成 ``OUT = GEN ∪ (IN - KILL)``。
* ``GEN`` 表示当前 block 产生并能流出的事实，``KILL`` 表示当前 block 使旧事实失效的集合。赋值通常生成新定义并杀死同一变量旧定义。
* 循环使事实产生递归依赖：header 的输入依赖 latch 输出，latch 输出又依赖 header 输入，因此一次线性扫描通常不够。
* Fixed point 是分析收敛状态：继续按同一传播和 transfer 规则迭代，所有 ``IN/OUT`` 都不再变化。此时事实才可以作为后续优化与诊断的稳定输入。
* Worklist 是常见求解方式：初始化事实，将受变化影响的 block 放入队列，重新计算其输出；若结果变化，再把相关 successor 或 predecessor 入队，直到队列为空。
* May analysis 往往从“无事实”开始逐步增加可能性；must analysis 常从较强的初始假设开始逐步收缩。初始化策略必须与 lattice 和合流规则一致。
* 保守近似是正确性的底线。证据不足时，优化分析宁可保留更多可能性或放弃改写，不能把“未知”错误当成“安全”。
* 指针、别名、函数调用和内存副作用会降低 transfer function 精度。此时必须借助 alias/effect analysis，或扩大 KILL/unknown 集合保持安全。

关键路径
--------

数据流求解：

::

   CFG + fact domain
   → initialize IN/OUT
   → merge predecessor/successor facts
   → apply transfer function
   → compare old/new facts
   → enqueue affected blocks
   → repeat until fixed point

Reaching-definition 型更新：

::

   predecessor OUT sets
   → union into block IN
   → remove KILL definitions
   → add GEN definitions
   → produce block OUT
   → propagate along CFG edges

循环中的收敛：

::

   entry facts
   → loop header
   → loop body transfer
   → backedge returns new facts
   → header merge changes
   → iterate
   → no fact changes

概念辨析
--------

* **Program fact 与 runtime state**：fact 是编译期对所有相关路径的抽象结论，不是某次实际执行时的具体状态。
* **CFG edge 与 data-flow edge**：CFG edge 表示控制可能转移；数据流框架借这些边传播抽象事实。
* **Transfer function 与 merge function**：前者描述单个 block 对事实的局部改写，后者描述多条路径如何合并。
* **Fixed point 与 single pass**：无回边的简单图可能一次传播就稳定；一般 CFG 尤其循环需要反复迭代。
* **Precision 与 correctness**：更精确能带来更多优化机会，保守结果仍可正确；错误地过度确定则会破坏语义。

本章结论
--------

数据流分析应按“Fact Domain—CFG Edge—Merge—Transfer—Iteration—Fixed Point”理解。编译器不是模拟一次具体执行，而是把所有相关路径压缩成可查询静态知识；只有事实在 CFG 上传播并收敛后，后续优化和诊断才拥有稳定、可证明的依据。