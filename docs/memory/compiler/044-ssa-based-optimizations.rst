第044章：SSA-Based Optimizations
================================

核心知识点
----------

* SSA 优化器同时操作两张图：value graph 表示 definition/use 依赖，CFG 表示执行路径与可达性。很多优化需要两类事实共同成立。
* Constant propagation 利用 value 的唯一定义沿 def-use chain 传播常量；当 operation 的输入都确定时，可继续 constant folding。
* DCE 的直接候选是“SSA result 无 users + defining operation 无副作用”。删除一个 dead value 后，旧 operands 的 producers 也可能继续变 dead，因此常需要递归清理。
* SCCP（Sparse Conditional Constant Propagation）同时传播 value lattice 与 CFG reachability。恒定 branch 可以剪掉不可达 edge，并反过来提高 ``phi`` 的常量精度。
* ``phi`` 的结果必须只考虑可达 predecessor inputs。某条 CFG edge 被证明不可达后，其 incoming value 不再影响运行时结果。
* Global Value Numbering / CSE 将等价计算归入同一 value class。判断等价不仅要比较 opcode 和 operands，还要考虑 dominance、type、flags、memory effects 和语言语义。
* SSA 让“替换所有 uses”成为直接图操作，但替换前必须确认新 value 支配所有 use sites，且类型与 operation constraints 合法。
* 删除 block、折叠 branch 或替换 ``phi`` 后，需要同步维护 predecessor/successor、incoming values、dominance、analysis cache 和 verifier invariants。
* 优化器通常以 pass pipeline 迭代工作：常量传播产生不可达块，CFG 简化删除 edge，DCE 删除 dead values，新的图形又可能暴露更多折叠机会。
* “无 users”只适用于有 result 的 value；``store``、``call``、``br`` 等即使没有 SSA result，也可能具有必须保留的 observable effect。
* SSA 的价值不在于自动保证优化正确，而在于让证明依赖更局部、更显式。内存、异常、并发和 poison/undef 等语义仍需要专门模型。

关键路径
--------

Constant propagation：

::

   SSA definition
   → prove constant fact
   → walk users
   → fold dependent operations
   → update phi/select values
   → simplify CFG

SCCP：

::

   initialize value + edge states
   → propagate constants through SSA uses
   → evaluate branch conditions
   → mark reachable CFG edges
   → re-evaluate phi using reachable inputs only
   → converge
   → cleanup dead blocks/instructions

DCE / GVN：

::

   query users or value equivalence
   → check side effects / dominance / semantics
   → replace uses or remove instruction
   → update graph relations
   → invalidate or recompute affected analyses

概念辨析
--------

* **Constant propagation 与 SCCP**：前者主要沿值图传播常量；SCCP 把值事实与 CFG 可达性联合求解。
* **Unused value 与 removable operation**：value 无 users 不代表 operation 一定可删，副作用仍是独立条件。
* **GVN/CSE 与 textual equality**：等价性建立在 IR value、operation semantics 和路径可用性上，不是源码字符串相同。
* **Phi input 与 reachable input**：phi 结构上可能有多个 incoming，运行时只会选择实际可达前驱边对应的值。
* **Graph rewrite 与 semantic proof**：SSA 让改写动作简单，正确性仍依赖替换前的完整证明。

本章结论
--------

SSA 把许多优化转化成“在 value graph 与 CFG 上传播事实、替换节点、删除无效边”的图重写。真正稳定的优化路径是先证明 value、reachability、dominance 与 effect 条件，再做局部替换，最后重新验证和更新分析结果。