第058章：Loop Unrolling, Fusion, Fission, and Tiling
=====================================================

核心知识点
----------

* Unrolling、fusion、fission 和 tiling 都直接改写循环形状：复制迭代、合并循环、拆分循环或重排迭代空间，而不是只替换一条局部指令。
* Loop unrolling 用代码体积换动态控制开销：一次循环体处理多个迭代，减少 branch、index update 和 backedge 次数，并暴露更多 ILP/SLP 机会。
* Partial/runtime unrolling 需要 remainder/epilogue loop 处理不能整除展开因子的尾部；full unrolling 只适合较小且 trip count 可确定的循环。
* 展开合法性依赖迭代语义仍被完整覆盖；收益则由 trip count、循环体大小、register pressure、I-cache 和 target cost model 决定。
* 展开因子越大不代表越快。额外 live values 可能造成 spill，代码膨胀也可能恶化 instruction cache 和解码带宽。
* Loop fusion 把相邻、迭代域兼容的循环合并，使 producer/consumer 更靠近，减少遍历次数并可能改善 cache locality。
* Fusion 必须保持依赖顺序。若第二个循环第 ``i`` 次迭代依赖第一个循环其它迭代产生的数据，简单逐 ``i`` 融合可能改变结果。
* Fusion 还要检查不同循环之间的副作用、异常、控制条件和别名，不能只因为边界相同就合并。
* Loop fission 把一个复杂循环拆成多个更简单循环，可隔离独立计算与依赖链、降低寄存器压力、改善向量化或缓存行为。
* Fission 会增加遍历次数和循环控制，因此它是否更好取决于依赖结构、working set、vectorization 和 target cost。
* Tiling/blocking 把大迭代空间切成小块，使一组数据在 cache 中被重复使用后再进入下一块，核心收益来自 locality 而非减少算术量。
* Tiling 会改变迭代顺序，因此必须证明跨迭代依赖允许这种重排；矩阵/tensor 代码常依赖 affine access/dependence analysis 做合法性判断。
* 这些循环变换经常互相创造机会：unroll 后可 SLP，fission 后可 vectorize，tiling 后可提高局部性，fusion 后可消除中间 load/store。
* 循环变换必须同时通过 legality 和 profitability：先证明保持语义，再用 profile、代码大小、cache、寄存器和目标机器成本判断是否值得。

关键路径
--------

Unrolling：

::

   canonical loop + trip-count information
   → choose unroll factor
   → clone body iterations
   → adjust induction / bounds
   → generate remainder path if needed
   → repair phi/CFG
   → evaluate code size and register pressure

Fusion / fission：

::

   identify loop iteration domains
   → analyze cross-loop / intra-loop dependencies
   → verify effects and control compatibility
   → merge or split bodies
   → rebuild induction/exit structure
   → rerun locality/vectorization analyses

Tiling：

::

   multi-dimensional iteration space
   → choose tile sizes
   → prove dependence-preserving reorder
   → create outer tile loops
   → create inner point loops
   → keep working set in cache
   → tune tile size for target

概念辨析
--------

* **Unrolling 与 vectorization**：展开复制标量迭代并减少控制开销；向量化把多个标量操作合并为 SIMD 操作。
* **Fusion 与 CSE**：fusion 改写循环边界和遍历顺序；CSE 主要复用等价值计算。
* **Fission 与 parallelization**：拆分本身不等于并行，但可能隔离依赖后创造并行/向量化机会。
* **Tiling 与 unrolling**：tiling 主要优化数据局部性，unrolling 主要减少控制开销并暴露调度空间。
* **Legality 与 profitability**：前者回答“能不能改”，后者回答“值不值得改”。

本章结论
--------

循环结构变换的核心是重排“迭代如何分组和执行”。Unrolling 改变每次循环处理的迭代数，fusion/fission 改变循环之间的边界，tiling 改变迭代空间的访问顺序；任何收益都必须建立在依赖与副作用证明之上，并由代码大小、寄存器和 cache 成本共同验证。