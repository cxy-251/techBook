第093章：Operations, Regions, Attributes, and Types
====================================================

核心知识点
----------

* Operation 是 MLIR 的中心组织单元。它可以拥有 operands、results、attributes/properties、regions 和 successors，并通过 dialect 定义具体语义。
* Operation 同时承担计算、声明、容器、结构化控制流和目标指令等多种角色；统一点不是“它们都像指令”，而是它们都落在同一套可遍历、可验证、可重写的 IR 对象模型上。
* Operand 是已有 SSA value 的使用，result 是当前 operation 新定义的 SSA value。SSA use-def 关系贯穿不同 dialect，是 mixed-dialect IR 仍能统一分析的基础。
* 每个 SSA value 都带 type。Type 约束 operand/result 的合法组合，并为 verifier、pattern matching、conversion 和 lowering 提供静态证明边界。
* Region 是 operation 内部的嵌套程序容器，包含 blocks；block 又包含 operations，并可拥有 block arguments。
* Region 的语义由 enclosing operation 决定。函数体、``scf.if`` 分支、循环体、GPU kernel body、领域 graph body 都可以用 region 承载，但合法性规则不同。
* Region 使结构化控制流和领域嵌套能在 IR 中保留更久，而不是过早平坦化为 CFG；这给高层重写保留了直接结构证据。
* 内层 region 可以读取其可见作用域中的外部 SSA values；region 内部定义的值若要影响外层，通常需要通过 enclosing operation result、yield 或显式 block argument 关系传出。
* 多 block region 中，block arguments 承担传统 SSA ``phi`` 类似的合流职责。值通过 predecessor edge 显式传给 successor block arguments。
* Attribute 是编译期常量配置，例如 constant literal、comparison predicate、layout、symbol reference、array parameter、enum strategy。它不应承担需要运行时流动的动态值职责。
* ``arith.constant`` 很好地展示 attribute 与 SSA result 的区别：常量字面值是 operation 的编译期属性，产生的 SSA value 才进入后续 use-def graph。
* Type 与 attribute 都是静态事实，但职责不同：type 描述 value 的类别和约束，attribute 描述某个 operation/type 的固定参数或配置。
* Generic operation form 暴露 MLIR 统一骨架；custom assembly form 提高可读性。二者应映射到同一个 operation 语义对象。
* Operation verifier 先检查通用结构，再执行 dialect-specific 规则；rewriter 则在保持 SSA、type、region 和 block invariants 的前提下替换 operation。
* MLIR 的可扩展性来自“统一结构 + 可扩展语义”：基础设施不需要预先理解所有领域 op，只需让 dialect 把语义、接口和验证规则接入通用 operation model。

关键路径
--------

Operation 数据流：

::

   existing SSA values
   → operation operands
   → operation semantics
   → typed results
   → new SSA values
   → downstream uses

Region 值流：

::

   outer values
   → nested region/block
   → inner operations
   → yield / branch arguments
   → enclosing op result or successor block argument
   → outer continuation

结构验证：

::

   operation
   → check operand/result types
   → check attributes/properties
   → check region/block shape
   → check successors/value flow
   → run dialect-specific verifier
   → accept or reject IR

概念辨析
--------

* **Operation 与 instruction**：instruction 通常强调可执行动作；MLIR operation 还能表示函数、模块、循环、声明和领域结构。
* **Region 与 basic block**：region 是 block 的容器并由 enclosing op 定义语义；block 是 region 内的顺序 operation 单元。
* **Block argument 与 phi**：二者都表达控制流合流值；MLIR 常把 incoming values 显式绑定到 successor block arguments。
* **Attribute 与 SSA operand**：attribute 是编译期固定配置，operand 是可在 IR 数据流中变化和传递的 value。
* **Type 与 attribute**：type 约束 value 的静态类别，attribute 描述固定参数、策略或元数据。

本章结论
--------

MLIR 的核心对象模型可以压缩为 ``Operation + Typed SSA Values + Attributes + Nested Regions``。稳定阅读顺序是先拆 operation 的 operands/results，再看 types 和 attributes，最后进入 regions/blocks 与 successor 关系；这套统一结构让 verifier、rewriter 和 lowering 能在多个 dialect 之间共享同一基础设施。