第094章：Dialect Conversion and Progressive Lowering
======================================================

核心知识点
----------

* Dialect conversion 把 lowering 变成“有目标合法性约束的结构化转换”，而不是任意把高层文本改写成低层文本。
* Conversion target 定义一次 lowering 结束时哪些 operations/dialects 合法、哪些必须消失、哪些实例需要动态判断合法性。
* ``Legal`` 表示当前阶段允许保留；``Illegal`` 表示必须被转换；``Dynamic`` 表示是否允许取决于 operation 的具体 type/attribute/region 状态。
* Target 与 pattern 分离是关键设计：target 描述“结果必须长什么样”，rewrite pattern 描述“如何把源 operation 转成目标表示”。
* Rewrite pattern 是 lowering rule。它匹配特定高层 operation，检查语义前提，然后创建一个或多个更低层 operation，并替换旧 SSA results。
* Pattern 必须通过 rewriter API 维护 use-def、source location、region、block、type 和 verifier invariants；它不是对 ``.mlir`` 文本做字符串替换。
* Lowering 不要求一步直达最终 legal op。多个 patterns 可以组成 legalization graph，例如 custom matmul → linalg.matmul → scf/memref/arith → LLVM dialect。
* Pattern 的匹配失败是正常控制路径：如果 rank、element type、shape、layout 或 target capability 不满足前提，应拒绝匹配，而不是生成语义不确定的 IR。
* TypeConverter 负责高层 type 到目标 type 的映射，并把类型变化传播到 function signatures、block arguments、operands、results 和 region boundaries。
* Tensor-to-buffer lowering 是典型类型边界：``tensor<...>`` 可能变成 ``memref<...>``，此后值语义转换为显式 memory identity、layout 与 mutation 约束。
* Type conversion 可能需要 materialization，把暂时处于不同类型系统的 values 通过显式 bridge operation 连接，直到整个 pipeline 完成合法化。
* Operand remapping 让 conversion pattern 读取“已经转换后的输入 values”，而不是继续错误使用旧类型的原始 operands。
* Partial conversion 允许未被标记为非法的 mixed-dialect IR 暂时保留，适合渐进 lowering；full conversion 要求最终所有 operation 都满足 target，适合作为严格阶段边界。
* Mixed-dialect IR 的合法性来自 conversion target，而不是来自“看起来还能解析”。一个 pass 是否完成，应检查残留 illegal ops 和 type constraints。
* Progressive lowering 的正确性由一系列局部转换共同构成：每一步都明确源语义、目标合法集合、类型映射和验证条件，最终才能安全进入 backend。

关键路径
--------

Dialect conversion：

::

   current mixed/high-level IR
   → define ConversionTarget
   → mark legal / illegal / dynamic operations
   → register rewrite patterns
   → match illegal operation
   → check semantic preconditions
   → remap operands / convert types
   → build lower-level operations
   → replace old results
   → verify target legality

渐进 lowering：

::

   custom/domain dialect
   → partial conversion to shared high-level dialects
   → type/buffer conversion
   → structured control/memory dialects
   → full conversion at strict backend boundary
   → LLVM/target dialect

概念辨析
--------

* **Conversion target 与 rewrite pattern**：target 定义验收标准，pattern 定义实现转换的方法。
* **Illegal op 与 invalid IR**：illegal 表示“当前 lowering 阶段不允许留下”，不代表该 operation 在其原 dialect 中本身非法。
* **Partial conversion 与 failed conversion**：partial conversion 有意允许一部分未要求转换的 IR 保留；失败是无法满足 target 对 illegal/dynamic op 的要求。
* **Type conversion 与 bitcast**：TypeConverter 描述抽象层级的类型体系迁移，可能需要重写函数、blocks 和 values，不等于插入一个普通 cast。
* **Pattern rewriting 与 text rewriting**：pattern 修改 IR 对象图和 SSA 关系，必须维护 verifier invariants。

本章结论
--------

Dialect conversion 的稳定模型是 ``Legality Contract → Rewrite Patterns → Type/Value Remapping → Verification``。Progressive lowering 之所以可控，是因为每一步都能明确回答“哪些抽象必须消失、它们被什么替代、类型如何变化、输出是否已经满足下一阶段契约”。