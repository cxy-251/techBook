第042章：Phi Nodes, Block Arguments, and Value Merging
======================================================

核心知识点
----------

* SSA 在分支合流处必须解决“当前值来自哪条路径”的问题。单个分支里的定义通常不能支配 merge block，因此需要新的合流 value。
* ``phi`` 在合流 block 开头定义新的 SSA value，并按刚执行过的 predecessor 选择对应 incoming value。
* ``phi`` 的每个 incoming pair 都绑定“value + predecessor”。缺少某个前驱输入会让该路径无值，多出非前驱输入则让 IR 与 CFG 不一致。
* ``phi`` 不是普通函数调用，也不是同时计算所有输入；输入值已经在各自前驱路径上产生，``phi`` 只按控制流边选择当前 value identity。
* 循环 header 的 ``phi`` 通常同时接收 entry 初始值和 latch/backedge 上的迭代值，因此它也是归纳变量的基础表示。
* Block argument 是另一种 SSA 合流形式：successor block 声明参数，predecessor terminator 在跳转时显式传值。
* ``phi`` 与 block argument 表面位置不同，语义核心相同：控制流边携带 value，后继 block 获得一个支配内部使用点的新 SSA value。
* Phi/block argument 的值传递可理解为发生在 CFG edge 上：前驱完成计算之后、后继普通指令开始之前。
* 多个 ``phi`` 在同一合流边上的语义接近 parallel copy，而不是按文本顺序逐个赋值；这对 SSA destruction 尤其重要。
* 优化或 CFG 重写后，predecessor 集合、incoming values、dominance 和 use-def 关系必须同步更新，否则 SSA 结构失效。
* 路径相关值的正确判断顺序是：先看 CFG predecessor，再看 edge 上传入哪个 value，最后看 merge value 的 users。

关键路径
--------

分支合流：

::

   branch
   → path A defines value_A
   → path B defines value_B
   → CFG edges enter merge block
   → phi/block argument selects edge value
   → merged SSA value
   → downstream uses

读取 ``phi``：

::

   locate phi block
   → enumerate all predecessors
   → match each predecessor to incoming value
   → verify incoming definition is valid on that edge
   → inspect phi users

Block argument：

::

   predecessor terminator
   → successor operand list
   → successor block parameters
   → parameter becomes SSA value inside block

概念辨析
--------

* **Phi 与普通 select**：``phi`` 按进入 block 的控制流边选择；``select`` 在同一个执行点按条件在普通 values 间选择。
* **Phi 与普通 assignment**：``phi`` 表达边上的路径合流，不是块内顺序执行的一次可变槽位写入。
* **Phi 与 block argument**：两者解决同一 SSA 合流问题，只是 incoming value 的书写位置不同。
* **CFG predecessor 与 textual predecessor**：incoming label 必须对应真实 CFG 前驱，而不是 IR 文本中刚好写在前一段的 block。
* **Merged value 与 source variable**：合流产生的是新的 SSA identity，不是把源码变量恢复成可变槽位。

本章结论
--------

SSA 与控制流真正相遇在合流点。无论使用 ``phi`` 还是 block argument，本质都是把 predecessor edge 上携带的不同 values 合并成后继 block 内唯一、可支配后续 uses 的 SSA value；读取和改写它时必须同时维护 CFG 与 value graph。