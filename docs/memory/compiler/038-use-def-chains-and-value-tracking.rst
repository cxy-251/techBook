第038章：Use-Def Chains and Value Tracking
==========================================

核心知识点
----------

* Definition 是值产生点，use 是某条 operation 读取该值的具体 operand 位置，value identity 用来区分不同计算结果。源码变量名不能替代 IR 中的值身份。
* Def-use chain 从定义出发列出所有 users，回答“这个值流向哪里”；use-def chain 从使用点反查 producer，回答“这个操作数来自哪里”。
* 在非 SSA 表示中，一个 use 可能对应多个 reaching definitions，因此 use-def 来源是集合；在 SSA 中，寄存器式 value 通常有唯一 producer。
* 分支合流会把多个路径来源压缩成新的值身份。``phi`` 或 block argument 记录 predecessor-specific incoming values，后续 use 只读取合流后的新 value。
* Def-use edge 描述值依赖，CFG edge 描述控制可达。二者必须同时成立：某个值可以作为某条 operation 的输入，不代表每条控制路径都会实际选择该来源。
* 支配关系约束跨 block 的直接 value use。普通 SSA definition 必须在所有到达 use 的路径上可用；无法满足时需要 ``phi``、block argument 或其它路径合流表示。
* Def-use list 让 DCE 可以快速识别没有 users 的纯计算，也让统一替换能从一个 definition 直接修改所有 use sites。
* Use-def 查询支撑 constant propagation、copy propagation、value folding 与诊断：先定位 operand，再找到 producer，必要时继续穿过 ``phi``、cast、copy 等节点追踪来源。
* Value tracking 可以选择追到不同层级。某些分析停在 ``phi`` 的合流值即可，某些分析需要继续枚举每个 incoming definition 和路径条件。
* 内存值比寄存器 SSA 值复杂。``load`` 的来源可能是多个 ``store`` 或调用副作用，需要 alias analysis、MemorySSA、effect summary 等机制建立近似 use-def 关系。
* 替换一个 value 前不仅要证明结果等价，还要检查 type、poison/undef、overflow、floating-point flags、memory effects 和 dominance 等 IR 语义约束。
* 优化器真正操作的是“值图 + 控制流图”。值来源与用途越显式，删除、替换、合并和移动代码的证明成本越低。

关键路径
--------

从 use 追来源：

::

   locate operand use
   → read value identity
   → find defining operation
   → if phi/block argument, inspect incoming values
   → combine with predecessor/control conditions
   → continue until required origin is reached

从 definition 追用途：

::

   definition
   → enumerate users / use sites
   → classify each consuming operation
   → check control-flow reachability and dominance
   → replace / fold / preserve
   → update all use lists consistently

内存值追踪：

::

   load / memory use
   → alias set
   → possible reaching stores/calls
   → memory-version relation
   → path/effect filtering
   → conservative origin set

概念辨析
--------

* **Def-use 与 use-def**：前者从 producer 看 consumers，后者从 consumer 看 producer；是同一值关系的两个查询方向。
* **Variable identity 与 value identity**：变量可以反复赋值，IR value 通常代表某一次具体计算结果。
* **CFG edge 与 value-flow edge**：控制边说明路径可能执行，值边说明 operand 依赖哪个结果。
* **SSA producer 与 memory producer**：SSA 寄存器值通常有唯一定义；内存 load 可能对应多个 store，需要额外分析。
* **Textual similarity 与 value equivalence**：两段表达式写法相同不代表可以直接替换，仍需 IR 语义和路径证据。

本章结论
--------

值追踪应按“Definition—Value Identity—Use—CFG/Path—Replacement Evidence”理解。Use-def 与 def-use chain 把值来源和用途从源码名字中剥离出来，变成优化器可直接查询的图关系；SSA 让寄存器值关系更明确，而内存则需要额外的别名与副作用模型。