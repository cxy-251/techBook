第022章：Tokenizer 与 PEG 解析器
================================

核心知识点
----------

Tokenizer 把源文本转换为 token stream
   源文件先按声明编码或 UTF-8 解码，再由 tokenizer 识别名字、数字、字符串、运算符、逻辑换行、缩进和文件结束标记。Parser 消费的是 token，不再直接处理原始字符。

物理行与逻辑行不是同一概念
   文件中的换行形成物理行；括号内隐式续行、反斜杠续行和多行字符串会改变逻辑语句边界。只有逻辑语句结束才产生终止语句的 ``NEWLINE``。

缩进由词法阶段结构化
   Tokenizer 维护缩进栈。缩进增加产生 ``INDENT``，缩进回退产生一个或多个 ``DEDENT``。Parser 因此能直接按 token 判断代码块范围。

Tokenizer 与 parser 分工明确
   Tokenizer 判断字符怎样组成 token；PEG parser 判断 token 怎样组成合法语句和表达式。非法字符、字符串未闭合和缩进错误更靠近词法层；结构组合失败通常产生 ``SyntaxError``。

PEG 使用有序选择
   Grammar 中多个候选分支按书写顺序尝试，前面的成功分支优先。分支失败可以回退并尝试后续分支；完整起始规则无法消费输入时，解析才整体失败。

Grammar 描述结构而非执行语义
   ``NAME``、``NUMBER`` 等大写符号表示 token 类别，固定字面量表示关键字或符号，顺序、选择、可选、重复、前瞻和 commit 共同定义合法程序形状。

软关键字由 parser 按上下文识别
   ``match``、``case``、``type`` 等词在普通位置仍可作为名字，只在特定 grammar 位置承担语法角色。Tokenizer 无法单独完成这种上下文判断。

Parser state 支撑回退与错误定位
   一次解析需要保存 token 位置、错误位置、memo、起始规则、arena 和 tokenizer 连接状态。Memoization 减少同一规则在同一位置的重复尝试。

PEG parser 属于现代 CPython 主线
   Python 3.9 引入 PEP 617 的 PEG parser，Python 3.10 后旧 LL(1) parser 退出主线。阅读现代 CPython 应从 ``Grammar/python.gram``、生成 parser 和 tokenizer 目录进入。

关键路径
--------

源码前端路径：

::

   源文件字节
   → 按编码规则解码为字符
   → 识别物理行、逻辑行和括号状态
   → 生成 NAME / NUMBER / STRING / OP / NEWLINE
   → 根据缩进栈生成 INDENT / DEDENT
   → 形成 token stream 与 ENDMARKER
   → PEG parser 从起始规则消费 token
   → 按有序选择、前瞻和 commit 匹配 grammar
   → 构造后续阶段使用的语法结构或 AST

错误定位路径：

::

   观察失败字符和源码位置
   → 检查编码、字符串、括号与续行
   → 检查缩进栈是否一致
   → 检查 token 序列是否完整
   → 检查 grammar 分支与 commit 点
   → 判断属于词法错误、缩进错误还是语法错误

概念辨析
--------

* **字符与 token**：字符是源文本单位；token 是 tokenizer 给 parser 的分类输入。
* **物理行与逻辑行**：物理行由文件换行划分；逻辑行由词法规则决定语句边界。
* **Tokenizer 与 parser**：前者负责切分和缩进结构化；后者负责 grammar 匹配和层级组织。
* **硬关键字与软关键字**：硬关键字始终保留；软关键字只在特定语法上下文中生效。
* **候选分支失败与整体解析失败**：单个 PEG 分支失败可以回退；起始规则最终失败才形成语法错误。
* **Parse tree 与 AST**：前者强调 grammar 匹配层级；AST 删除部分表层语法，只保留编译需要的抽象结构。

本章结论
--------

分析 Python 前端错误时，应沿“解码、逻辑行、token、缩进、grammar”逐层定位。Tokenizer 把字符整理成带边界的 token stream，PEG parser 再按有序 grammar 识别程序结构；两者的交接决定源码能否进入 AST 和后续编译阶段。
