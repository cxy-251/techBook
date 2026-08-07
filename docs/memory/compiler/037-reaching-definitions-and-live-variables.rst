第037章：Reaching Definitions and Live Variables
================================================

核心知识点
----------

* Reaching definitions 回答“当前读取可能来自哪些先前写入”；live variables 回答“当前保存的值未来是否还可能被读取”。二者都在 CFG 上传播集合事实，但方向、集合元素和用途不同。
* Definition 是一次明确写入，例如变量赋值、参数绑定、寄存器定义或 IR value 产生点。一个源码变量可以对应多个 definition。
* 某个 definition 能 reach 程序点，当且仅当存在一条 CFG 路径从定义点到该点，并且途中没有被同一对象的新 definition 覆盖。
* Reaching definitions 是典型 forward may analysis。``IN[B]`` 来自 predecessor ``OUT`` 的 union，``OUT[B] = GEN[B] ∪ (IN[B] - KILL[B])``。
* ``GEN`` 产生新 definition，``KILL`` 消除同一变量旧 definition。分支合流时多个来源都必须保留，因为任一路径都可能实际执行。
* Liveness 判断的是“当前值”而不是变量名是否存在。若当前值沿未来某条路径在再次定义前会被读取，则该变量/寄存器在此点 live。
* Live variables 是典型 backward may analysis。``OUT[B]`` 来自 successor ``IN`` 的 union，``IN[B] = USE[B] ∪ (OUT[B] - DEF[B])``。
* ``USE`` 表示 block 内在首次定义前就需要读取的值，``DEF`` 表示 block 内产生新值并覆盖旧值需求的定义。
* Reaching definitions 的集合元素通常是 definition identity；liveness 的集合元素通常是 variable/register/value identity。来源与未来需求不可混为同一事实。
* DCE 依赖 liveness 但不能只看 liveness：一个结果 dead 的指令如果有 store、I/O、volatile、atomic、异常或未知调用副作用，仍不能删除。
* Register allocation 关心 live range 重叠。多个值同时 live 会形成寄存器压力或 interference；某个 definition 是否到达 use 则帮助建立值来源关系。
* 指针和内存写入会让 ``KILL``/``DEF`` 边界依赖 alias/effect analysis。无法证明写入只影响单一对象时必须保守处理。

关键路径
--------

Reaching definitions：

::

   definitions in predecessors
   → union into IN
   → KILL overwritten definitions
   → GEN new definitions
   → OUT
   → propagate forward
   → fixed point

Liveness：

::

   future uses in successors
   → union into OUT
   → remove values redefined here
   → add USE before definition
   → IN
   → propagate backward
   → fixed point

优化使用：

::

   use site
   → query reaching definitions
   → identify possible value origins
   → query liveness of produced values
   → check side effects / aliasing
   → replace, keep, or delete safely

概念辨析
--------

* **Reaching definition 与 last textual assignment**：真正来源由 CFG 路径和覆盖关系决定，不能只找源码中最近一行赋值。
* **Live variable 与 initialized variable**：live 表示当前值未来仍有用途；initialized 表示当前读取是否合法，两者回答不同问题。
* **Definition identity 与 variable name**：同一个变量可有多个 definition；数据流分析通常必须区分具体写入点。
* **Forward 与 backward**：reaching definitions 从过去写入传播到未来 use；liveness 从未来 use 反推当前需要保留什么。
* **Dead value 与 removable instruction**：结果没人使用不等于指令可删除，还必须证明没有可观察副作用。

本章结论
--------

Reaching definitions 与 liveness 应按“值从哪里来”和“值还要去哪里”分别理解。前者沿 CFG 正向追踪可能写入来源，后者沿 CFG 反向追踪未来使用需求；两者结合后，编译器才有足够证据建立 use-def 关系、删除死计算并管理值生命周期。