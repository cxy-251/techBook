第082章：Bytecode as a Compact Execution Format
===============================================

核心知识点
----------

* Bytecode 是位于 AST 与机器码之间的紧凑执行表示，由语言 VM 定义而不是由物理 CPU ISA 定义。
* AST 是树状结构，bytecode 把程序线性化成 instruction stream，使 VM 可以围绕 program counter 顺序取指、解码、执行和跳转。
* Bytecode 已经完成大量前端工作：语法结构、名字分类和部分语义判断通常已被固定；它保留的是执行所需的 opcode、operands、constant pool、locals、jumps 和 metadata。
* Bytecode 与机器码的核心差异是约束来源。机器码受真实 ISA、寄存器、寻址和 ABI 约束；bytecode 受虚拟机对象模型、调用规则、异常模型和版本格式约束。
* 指令流中 opcode 表示“做什么”，operand 表示“对谁做”或“跳到哪里”。operand 可以是 local slot、constant index、name index、jump offset、argument count 等。
* Constant pool 把字面量、字符串、符号、方法/字段引用等从指令流中抽离，用短索引复用，从而缩短代码并集中管理可解析对象。
* Local slot 和 name/symbol lookup 不是同一类操作。Local slot 通常能直接访问当前 frame；全局名、属性、方法等可能仍需 runtime 动态解析。
* Jump 把线性 instruction stream 重新组织成 CFG。分析 bytecode 时应先标出 jump target，再还原 basic blocks、循环和 merge points。
* VM 格式需要维护结构不变量：jump target 必须合法，stack/register state 必须在控制流汇合处可解释，调用和返回必须满足 frame 规则。
* Stack-based bytecode 通过隐式 operand stack 传递中间值；算术指令通常只写 opcode，不显式写输入输出位置，编码紧凑。
* Register-based bytecode 使用显式 virtual registers，def-use 更直接，但单条指令要携带更多 operand。
* Stack bytecode 的核心分析量是 stack effect；register bytecode 的核心分析量是 virtual-register def-use。二者都可以表达同一语义。
* Bytecode verifier 可以在执行前检查类型、栈深度、控制流、初始化状态和访问边界，使 VM 不必为每条指令重新证明结构合法。
* 不同 VM 对 bytecode 稳定性的承诺不同。JVM class file 属于规范化跨实现格式；CPython bytecode 更偏实现细节，必须绑定具体 Python 版本分析。
* Bytecode 的工程价值是把源码结构提前压缩成“语言虚拟机的 ISA”：比 AST 更适合高频执行，又比原生机器码更具平台可移植性和 runtime 可控性。

关键路径
--------

AST 到 bytecode：

::

   parsed/checked AST
   → choose evaluation order
   → linearize expressions/statements
   → assign locals/constants/names
   → emit opcodes + operands
   → resolve labels/jump offsets
   → attach exception/debug metadata
   → bytecode object

Stack VM：

::

   LOAD operand
   → push value
   → LOAD operand
   → push value
   → arithmetic/call consumes stack entries
   → push result
   → RETURN / STORE / JUMP

Bytecode 检查：

::

   instruction stream
   → decode valid boundaries
   → validate operands and constant indexes
   → build control-flow edges
   → propagate stack/register state
   → reject inconsistent states
   → execute or JIT verified code

概念辨析
--------

* **AST 与 bytecode**：AST 通过父子节点表达结构；bytecode 通过指令顺序、operand 和 jump 表达执行。
* **Bytecode 与 machine code**：前者面向虚拟机，后者面向真实 ISA；bytecode 还需要 interpreter/JIT 才能在 CPU 上执行。
* **Stack-based 与 register-based bytecode**：前者操作数隐式位于 operand stack，后者显式命名 virtual registers。
* **Constant pool 与 runtime heap**：constant pool 是代码格式中的常量/符号表，runtime heap 是执行时对象存储；pool entry 可能在加载时解析成 heap/runtime 对象。
* **Verification 与 dynamic checking**：verifier 检查 bytecode 结构/类型不变量，动态语言语义仍可能在执行时做对象类型、属性或权限检查。

本章结论
--------

Bytecode 是“为语言 runtime 定义的一套紧凑虚拟 ISA”。稳定阅读路径是 ``Instruction Stream → Operands/Constant Pool → Stack or Virtual Registers → Jumps/CFG → Verification``；它的价值在于先把树状程序压成统一执行格式，再让 interpreter 或 JIT 选择如何把这台虚拟机器落实到真实硬件。