第118章：Cost-Based Optimization and Plan Search
=================================================

核心知识点
----------

* Cost-Based Optimization（CBO）的任务是在多个语义等价的候选计划中，选择预计执行成本最低的一个。
* 同一逻辑查询可能对应不同 scan path、join order、join algorithm、sort、aggregate、materialization 和 parallel strategy。
* 优化器首先需要 cardinality estimate：每个节点预计输出多少行。中间结果规模是后续 CPU、I/O、memory 和 network cost 的基础。
* Selectivity 表示谓词保留输入的比例。过滤条件越有选择性，越适合尽早缩小后续 join、sort 和 aggregate 的输入。
* Statistics 常包括表行数/页数、distinct count、most-common values、histogram、null fraction，以及描述多列相关性的扩展统计。
* 基数估算最难的问题之一是数据相关性。把强相关谓词错误地视为独立，会造成数量级级别的估算偏差。
* Join cardinality 会把早期估算误差放大。一个节点低估十倍，后续 join、sort、aggregate 的 cost 都可能被错误压低。
* Cost model 不等于真实毫秒，而是一套用于计划比较的内部尺度，通常综合 CPU tuple processing、page I/O、random access、memory、spill、network shuffle 等代价。
* Join-order search space 会随关系数量快速爆炸，优化器无法穷举所有排列，因此需要 dynamic programming、memoization、heuristics、genetic search 或搜索上限。
* Nested loop、hash join、merge join 没有绝对优劣，它们的成本取决于输入规模、索引、有序性、内存和数据分布。
* CBO 的正确性前提仍是语义等价；成本模型只在合法候选计划之间比较，不能用“更便宜”覆盖 SQL 语义。
* Statistics 是近似且会过期，参数化查询、数据倾斜、相关列、UDF 和运行时热点都会让优化器在不完美信息下决策。
* ``EXPLAIN ANALYZE`` 中 estimated rows 与 actual rows 的差距，是定位错误计划最重要的证据之一。
* Query optimization 本质是“在不完美知识下搜索”，而非一次确定性的代数化简。

关键路径
--------

成本优化：

::

   logical plan
   → enumerate legal physical alternatives
   → obtain table/column statistics
   → estimate predicate selectivity
   → estimate node cardinalities
   → estimate CPU/I/O/memory/network cost
   → search/prune candidate space
   → choose lowest-estimated-cost plan

估算错误传播：

::

   stale/skewed statistics
   → wrong predicate selectivity
   → wrong intermediate cardinality
   → wrong join order/algorithm
   → wrong memory/sort/spill assumptions
   → unexpectedly slow physical plan

概念辨析
--------

* **Cardinality 与 selectivity**：cardinality 是行数，selectivity 是过滤比例；后者常用于推导前者。
* **Cost 与 elapsed time**：cost 是优化器内部比较尺度，不等于真实运行时间。
* **Logical equivalence 与 physical alternatives**：逻辑等价定义候选范围，物理选择在这个范围内比较执行成本。
* **Statistics 与 runtime facts**：统计信息是规划期近似，真实数据量要到执行时才完全可见。
* **Search optimality 与 practical optimizer**：理论最优搜索空间可能不可承受，真实优化器必须在搜索质量与规划时间之间折中。

本章结论
--------

CBO 的稳定模型是 ``Equivalent Plans + Statistics → Cardinality Estimates → Cost Model → Bounded Search``。数据库优化器并不是“知道最快计划”，而是在有限统计与有限搜索预算下预测哪个合法计划最便宜；错误计划往往首先暴露为错误基数估算。
