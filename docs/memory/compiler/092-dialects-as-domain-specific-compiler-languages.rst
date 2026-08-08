第092章：Dialects as Domain-Specific Compiler Languages
=======================================================

核心知识点
----------

* Dialect 是 MLIR 扩展 IR 词汇和语义的基本单位。它不仅提供 namespace，还定义 operations、types、attributes、verifier、interfaces、traits 和 lowering 入口。
* Dialect 的价值是让领域语义直接进入统一 compiler infrastructure，而不是被迫立即翻译成最低公共表示。
* 一个 operation 名称通常形如 ``dialect.operation``。前缀标识语义归属，使多个领域和抽象层能够安全共存于同一个 module/function 中。
* Operation 表达“发生什么计算或结构动作”，type 表达“值满足什么静态约束”，attribute 表达“编译期已经固定的配置或常量”。三者共同形成当前阶段的语义合同。
* 自定义 dialect 适合保存框架、DSL、硬件或项目特有概念，例如卷积布局、量化策略、数据库 operator、设备 tile、专用寄存器和调度约束。
* 标准/内置 dialect 提供可复用的通用抽象，例如 ``func``、``arith``、``tensor``、``memref``、``linalg``、``scf``、``affine``、``vector``、``gpu``、``llvm``。
* 标准 dialect 与自定义 dialect 的区别不是“高层/低层”。标准 dialect 可以很高层，自定义 dialect 也可以非常接近硬件；判断依据是语义通用性与复用边界。
* 高质量 dialect 应把关键领域事实结构化地放入 op/type/attribute，而不是藏进字符串、side table 或隐式约定。结构化事实才能被 verifier、rewriter 和 analysis 稳定消费。
* Verifier 让错误在高层语义仍然可见时暴露。例如 convolution op 可以直接检查 rank、shape、stride、padding 和 output shape，而无需等到低层循环生成后再发现不一致。
* Dialect composition 是 MLIR 的关键能力。一个函数可以同时包含 ``func``、``tensor``、自定义 ``img``、``linalg`` 等 operation，逐步 lowering 不要求整份 IR 同时进入同一抽象层。
* Mixed-dialect IR 不是临时失控状态，而可以是有意设计的中间表示；前提是每个 op 的语义归属和合法性边界清晰。
* 自定义 dialect 的主要工程问题是抽象边界：哪些领域事实值得长期保留，哪些应尽早转入标准 dialect 以复用既有 pass。
* Dialect 设计应围绕“谁会消费这些语义”展开。若某个事实只在高层优化有价值，应在这些优化结束前保留；若通用 pass 已能表达后续需求，则应适时降低。

关键路径
--------

领域语义进入 IR：

::

   domain concept
   → define dialect namespace
   → define operations/types/attributes
   → attach verifier/interfaces/traits
   → run domain-specific analyses/transforms
   → lower into reusable standard dialects

Mixed-dialect lowering：

::

   custom high-level op
   → preserve domain semantics
   → rewrite to tensor/linalg/scf/etc.
   → retain shared SSA/type relations
   → continue lower dialect by dialect
   → target/runtime representation

概念辨析
--------

* **Dialect 与 namespace**：namespace 只解决名称组织；dialect 还携带语义、验证、接口和转换规则。
* **Standard dialect 与 custom dialect**：前者强调生态复用，后者强调领域专属语义；它们可以同时存在且没有固定高低层关系。
* **Operation 与 attribute**：operation 是 IR 中的计算/结构节点，attribute 是编译期固定配置；动态值应作为 SSA operand/result 流动。
* **Dialect composition 与 monolithic IR**：composition 允许不同抽象层在同一 IR 中共存，避免设计一个包含所有概念的巨大统一指令集。
* **Custom dialect 与 black box**：自定义 op 仍应参与统一 SSA、type、region 和 verifier 机制，而不是把整个领域程序封装成不可分析字符串。

本章结论
--------

Dialect 的稳定模型是 ``Domain Semantics → Structured Operation/Type/Attribute → Verification/Optimization → Lower to Shared Dialects``。它让统一基础设施能够同时“说多种领域语言”，并把领域语义保留到真正完成相关优化之后再进入更通用、更低层的表示。