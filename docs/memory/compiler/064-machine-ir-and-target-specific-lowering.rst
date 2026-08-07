第064章：Machine IR and Target-Specific Lowering
================================================

核心知识点
----------

* Machine IR 是后端的工作表示：已经包含 target opcode、register class、implicit state、ABI 和机器基本块等硬件事实，但仍保留 virtual registers、pseudo instructions、frame objects 和调度信息等编译器自由度。
* LLVM IR 中的 ``add i32`` 只表达数值语义；进入 Machine IR 后，它会变成某个目标 opcode，并携带寄存器类别、隐式 flags、物理寄存器约束和机器层副作用。
* Virtual register 允许后端在 register allocation 前用近似无限的名字表达值流。每个 vreg 已经绑定某类目标资源，例如整数、浮点或向量 register class。
* Physical register 会因 ABI、stack pointer、flags、特殊指令和固定操作数约束提前出现。它们限制后续 vreg 的可分配空间。
* Register allocation 前的核心问题仍是“值如何流动”；分配后才真正变成“这些值在什么时刻占用哪些有限物理寄存器或 stack slots”。
* COPY 等 Machine IR 操作不一定最终生成真实 move。寄存器合并、coalescing 或重命名可能让它完全消失。
* Pseudo instruction 用来延迟尚未具备完整信息的机器决策，例如大立即数、调用序列、stack adjustment、长分支、特殊原子序列等。
* Late expansion 的意义是等 register allocation、frame layout、code model 或 branch distance 更明确后，再把 pseudo 展开成最终目标指令序列。
* Instruction scheduling 会在数据、memory、control、implicit flags 等依赖允许的范围内重排机器指令，以优化 latency、throughput、pipeline/resource conflict。
* 机器层的隐式寄存器依赖必须当成真实依赖，例如 flags 被一条指令定义后供条件分支使用，中间不能插入会覆盖 flags 的不受约束指令。
* Machine IR 是观察后端 bug 的关键边界：可以分别检查 selection 后、register allocation 前后、pseudo expansion 前后，定位哪一阶段第一次破坏机器级不变量。

关键路径
--------

后端表示演进：

::

   target-specific selection
   → Machine IR with vregs / pseudos
   → machine combines / scheduling
   → register allocation
   → frame/prologue/epilogue lowering
   → late pseudo expansion
   → MC / assembly / object emission

虚拟寄存器：

::

   machine definition
   → virtual register + register class
   → live range / interference
   → allocate physical register
   → spill/reload if pressure exceeds capacity

伪指令：

::

   abstract machine action
   → keep as pseudo while information incomplete
   → wait for registers/frame/layout/features
   → expand to real instructions
   → verify target constraints

概念辨析
--------

* **Machine IR 与 assembly**：MIR 已高度目标相关，但仍包含虚拟寄存器、伪指令和编译器元数据；汇编更接近最终可编码形式。
* **Virtual register 与 SSA value**：两者都表达值身份，但 vreg 已进入机器寄存器类别和后端活跃性约束。
* **COPY 与 MOV**：COPY 是后端值传递关系，不保证最终存在一条真实 move 指令。
* **Pseudo instruction 与 illegal instruction**：pseudo 是后端有意保留的临时抽象；illegal operation 则需要 legalization 才能继续。
* **Scheduling 与 semantic reordering**：调度可以改变机器执行顺序，但必须保留所有显式与隐式依赖。

本章结论
--------

Machine IR 是编译器开始“像 CPU 一样思考”的层级。它把 IR 的值流压入 opcode、register class、flags、ABI 和 pipeline 约束，同时用 virtual registers 与 pseudos 保留尚未决定的资源分配；理解后端时应沿 ``MIR → RA → Frame → Late Expansion → Emission`` 追踪机器约束逐步收紧。