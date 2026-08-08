第133章：Building Semantic Analysis and IR
===========================================

核心知识点
----------

* AST 只固定语法结构；semantic analysis 要进一步回答名字指向谁、表达式是什么类型、当前位置是否合法。IR 再把这些已确定语义改写成更接近执行的数据流与控制流。
* Symbol table 是名字到实体的映射；scope stack 维护当前可见声明。名字查找通常从最内层作用域向外层搜索，shadowing 规则由语言契约决定。
* 顶层函数常需要两遍处理：第一遍收集函数名与签名，第二遍分析函数体，从而支持递归与前向调用。
* 每个 NameExpr 在语义分析后都应绑定到具体 symbol。后续类型检查和 IR lowering 应依赖绑定对象，而不是再次按字符串猜名字。
* Type checker 输入是已完成名字绑定的 AST，输出是 typed AST 或等价旁表。每个表达式都应有可查询的类型事实。
* 类型规则应围绕语言承诺写成局部不变量：算术只接收 number，条件只接收 bool，调用实参与函数签名匹配，返回表达式与函数返回类型兼容。
* 语义约束不只包括类型。例如 ``return`` 必须处于函数中，``break`` 必须处于循环中；这类规则需要 current-function、loop-depth 等上下文状态。
* Semantic analysis 的价值是把“程序是什么意思”固定下来，使 IR builder 可以依赖这些事实生成具体指令，而无需重复名字和类型推断。
* Simple IR 至少需要 function、basic block、instruction、value、terminator。控制流必须由显式 edge/terminator 表示。
* AST 中的高层 ``if``、``while``、短路逻辑会在 IR 中变成 basic blocks、conditional branches、backedges 和 merge points。
* SSA-like IR 让每个计算值只定义一次；多路径值合并需要 phi 或等价 block argument。命令式局部变量也可先降低到 slot/load/store，再由后续优化提升。
* CFG 是控制流事实的核心载体。Reachability、dominance、loop detection、DCE 等后续分析都依赖正确的 block 与 edge。
* IR lowering 的正确性标准是：高层语法形态可以消失，但名字、类型、求值顺序、分支/循环和可观察行为必须被保留。

关键路径
--------

语义分析：

::

   AST
   → collect declarations/signatures
   → enter/leave lexical scopes
   → resolve every name use to a symbol
   → compute expression types
   → check calls/returns/control-flow constraints
   → typed/bound AST
   → semantic diagnostics if any

IR lowering：

::

   typed AST
   → create function + entry block
   → lower expressions into values/instructions
   → lower if into condition/then/else/merge blocks
   → lower while into header/body/exit + backedge
   → merge path values with phi/block arguments when needed
   → terminate every block explicitly
   → verify CFG/IR invariants

概念辨析
--------

* **Parsing 与 semantic analysis**：parsing 确认结构是否合法，semantic analysis 确认名字、类型和上下文关系是否合法。
* **Symbol name 与 symbol binding**：名字是文本，binding 是对具体声明实体的引用；后续阶段应使用后者。
* **Typed AST 与 IR**：typed AST 仍保留源语言结构，IR 开始围绕统一操作、值和控制流组织程序。
* **Source variable 与 IR value**：一个源码变量可能对应多个 SSA value、一个 memory slot，或经过优化后完全消失。
* **AST control structure 与 CFG**：``if/while`` 是源语言结构，basic blocks/edges/terminators 才是 IR 中的执行关系。

本章结论
--------

小编译器中段的稳定模型是 ``AST → Name/Type Meaning → Typed Program → Explicit IR/CFG``。语义分析先固定程序意义，IR lowering 再把意义压缩成可执行、可分析、可优化的值与控制流；两者边界清楚后，后续优化和运行时才有可靠输入。