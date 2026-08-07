第026章：Intermediate Representation as Compiler Working Language
=================================================================

核心知识点
----------

* IR 是 AST 与机器码之间的编译器内部工作语言，目标是把源语言语义转换成可分析、可验证、可优化、可继续降低的统一表示。
* AST 更接近源码结构，适合名字、类型、源码范围和诊断；机器码更接近硬件，承载寄存器、ABI、指令和栈布局；IR 位于两者之间。
* 典型 IR 显式表达 operation、value、type、basic block、control flow、memory access 和 side effect，使中端 pass 不必理解每种源语言的语法细节。
* SSA 风格 IR 让值的定义和使用关系清晰，便于常量传播、死代码删除、CFG 简化和数据流分析。
* 共同 IR 能形成 ``多个前端 -> 一个中端 -> 多个后端`` 的结构，降低多语言、多架构组合的工程复杂度。
* IR lowering 必须保留后续阶段仍需要的语义证据；过早丢失异常、别名、类型、源码位置或副作用信息，会限制优化与诊断能力。

关键路径
--------

``Source -> Lexer/Parser -> AST -> Semantic Analysis -> IR -> Analysis/Optimization -> Lower IR -> Machine Code``。

以条件函数为例，源码中的局部变量和 ``if`` 会降低为 SSA value、比较指令、条件分支和 basic block；中端随后直接在 CFG 与 use-def 关系上工作，后端再把这些事实映射到具体指令、寄存器和 ABI。

排查问题时按表示层定位：源码结构、名字或诊断问题优先看 AST；优化合法性、控制流和数据流问题优先看 IR；指令选择、寄存器或 ABI 问题优先看机器级表示。

概念辨析
--------

* **AST vs IR**：AST 强调源语言结构；IR 强调可转换的执行语义和中端不变量。
* **IR vs machine code**：IR 通常仍保持机器无关的类型、值和控制流事实；机器码已经绑定目标架构约束。
* **IR textual form vs IR semantics**：文本只是 IR 的一种打印形式，真正重要的是内存中的图结构、类型、值关系和结构规则。
* **Frontend lowering vs optimization**：lowering 改变表示层级；optimization 在语义允许范围内寻找更优等价形式，二者目标不同。

本章结论
--------

IR 的核心价值是建立稳定的编译器内部契约：前端把源语言语义交付成统一操作、值和控制流，中端据此分析与改写，后端再承担目标机器约束。读编译器时，应始终先确认当前表示层，再选择该层真正保留的证据。