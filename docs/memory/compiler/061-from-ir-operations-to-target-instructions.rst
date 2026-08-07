第061章：From IR Operations to Target Instructions
===================================================

核心知识点
----------

* 后端接手的是已经结构化并经过中端优化的 IR。它的任务不是继续理解源码表面，而是把 ``load/add/icmp/select/br`` 等抽象操作映射到真实目标机器能够执行的指令、寄存器和 ABI 约束。
* Target-independent IR 保存“程序要做什么”；target-specific instruction 描述“这台机器怎么做”。同一个 ``i32 add`` 在 x86-64、AArch64、RISC-V 上可以得到完全不同的目标指令序列。
* 后端首先匹配 operation semantics，再考虑具体编码。IR 中的位宽、signedness、overflow flags、volatile/atomic、地址空间和浮点 flags 都属于选择目标实现时必须保留的语义。
* 一个 IR operation 不必对应一条机器指令。它可以 lower 成一条指令、多条指令、伪指令、runtime helper/libcall，甚至被合并进另一条指令的寻址模式或条件码使用中。
* 目标描述是后端认识硬件的事实集合，包括 DataLayout、寄存器文件、register classes、合法类型、目标指令、立即数范围、寻址模式、调用约定、stack/frame 规则和 subtarget feature。
* 比较结果在目标上不一定成为普通布尔寄存器。它可能被编码成 flags、condition code、predicate register 或直接变成条件分支。
* 内存访问的 lowering 必须保留地址、宽度、对齐、volatile/atomic/order 等语义；目标是否允许复杂寻址模式只改变实现形状，不改变读取位置与可观察顺序。
* 同一个架构的不同 CPU feature 集合也会改变目标能力，例如 SIMD、crypto、atomic、浮点扩展会改变 legal operations 和可选指令。
* 后端的正确性目标是把 IR 语义嵌入硬件约束，而不是逐条“翻译”。指令越少、寻址越复杂都只是成本选择，语义保持优先。

关键路径
--------

后端入口：

::

   optimized IR
   → read operation/type/effect semantics
   → read target triple + DataLayout + subtarget features
   → query legal types / operations / register classes
   → lower generic operations
   → instruction selection
   → Machine IR
   → register allocation / scheduling / emission

单个 IR 操作：

::

   IR opcode + operands + flags
   → identify semantic contract
   → query target capabilities
   → choose native instruction / sequence / pseudo / libcall
   → preserve value, memory and control behavior

概念辨析
--------

* **Target-independent 与 target-agnostic**：IR 可以统一表达程序语义，但仍可能携带 DataLayout、target triple、ABI 属性等目标事实。
* **Operation semantics 与 instruction encoding**：前者决定“必须实现什么”，后者决定最终机器指令怎样编码成字节。
* **IR value 与 physical register**：IR value 是语义层结果，真正绑定有限物理寄存器通常发生在更晚的 register allocation。
* **Lowering 与 optimization**：lowering 主要把抽象操作改成目标可实现形式；过程中也可能顺带选择更便宜的目标表达。
* **一条 IR 与一条指令**：二者没有一一对应关系，复杂 ISA 和受限 ISA 都会打破这种直觉。

本章结论
--------

后端从“抽象操作”进入“硬件约束”。正确理解路径是 ``IR Semantics → Target Description → Legal Form → Target Instruction → Machine Representation``；只有先确认 IR 承诺的值、内存和控制语义，再讨论寄存器、寻址模式和具体指令，才能判断后端输出是否正确。