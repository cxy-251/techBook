第117章：Parsing, Binding, and Logical Query Plans
===================================================

核心知识点
----------

* SQL 编译前半段的核心链路是 ``text → query tree → bound query → rewritten query → logical plan``。
* Parser 负责把 token stream 组织成 SQL 结构，识别 ``SELECT``、``FROM``、``JOIN``、``WHERE``、``GROUP BY``、``ORDER BY`` 等子句；它只确认语法形状，不确认数据库对象身份。
* Binding/analyzer 把表名、列名、函数名和类型绑定到 catalog 中的真实对象，同时建立查询块作用域、别名、类型与隐式转换规则。
* 语法正确但列不存在、名字歧义、函数重载无法解析、类型不兼容等问题属于 binding/semantic 阶段，而不是 parsing 阶段。
* Query rewriting 在保持逻辑结果的前提下展开 view、规整子查询、应用规则或把表达式变成更统一的逻辑形式。
* View expansion 不是简单文本替换。展开后仍要保持列映射、类型、权限、NULL 与重复行等语义。
* Logical plan 用关系代数风格算子表达查询含义，常见节点包括 Scan、Filter、Join、Aggregate、Sort、Project。
* Logical Scan 只表示“需要读取某个关系及其列”，还没有决定 Seq Scan、Index Scan、column scan 或 remote scan。
* Logical Join 只表示关系匹配条件，还没有决定 nested loop、hash join 或 merge join。
* Logical plan 的价值是把 SQL 表面结构压缩成可重写的数据流表示，使谓词下推、join reorder、projection pruning 等优化有统一对象可操作。
* 不同数据库会把 rewrite 与 logical optimization 的边界划分得不同；稳定判断标准是：只要还未绑定具体物理算法，就仍处于逻辑语义层。
* Binding 是 SQL 从通用文本变成“当前数据库实例中的具体程序”的关键时刻，因为 catalog、schema、类型与权限都在这里进入查询含义。

关键路径
--------

前端链路：

::

   SQL text
   → lexer/parser
   → query tree
   → catalog lookup + name resolution
   → type/function binding
   → query rewriting / view expansion
   → logical operator tree
   → physical optimization

Logical plan：

::

   base relations
   → Scan
   → Filter predicates near their dependencies
   → Join related relations
   → Aggregate by group keys
   → Sort if ordering required
   → Project final expressions

概念辨析
--------

* **Parsing 与 binding**：parsing 确认语法结构，binding 确认名字在当前 catalog 中究竟指向什么对象并补齐类型语义。
* **Query tree 与 logical plan**：query tree 更接近 SQL 子句结构，logical plan 更接近关系数据流。
* **View 与 base table**：视图在源码中像关系名，但逻辑重写后可能展开成底层查询子图。
* **Logical operator 与 physical operator**：Logical Join/Scan 说明语义，Hash Join/Index Scan 才是具体执行算法。
* **Rewrite 与 optimization**：二者都可能改变表示；rewrite 更强调语义规整，optimization 进一步围绕等价计划与成本做选择。

本章结论
--------

SQL 前端的稳定模型是 ``Syntax → Binding → Rewriting → Logical Dataflow``。真正让查询进入优化器世界的不是 parser 本身，而是 binding 把名字和类型落到 catalog，再由 logical plan 把查询整理成可重写的关系算子图。
