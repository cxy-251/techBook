第060章：Parallelism, Dependence Analysis, and Safety
=====================================================

核心知识点
----------

* 循环并行化的核心不是“循环看起来规则”，而是不同迭代是否能同时执行、乱序执行或分组执行而不改变程序语义。
* Loop-carried dependence 表示一次迭代依赖另一迭代产生的值。只要存在必须保持的跨迭代边，对应操作就不能任意并行。
* 真依赖（RAW）最直接限制并行：第 ``i`` 次迭代读取第 ``i-1`` 次写入的值时，迭代间存在明确先后关系。
* WAR/WAW 也会限制重排，尤其当多个迭代可能访问同一内存位置时；alias analysis 决定这些关系能否被排除。
* Dependence distance 描述 producer 与 consumer 相隔多少次迭代。距离和方向可用于判断 vectorization、pipeline、tiling 或其它重排是否可行。
* 规则数组访问常可表示为 ``base + i*stride + offset``，编译器据此分析不同迭代是否可能命中同一地址；间接索引和未知指针会显著降低精度。
* MayAlias 意味着“无法证明独立”，因此不能直接并行；它不等于运行时一定冲突。
* Reduction 是结构化跨迭代依赖。sum/min/max/bitwise 等可在满足结合性、交换性及语言数值语义时改写为 partial reductions。
* 浮点 reduction 是否可重排取决于舍入、NaN、signed zero、异常和 fast-math/语言许可；数学上可结合不代表 IR 中自动可结合。
* Recurrence 与 reduction 要区分。``dst[i] = dst[i-1] + x`` 是一般递推链；``sum += x[i]`` 的目标是聚合多个贡献，后者通常有更明确的并行化重构方式。
* 静态证明不足时，可以做 runtime versioning：运行时检查 pointer ranges、alignment、trip count 等，满足条件走并行/向量快路径，否则回退原始顺序路径。
* Runtime check 只解决合法性缺口，不保证收益。检查、分支、双版本代码和 fallback 都进入 cost model。
* 并行安全还必须尊重 side effects、volatile、atomic、fence、异常和语言内存模型；证明数组下标独立并不等于所有操作都可并行。
* 编译器并行化的底线是“已证明独立，或已把依赖安全重构”。任何未知依赖都应保留原顺序。

关键路径
--------

依赖分析：

::

   loop body accesses
   → classify reads/writes
   → derive address functions
   → query alias / overlap
   → find cross-iteration RAW/WAR/WAW edges
   → compute distance/direction
   → decide legal reorder/parallel form

Reduction 识别：

::

   loop-carried scalar phi/value
   → detect associative reduction pattern
   → verify operation semantics allow regrouping
   → create partial accumulators
   → process iterations in parallel/vector lanes
   → combine partial results

Speculative fast path：

::

   static proof insufficient
   → generate runtime alias/range/alignment checks
   → condition true: optimized parallel/vector loop
   → condition false: original scalar/sequential loop
   → merge outputs

概念辨析
--------

* **Loop-carried dependence 与 loop-local dependence**：前者跨迭代限制整体并行，后者只要求单次迭代内部保持顺序。
* **Dependence distance 与 trip count**：distance 描述依赖跨几轮，trip count 描述循环总共执行多少轮。
* **Reduction 与 recurrence**：reduction 可按代数结构重新分组；一般 recurrence 往往必须保留逐轮传播。
* **MayAlias 与 dependence proof**：MayAlias 表示不能排除冲突，因此还没有并行化所需的独立性证明。
* **Runtime speculation 与 unsafe optimization**：speculation 通过 guard 保证快路径只在条件成立时执行，不是无证明地直接重排。

本章结论
--------

循环并行化应按“Access Pattern—Alias—Dependence Edge—Distance—Structured Reduction—Runtime Guard”理解。编译器只有在证明迭代独立，或能把依赖重构成 reduction 等安全形式时，才能改变执行顺序；证据不足时，保留原顺序或生成受运行时检查保护的快路径才是正确策略。