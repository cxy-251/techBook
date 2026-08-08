第116章：SQL as a Declarative Source Language
===============================================

核心知识点
----------

* SQL 更接近数据库编译器的声明式源语言：用户描述需要什么结果，数据库决定怎样扫描、连接、聚合、排序和访问存储。
* 查询语义与执行策略必须分离。``SELECT``、``FROM``、``WHERE``、``JOIN``、``GROUP BY``、``HAVING``、``ORDER BY`` 描述结果约束，不直接规定物理执行顺序。
* 优化器的自由来自结果等价。只要行集合、列值、重复行、NULL 语义、聚合与排序要求保持不变，底层可以选择不同访问路径、join order 和算法。
* SQL 文本会被拆成更稳定的逻辑对象：relation、predicate、expression、projection、group key、aggregate、sort key。
* ``WHERE`` 与 ``HAVING`` 都是过滤，但作用层级不同：前者通常过滤输入行，后者过滤聚合后的分组结果。
* Join predicate 与普通 filter predicate 也要区分；前者定义关系匹配，后者缩小单个输入或中间结果。
* SQL 的书写顺序不等于执行顺序。优化器可以在合法范围内下推谓词、重排内连接、复用已有排序或选择不同聚合方式。
* 外连接、窗口函数、``LIMIT``、volatile function、锁定语义等会收紧等价改写空间，优化自由始终受语义边界约束。
* 不同 SQL 文本可能表达同一逻辑查询；优化器关心的是绑定后的查询含义与逻辑等价关系，不是源码表面形状。
* SQL 因此可以看成 dataflow compiler 的源码：数据库把关系意图逐步编译成逻辑计划、候选计划和可执行数据流。

关键路径
--------

查询编译主链：

::

   SQL text
   → parse tree
   → bound query
   → logical relations/predicates/expressions
   → logical plan
   → equivalent plan alternatives
   → physical plan
   → executor dataflow

语义拆解：

::

   FROM/JOIN → input relations + join predicates
   WHERE → row predicates
   SELECT → projection expressions
   GROUP BY → grouping keys
   HAVING → post-aggregate predicate
   ORDER BY → required output ordering

概念辨析
--------

* **SQL text 与 query meaning**：文本是源码表面，绑定后的关系、谓词和表达式才是优化器需要保持的语义对象。
* **Declarative 与 no execution order**：声明式不表示没有执行顺序，而是执行顺序由优化器生成，不由源码逐步指定。
* **Logical equivalence 与 same text**：不同文本可以逻辑等价；优化器依赖等价规则，而非字符串匹配。
* **WHERE 与 HAVING**：前者主要作用于聚合前的行，后者作用于分组/聚合后的结果。
* **Logical query 与 physical plan**：前者说明要计算什么关系结果，后者说明用什么算法和访问路径得到结果。

本章结论
--------

SQL 的稳定模型是 ``Declarative Result Semantics → Logical Relations/Predicates → Optimizer Freedom → Executable Dataflow``。数据库优化器之所以能重排连接、选择索引和替换算法，前提是 SQL 先把“结果是什么”和“怎样得到结果”分离开来。
