第119章：Physical Operators and Execution Plans
================================================

核心知识点
----------

* Physical plan 是查询在 executor 中的可执行表示。它把逻辑 Scan/Join/Aggregate/Sort 绑定成具体访问路径、算法、数据结构和执行顺序。
* 叶子节点决定数据怎样进入执行树：Sequential Scan、Index Scan、Bitmap Scan、column scan、remote scan 等都属于 access path。
* Seq Scan 适合命中比例高、表较小或连续读取更划算的场景；Index Scan 适合高选择性查找或可复用索引顺序；Bitmap Scan 适合中等命中比例和多个索引条件组合。
* 同一个 ``WHERE`` 谓词在物理计划中可能落到 ``Index Cond``、``Filter``、``Recheck Cond`` 或 ``Join Filter``，谓词落点直接影响真实执行成本。
* Nested Loop、Hash Join、Merge Join 都是 Join 的物理实现。前者适合小外层加高效内层查找，Hash Join 适合大规模等值连接，Merge Join 适合有序输入或排序可复用的场景。
* Hash Join 通常分 build/probe 两侧；build side 的规模与内存决定是否能完全驻留，过大时可能 spill 或分批。
* Merge Join 依赖连接键有序；已有索引顺序或前序 sort 可以降低其准备成本。
* Sort、HashAggregate、Materialize 等节点可能是 blocking operator：需要消费大量甚至全部输入后才能稳定地产生输出。
* 经典 executor 常以 plan-node tree 运行。父节点请求下一行，子节点按需产生 tuple，形成 demand-pull / iterator-style execution。
* 数据流方向与调用方向相反：tuple 从叶子向根流动，而执行请求通常从顶层节点向下传播。
* ``EXPLAIN`` 中 cost/rows/width 是优化器预测；``EXPLAIN ANALYZE`` 中 actual rows/loops/time/buffers 才反映真实执行。
* ``loops`` 很重要：一个内层 Index Scan 单次很快，如果被 Nested Loop 调用数十万次，总成本仍可能巨大。
* Physical plan 是“由数据算子组成的程序”。它决定 tuple 如何流过扫描、连接、聚合、排序、限制和物化边界。

关键路径
--------

计划执行：

::

   top-level result node requests rows
   → parent requests child output
   → leaf access path reads base data
   → filters produce candidate tuples
   → join combines tuple streams
   → aggregate/sort/materialize process intermediates
   → root returns final rows

Access path 判断：

::

   predicate + table/index metadata
   → estimate selectivity
   → Seq Scan / Index Scan / Bitmap Scan alternative
   → compare I/O + random access + ordering benefit
   → choose concrete scan node

概念辨析
--------

* **Logical operator 与 physical operator**：Logical Join 说明关系语义，Hash Join/Nested Loop 才说明算法。
* **Index Cond 与 Filter**：前者参与定位候选行，后者通常在行已经读取后再判断。
* **Dataflow 与 control flow**：tuple 自底向上流，pull-style 调用请求自顶向下传播。
* **Blocking 与 streaming operator**：前者需要积累大量输入后才能输出，后者可以边消费边产生结果。
* **Estimated rows 与 actual rows**：前者来自规划期统计，后者来自真实运行；两者差距直接影响计划诊断。

本章结论
--------

物理计划的稳定模型是 ``Access Paths + Concrete Operators + Tuple Flow + Runtime Evidence``。读慢查询时应从叶子确认数据怎样进入计划，再看 join/aggregate/sort 的算法与阻塞边界，最后用 actual rows、loops、buffers 和估算偏差解释真实成本。
