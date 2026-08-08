第113章：Graph Optimization and Operator Fusion
===============================================

核心知识点
----------

* Graph optimization 直接在 operator graph 与 tensor use-def 上工作，目标是减少无效计算、降低数据搬运、缩短执行路径并为后端暴露更大的优化单元。
* Constant folding 把纯常量子图提前求值；dead node elimination 从 graph outputs 与 side-effect roots 反向标记活节点；algebraic simplification 用语义等价规则缩短表达式。
* 图优化必须尊重 dtype、broadcast、NaN/signed-zero、量化和副作用边界。``x + 0``、``x * 1`` 等恒等式并非在所有数值模式下都可无条件使用。
* Operator fusion 的本质是把原本需要 materialize 的中间 tensor，变成同一 kernel 内部的临时标量、向量、寄存器值或 tile buffer。
* Fusion 的主要收益来自减少 global-memory round trip、临时 buffer、kernel launch 与 runtime scheduling，而不只是“节点数量变少”。
* Elementwise fusion 适合相同或兼容 iteration space；reduction fusion 需要处理归约维与数值顺序；producer-consumer fusion 关注数据重用；epilogue fusion 常把 bias、activation、scale 等接到 MatMul/Conv 后端实现中。
* Fusion 决策必须依次通过 legality、profitability、backend constraints 三层。语义合法是前提，性能收益与后端生成能力是后续条件。
* Shape、dtype、layout、broadcasting、alias、side effects、multiple consumers 都会限制 fusion legality。
* 合法 fusion 也可能亏损：更大的 fused kernel 可能增加 register pressure、降低 occupancy、破坏 vectorization，或失去成熟 library primitive。
* Backend-specific fusion 可能表现为生成自定义 fused kernel，也可能直接匹配 cuDNN/oneDNN/其它供应商 fused primitive。
* 多个 optimization pass 往往迭代工作：constant folding 产生新的 simplification，fusion 删除 materialization 后又可能暴露新的 DCE 和 layout elimination 机会。
* 调试 fusion 时应同时观察优化前后 graph、kernel launch 数量、buffer 生命周期、memory traffic 和后端代码质量，而不是只比较节点数。

关键路径
--------

图简化：

::

   graph outputs + side-effect roots
   → mark live nodes
   → fold constant subgraphs
   → algebraic/canonical simplification
   → delete dead nodes
   → repeat until stable enough for lowering

Fusion 决策：

::

   producer-consumer pattern
   → check shape/dtype/layout/broadcast legality
   → check effects/alias/multiple consumers
   → estimate saved materialization + launch cost
   → estimate register/schedule/library cost
   → check backend support
   → fuse or keep separate

概念辨析
--------

* **Graph simplification 与 fusion**：前者主要删除或替换冗余计算，后者改变多个 operator 的执行边界。
* **Fusion 与 concatenation**：融合不是把源码简单拼在一起，而是重新设计中间值是否 materialize 及其 iteration/schedule。
* **Legality 与 profitability**：合法只表示语义可保持，不表示一定更快。
* **Elementwise fusion 与 reduction fusion**：前者通常共享并行 iteration space，后者还要处理归约依赖和数值顺序。
* **Fused node 与 fused kernel**：图中合并成一个节点不保证最终只有一个高效 kernel；后端仍可能拆分或 fallback。

本章结论
--------

Graph optimization 的稳定模型是 ``Prove Equivalence → Remove Redundancy → Reduce Materialization → Respect Backend Cost``。Operator fusion 的核心价值是减少数据移动与执行边界，但真正高质量的融合必须同时满足语义合法、成本有利和后端可实现三组条件。
