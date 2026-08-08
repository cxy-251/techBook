第120章：Query Compilation, JIT, and Vectorized Execution
==========================================================

核心知识点
----------

* Physical plan 选定后，数据库仍要决定 CPU 以什么执行表示跑这些算子。解释式 executor、query compilation、JIT 与 vectorized execution 解决的是“算子机器怎样执行”，不是“计划选哪一个”。
* Interpreted execution 保留通用 plan-node/表达式结构，在运行时逐节点、逐 tuple 分发；优势是通用、易组合，代价是频繁函数调用、分支、类型检查和字段提取。
* Query compilation 把固定查询中的部分计划或表达式结构提前改写成专用循环或机器码，减少通用分发。
* Expression JIT 常先优化短而热的局部路径，例如 ``WHERE`` 谓词、projection、aggregate expression、hash-key 计算和 tuple deforming，而不必把整个数据库 executor 编译掉。
* JIT 是成本转移：用一次 compilation cost 换取后续大量重复求值的更低 CPU 成本。短查询可能因 JIT 更慢，长时间 CPU-bound 查询才更容易摊销。
* 编译后的表达式仍必须保持 SQL 的 NULL、三值逻辑、类型转换、collation、overflow/error 等语义；“机器码更直接”不代表可以跳过语言规则。
* Vectorized execution 把逐行处理改成批量处理，一次向算子传递一批 rows 或 column vectors，从而摊销 dispatch、改善 cache locality，并给 SIMD 提供更连续的数据。
* 数据库中的 vectorized execution 与 CPU SIMD 是不同层级：前者是 executor batch model，后者是机器指令级并行；二者可以叠加。
* Selection vector/bitmap 常用于记录一个 batch 中哪些行通过谓词，使后续算子只处理有效位置，减少分支和数据搬运。
* Column-oriented/compact batch layout 能让过滤、聚合和扫描更容易形成紧凑循环，但 batch size 过大也会增加 cache pressure 和中间状态。
* Plan quality 与 execution machinery 是两层独立变量：正确的 join order 仍可能被低效逐行解释拖慢，高效 JIT/vectorization 也无法挽救严重错误的基数估算和 join order。
* Runtime feedback 能把 actual rows、selectivity、spill、skew 等真实执行事实反馈给 adaptive execution、re-optimization 或后续统计更新。
* 自适应机制的核心是承认规划期估算可能失真，并在运行时以 guard、反馈、重选策略或重新优化修正执行路径。
* 数据库执行性能最终取决于 plan quality、operator implementation、data layout、cache behavior、JIT cost 与批处理粒度的共同作用。

关键路径
--------

解释式与编译式执行：

::

   physical plan
   → interpreted plan nodes + generic expression evaluator
   or
   → identify hot/fixed query fragments
   → generate specialized code
   → compile/JIT
   → execute query-specific loops

向量化执行：

::

   scan batch
   → load column/value vectors
   → evaluate predicates over batch
   → build selection vector
   → process surviving values in join/aggregate
   → emit next batch

运行时反馈：

::

   estimated rows/cost
   → execute plan
   → observe actual rows/skew/spill/time
   → compare estimate vs reality
   → adaptive choice / reoptimization / statistics update

概念辨析
--------

* **Plan optimization 与 query compilation**：前者选择执行算法与顺序，后者把已选计划的执行路径变成更高效代码。
* **JIT 与 vectorized execution**：JIT 改变代码表示，vectorization 改变数据处理粒度；两者可以同时使用。
* **Database vector 与 SIMD vector**：前者是一批 rows/column values，后者是 CPU 指令中的硬件向量 lane。
* **Compilation cost 与 execution saving**：JIT 是否值得取决于重复执行规模和可摊销程度。
* **Static plan 与 runtime adaptivity**：静态计划基于估算固定选择，自适应执行允许真实运行事实影响后续策略。

本章结论
--------

数据库执行后半段的稳定模型是 ``Physical Plan → Operator Machinery → JIT/Batching → CPU Execution → Runtime Feedback``。SQL 性能既取决于优化器是否选对计划，也取决于 executor 是否用足够紧凑的代码、批处理和数据布局把这个计划跑出来。
