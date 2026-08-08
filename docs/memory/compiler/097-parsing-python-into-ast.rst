第097章：Parsing Python into AST
================================

核心知识点
----------

* Parser 的输入是 tokenizer 已经结构化好的 token stream，输出是供后续编译阶段使用的 Python AST，或在结构匹配失败时产生 SyntaxError。
* Token stream 是线性的，AST 是树形的。Parser 的核心工作是根据 grammar 把 token 序列组织成函数、语句、表达式、调用和控制结构。
* CPython 当前使用 PEG parser。工程上仍可把它理解为“按 grammar 消费 token、匹配规则并构造 AST”的前端阶段；具体 parser 实现细节属于版本边界。
* Concrete syntax 关心源码如何满足完整语法规则；abstract syntax 只保留后续 compiler 真正需要的程序结构。
* 括号、逗号、冒号、缩进标记等表面语法通常不会原样进入 AST，而会转化成字段、列表和父子关系。
* ``Module`` 是常见顶层节点；``FunctionDef``、``ClassDef``、``If``、``For``、``Return`` 等节点表达 statement structure；``Call``、``BinOp``、``Compare``、``Name``、``Constant`` 等表达 value computation。
* AST 字段比节点名字本身更重要。``FunctionDef.body``、``If.test``、``Call.args`` 等字段决定后续 symbol table 和 bytecode generator 如何遍历程序。
* ``Name.ctx`` 明确区分 ``Load``、``Store``、``Del`` 等语义角色。相同标识符出现在赋值左侧和表达式右侧时，AST 已经把读写身份区分开。
* AST 保留 source location，例如行列范围，使后续诊断、源码工具、traceback/debug metadata 能继续映回源文本。
* SyntaxError 表示当前 token stream 无法满足 grammar 要求。缺失冒号、括号不闭合、表达式结构非法等都属于 parser 阶段的结构失败。
* Parser diagnostic 的核心证据是当前 token、正在匹配的 grammar rule 和已经确认的上下文，而不是运行时对象状态。
* AST 是 CPython 后续 symbol table、scope analysis、compiler code generation 的主要结构输入；到这一层，源码已经从文本形式转为真正可遍历的编译器数据结构。

关键路径
--------

Parser 主路径：

::

   token stream
   → parser matches grammar rules
   → group tokens into statements/expressions
   → build AST nodes and fields
   → attach source locations
   → Python AST
   → symbol table / compiler

函数结构：

::

   def/name/parameters/:/INDENT...
   → FunctionDef
   → arguments
   → body statement list
   → nested If/Return/Call/Name nodes

语法错误：

::

   current grammar rule
   → consume valid prefix
   → encounter unexpected/missing token
   → rule cannot complete
   → SyntaxError with source position

概念辨析
--------

* **Token stream 与 AST**：token stream 只表达线性词法单元，AST 表达结构化父子关系和程序语义形状。
* **Concrete syntax 与 abstract syntax**：前者包含完整语法表面证据，后者丢弃大量分隔符和排版，只保留编译需要的结构。
* **AST node 与 source statement**：一个源码语句可能展开成多个嵌套 AST nodes，不能简单一行对应一个节点。
* **Name spelling 与 Name context**：标识符文本相同不代表语义相同，``Load/Store/Del`` 决定它在当前结构中的作用。
* **Syntax error 与 runtime error**：语法错误在 AST 构造阶段失败；运行时错误发生在合法程序已经编译并开始执行之后。

本章结论
--------

Python parser 的稳定模型是 ``Token Stream → Grammar Matching → AST``。真正进入 compiler 世界的不是源码表面括号和缩进，而是 ``Module/FunctionDef/If/Call/Name`` 等结构化节点及其字段；AST 是后续作用域分析与 bytecode 生成能够直接消费的程序形状。