第062章：Instruction Selection and Pattern Matching
===================================================

核心知识点
----------

* Instruction selection 的目标是为已经接近机器语义的 IR 选择语义等价的目标指令或指令序列。
* Selector 匹配的不是源码文本，而是 IR 中的 operation graph：算术、地址计算、load/store、比较和控制依赖会组成 tree/DAG 等结构。
* Tree pattern 强调局部父子关系，DAG 允许多个 use 共享同一 producer；选择器可以用一条目标指令覆盖一片 IR 子图，而不是逐节点机械翻译。
* 目标支持复杂指令时，较大 pattern 可能减少中间值、临时寄存器和指令数；但所有被覆盖节点的语义必须被目标指令完整承载。
* 复杂寻址模式是典型 pattern matching。``base + index*scale + displacement`` 可能折叠到 load/store 的地址操作数，而不是显式生成乘法和加法。
* 是否折叠地址还受 scale、位宽、立即数范围、寄存器类别、地址空间和目标特性限制。
* FMA 等融合指令说明“表达式形状相似”不足以直接选择：浮点 fused multiply-add 的一次舍入与分开的 mul+add 两次舍入不同，需要 IR flags/语言语义明确允许。
* 内存 pattern 还必须尊重 volatile、atomic、alignment、exception 和 memory-order 约束，不能为了减少指令越过可观察语义边界。
* SelectionDAG 类框架把依赖组织成 DAG 后做 legalization、combine 和 select；GlobalISel 类框架则围绕 generic Machine IR、legalizer、register bank 和 instruction select 组织流程。
* 不同框架实现方式不同，稳定抽象相同：先得到合法候选形状，再用 target patterns 覆盖语义子图，生成 target-specific Machine IR。
* Instruction selection 通常发生在最终寄存器分配和机器编码之前，因此输出里仍可能有 virtual registers、pseudo instructions 和未解决的资源约束。

关键路径
--------

模式选择：

::

   legalized IR / generic machine ops
   → build or inspect dependency graph
   → choose root operation
   → match target pattern
   → verify type / flags / memory / feature constraints
   → cover semantic subgraph
   → emit target instruction or pseudo

复杂地址：

::

   GEP / add / mul address chain
   → recover base + index + scale + displacement
   → query target addressing mode
   → fold when legal and profitable
   → otherwise keep explicit address computation

概念辨析
--------

* **Pattern matching 与 textual matching**：选择器匹配 IR 语义图，不匹配源码字符串。
* **Tree 与 DAG**：tree 假设单一父子结构，DAG 能表达一个 value 被多个 consumers 共享。
* **Instruction selection 与 legalization**：legalization 先让操作进入目标可处理集合，selection 再为合法语义选择目标实现。
* **复杂指令与更优指令**：一条指令覆盖更多工作不保证更快，调度、延迟和寄存器压力仍会进入成本判断。
* **SelectionDAG 与 GlobalISel**：它们是不同后端基础设施，解决的核心问题都是目标约束下的语义匹配。

本章结论
--------

指令选择本质是“用硬件指令覆盖 IR 语义子图”。正确路径是 ``Legalized Graph → Target Pattern → Constraint Check → Target Instruction``；越复杂的寻址或融合指令，越需要同时检查数值、内存、浮点和目标特性语义，不能把“模式能对上”误当成“转换一定合法”。