第035章：Control Flow Evidence in Real Compiler Pipelines
========================================================

核心知识点
----------

* 在真实编译器中，控制流证据主要存在于 basic block、terminator、CFG edge、PHI/block argument、debug location 和 pass 前后 IR 差异中。
* 文本 IR 是最精确的基础证据：label 确定 block，terminator 确定 outgoing edge，PHI 或等价机制确定合流值来自哪个 predecessor。
* CFG 图适合确认路径形状，pass dump 适合定位哪次转换改变了 block、edge 和 value relation；最终语义仍应回到 IR 操作数和控制边验证。
* 优化可以删除、合并、拆分或重排 block，也可以把 diamond CFG 的 PHI 合流改写成 ``select`` 等无分支值选择。
* 不可达块删除、分支常量折叠、jump threading、block merge、loop canonicalization 都会改变 CFG 外观，但必须保持程序可观察语义。
* 优化后的源码调试并不保证一行源码对应一个 block 或一条机器指令；debug metadata 只能重建低层执行状态到源码位置的近似映射。

关键路径
--------

* 读取 IR 时先找 block label，再逐块读取 terminator，建立完整 CFG edge 集合。
* 对 merge block 检查 PHI 或 block argument，把每个 incoming value 与对应 predecessor 对齐。
* 比较 pass 前后 IR 时记录 block 数量、terminator、edge、PHI incoming pair、reachability 和 debug relation 的变化。
* 若分支被优化为 ``select``，验证条件与两侧候选值关系是否保持，而非只比较 block 数量。
* 若 block 被删除或合并，继续检查所有 predecessor、successor、PHI 和 dominance 事实是否同步更新。
* 调试优化后代码时，把“源码行跳跃、变量消失、单步顺序变化”还原到 CFG 改写、值替换和 debug location 的变化上。

概念辨析
--------

* CFG visualization 与 IR 不同：图展示路径轮廓，IR 才完整承载 terminator、操作数、类型和合流值关系。
* PHI 与普通赋值不同：PHI 的值由进入当前 block 的 predecessor edge 决定，是 SSA 的路径敏感合流机制。
* Control-flow simplification 与语义删除不同：block 或 edge 可以消失，只要其选择和结果关系被等价表示保留。
* Source-level control flow 与 optimized CFG 不同：优化器依据 IR 语义重写路径，最终图形无需保持源码中的 ``if`` 或局部变量形态。
* Debug location 与真实执行顺序不同：它是低层指令到源码位置的映射证据，不是源码结构仍被完整保留的证明。

本章结论
--------

真实编译器中的控制流应以 IR 证据为准。先从 label 和 terminator 重建 CFG，再用 PHI 或等价值选择解释数据合流，随后比较 pass 前后 block、edge 与 value relation；优化改变的是表示形状，正确性要求控制选择、值来源和可观察行为保持等价。
