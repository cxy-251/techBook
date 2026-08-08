第091章：Multi-Level IR and Progressive Lowering
=================================================

核心知识点
----------

* Multi-Level IR 的核心不是“多保存几份 IR”，而是承认不同编译阶段需要不同抽象层：高层 IR 保留领域语义，低层 IR 暴露执行与硬件约束。
* 单一 universal IR 很难同时适合张量/图/数据库等领域优化、通用 SSA/CFG 优化、内存与循环变换、以及寄存器/ABI/目标指令生成。
* 高层语义若过早降低成 load/store、地址计算和普通循环，``transpose``、matmul、reduction、shader stage 等整体结构会消失，后续优化必须从低层模式重新猜测原始意图。
* 高层 representation 的价值是让 shape、layout、代数关系、结构化并行、算子副作用等事实直接可见，从而支持 fusion、shape propagation、layout selection 等领域级证明。
* 高层 IR 也不能停留到最后。机器执行最终需要 buffer、stride、address space、vector width、calling convention、register pressure 和 target instruction 等低层事实。
* Progressive lowering 指每一步只丢弃已经完成主要用途的抽象，同时引入下一阶段需要的约束；降低应是受控的语义迁移，而不是一次性“翻译到底”。
* 典型路径可从 tensor/domain operation 进入 linalg/structured operation，再进入 affine/scf/memref/vector，最后进入 LLVM dialect/LLVM IR 或目标专属后端。
* 每一层 IR 都应回答三个问题：当前层保留什么事实、哪些 pass 消费这些事实、lowering 后哪些信息不可恢复。
* Tensor value 与 buffer/memref 的分界尤其重要。张量层更接近值语义和代数变换；buffer 层引入 alias、mutation、lifetime、allocation 和 memory effect。
* Structured loop/affine 层保留循环与访问函数，使 tiling、interchange、fusion、vectorization 等仍有明确结构证据；继续降低后，这些关系会分散到 CFG 和地址计算中。
* Lowering 的时机本身就是优化决策。过早降低会损失高层机会，过晚降低会延迟机器约束暴露并阻碍后端优化。
* Mixed-level pipeline 的正确性依赖阶段契约：每次 conversion 都必须明确输入抽象、允许输出、类型映射以及语义保持条件。
* Multi-level IR 的最终目标是让“最适合当前问题的语义”在最合适的阶段仍然直接可观察，而不是强迫所有 pass 在同一种表示上工作。

关键路径
--------

多层 lowering：

::

   source/domain semantics
   → high-level domain/tensor IR
   → domain optimization / shape / fusion
   → structured linear algebra / loop IR
   → buffer + affine/scf/vector constraints
   → LLVM/target dialect
   → machine/backend representation

每层判断：

::

   current IR
   → identify preserved semantics
   → run analyses/transforms that need them
   → decide which facts are no longer needed
   → lower one abstraction boundary
   → verify newly exposed constraints

概念辨析
--------

* **Multi-Level IR 与 duplicated IR**：前者是多个有明确职责和转换关系的语义层级，不是同一程序的冗余副本。
* **High-level IR 与 source AST**：高层 IR 已经是编译器工作表示，可以拥有 SSA、types 和 verifier；它不等于原始语法树。
* **Lowering 与 optimization**：lowering 主要改变抽象层级，optimization 主要利用当前层事实改写程序；实际 pass 可以同时承担两者，但证明目标不同。
* **Tensor value 与 buffer**：tensor 更接近整体值语义，buffer/memref 引入可变内存身份、布局和别名问题。
* **Late lowering 与 target ignorance**：延迟降低不表示忽略硬件，而是避免在高层优化尚未完成时过早固定低层选择。

本章结论
--------

Multi-Level IR 的稳定模型是 ``Preserve High-Level Meaning → Consume It → Lower One Boundary → Expose New Constraints``。Progressive lowering 的工程价值在于控制抽象信息何时消失：高层语义只在完成高层证明之后才被拆解，低层机器事实则在真正需要时逐步进入 IR。