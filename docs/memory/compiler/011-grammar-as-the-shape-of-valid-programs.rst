第011章：Grammar as the Shape of Valid Programs
===============================================

核心知识点
----------

* Grammar 描述 token 如何组合成合法程序结构；输入是 token stream，输出是 parse tree、AST 前置结构或直接 AST。
* Terminal 是 parser 直接消费的 token kind；nonterminal 是表达式、语句、声明、函数、模块等结构类别；production 描述组合规则；start symbol 定义完整输入必须归入的顶层结构。
* Grammar 的作用是把线性 token 序列提升为层级结构，使后续名字解析、类型检查、控制流分析和 IR lowering 有稳定入口。
* Expression 通常表示值计算，statement 表示执行动作，declaration 引入名字与接口，program unit 组织文件、模块或翻译单元。
* Grammar 只判断结构是否合法；名字是否存在、类型是否匹配、作用域是否合法属于后续语义分析。

关键路径
--------

``source text → lexer → token stream → start symbol → production 匹配 → expression/statement/declaration/program unit → AST → semantic analysis``。

Parser 处理完整输入时，先从 start symbol 进入顶层规则，再逐层展开到函数、block、statement 和 expression。每次 production 匹配都会把若干 terminal 或较小 nonterminal 组合成更高层结构。若当前 token 无法满足某条 production 的期待集合，失败发生在 syntax 层；若结构已经形成但名字、类型或作用域错误，失败发生在 semantic 层。

概念辨析
--------

* **Grammar vs lexer**：lexer 决定 token 边界与类别；grammar 决定 token 之间怎样组成结构。
* **Terminal vs nonterminal**：terminal 来自输入 token；nonterminal 是 parser 构造出的结构标签。
* **Syntax error vs semantic error**：``return x * ;`` 无法完成表达式结构，是 syntax error；``return y * y;`` 在 ``y`` 未声明时结构仍合法，是 name-resolution error。
* **Grammar vs program meaning**：grammar 可以接受 ``"text" * x`` 这类形状，类型系统仍可能拒绝其运算语义。
* **Start symbol vs 局部规则**：某段 token 能匹配 expression 或 statement，不代表它能作为完整 program 被接受。

本章结论
--------

Grammar 是 token stream 到程序结构之间的正式契约。阅读或调试 parser 时，应先找到 start symbol，再沿顶层结构、声明、语句和表达式向下追踪；遇到错误时先判断结构是否能完成，再把名字、类型和作用域问题留给语义阶段。