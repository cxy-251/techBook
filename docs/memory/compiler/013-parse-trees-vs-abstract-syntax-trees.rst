第013章：Parse Trees vs Abstract Syntax Trees
============================================

核心知识点
----------

* Parse tree 记录 token 如何按 grammar 被接受，通常保留 nonterminal、terminal、产生式选择、括号和分隔符等完整语法推导痕迹。
* AST 抽掉只服务 parser 的层级与符号，保留后续语义分析、类型检查、IR lowering、诊断和源码映射真正需要的程序结构。
* 同一表达式 ``(base + tax) * rate`` 的 parse tree 可能包含 ``expression/term/factor`` 与括号 token；AST 通常只保留 ``Mul(Add(base, tax), rate)``。
* AST 节点设计由消费者决定，常见字段包括 node kind、children、operator、name/value、source range 与阶段性 metadata。
* 从 parse tree 到 AST 是信息压缩；语法糖归一化可以减少内部结构种类，但必须保留求值顺序、副作用次数、绑定规则和诊断证据。

关键路径
--------

``token stream → grammar derivation → parse tree/CST → 删除 parser-only 层级 → 保留语义节点与 source range → AST → semantic analysis / type checking / IR lowering``。

括号、逗号、分号和 ``expression/term/factor`` 等节点如果已经把结构作用编码进父子关系，可以在 AST 中消失；若某种表面语法会影响求值次数、重载、绑定或诊断，则需要保留专门 AST 节点或 metadata。AST normalization 的提交点不是“让树更小”，而是确认被删信息已被其它结构可靠表达。

概念辨析
--------

* **Parse tree vs AST**：parse tree 证明 grammar 接受路径；AST 表达后续编译阶段真正消费的程序对象。
* **Concrete syntax vs abstract syntax**：concrete syntax 更强调括号、分隔符、token 与版面证据；abstract syntax 更强调表达式、语句、声明和语义依赖。
* **删除括号 vs 改变结构**：括号节点可以消失，前提是括号造成的分组已经固化在 AST 父子关系中。
* **Syntax sugar vs normalization**：语法糖是源码表面便利；normalization 是把多种写法压成内部少数结构，必须保持语义。
* **AST metadata vs semantic facts**：source range、操作符和语法糖来源可在 AST 阶段保存；完整名字绑定和类型结论通常由后续阶段补充。

本章结论
--------

Parse tree 服务“源码怎样被 grammar 接受”，AST 服务“程序结构怎样被后续阶段消费”。分析一棵语法树时，应先判断它保存的是 grammar 证据还是程序结构，再检查被删除的表面信息是否已经由树形关系、source range 或 metadata 承接。