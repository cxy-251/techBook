第131章：Designing a Tiny Language
===================================

核心知识点
----------

* 教学语言的第一原则是先定义学习目标，再定义语法。目标不是做完整语言，而是让一段程序真正穿过 ``source → tokens → AST → semantics → IR → execution`` 全链路。
* 第一版语言应“小到能完成、又足以暴露完整 pipeline”。变量、表达式、函数、``if``、``while``、``return`` 已能覆盖词法、优先级、作用域、类型、CFG、调用和运行时状态。
* 语言特性必须按“它会增加哪些表示和不变量”评估，而不是按表面语法是否简单评估。数组会引入索引与内存布局，闭包会引入捕获环境，异常会引入非局部控制流。
* 一个可实现的语言契约至少要固定：输入单位、顶层结构、表达式/语句集合、名字规则、类型规则、函数调用规则、控制流规则和执行目标。
* Minimal syntax 要覆盖五类结构：program unit、declaration、statement、block、expression。缺少任一类，后续编译器阶段都会少掉一类关键问题。
* 表达式语法必须明确 precedence 与 associativity，否则 parser 无法稳定决定 ``a + b * c`` 或 ``a = b = c`` 的 AST 形状。
* 第一版采用 minimal static types 很合适：例如只支持 ``number`` 与 ``bool``，既能建立真实 type checking，又不会被泛型、子类型和复杂推导拖散。
* 静态类型检查的核心收益是把后端可依赖的事实提前固定，例如通过语义检查后，算术指令只接收 number，条件跳转只接收 bool。
* 执行目标也必须早期固定。AST interpreter 最快形成闭环；bytecode VM 暴露执行模型；LLVM IR/Wasm 适合后续接入真实后端生态。
* 语言版本演进应以 pipeline 完整性为门槛：先完成一条能编译并执行的小主线，再增加数组、字符串、对象、闭包、模块等扩展能力。

关键路径
--------

设计顺序：

::

   learning goal
   → define smallest complete language contract
   → tokenizable syntax
   → unambiguous AST structure
   → name/type rules
   → control-flow and call semantics
   → choose execution target
   → implement one end-to-end sample
   → only then add language features

第一版 Tiny 语言：

::

   functions + locals
   + number/bool
   + arithmetic/comparison
   + calls
   + if/while/return
   → lexer/parser
   → symbol/type checking
   → CFG/IR
   → interpreter or bytecode VM

概念辨析
--------

* **Language design 与 syntax design**：syntax 只是表面形式，language design 还包括名字、类型、控制流、调用和运行时语义。
* **Feature richness 与 compiler learning value**：特性多不代表更适合学习；能清晰暴露 pipeline 的最小特性集更有价值。
* **Dynamic typing 与 minimal static typing**：前者把更多判断推迟到运行时，后者让 semantic analysis 提前建立可验证事实。
* **AST interpreter 与 bytecode/LLVM/Wasm**：它们是不同执行目标，区别在于语义转换和执行成本被放在哪一层。
* **Toy language 与 toy pipeline**：语言可以很小，但 pipeline 应完整；真正的学习价值来自端到端闭环，而不是语法数量。

本章结论
--------

小语言设计的稳定模型是 ``Learning Goal → Minimal Language Contract → Complete Compiler Pipeline``。第一版的成功标准不是“支持很多语法”，而是每个保留的语言特性都能从源码一路被表示、检查、lowering 并最终执行。