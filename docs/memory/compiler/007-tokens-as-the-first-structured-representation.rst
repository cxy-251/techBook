第007章：Tokens as the First Structured Representation
======================================================

核心知识点
----------

* Token 是源码第一次变成编译器结构化数据的结果；lexer 把连续字符切成带类别、边界和位置的单位。
* Lexeme 是源码中的实际字符片段；token 是编译器对该片段的内部记录。多个不同 lexeme 可以共享同一 token kind。
* 一个实用 token 通常包含 ``kind``、源码 spelling/lexeme、可选 value 和 source location/range。
* parser 主要消费 token kind 和顺序，不再重新处理字符级边界；名字绑定、类型是否合法仍由后续语义阶段完成。
* 多字符操作符、数字、名字等通常遵循 longest match/maximal munch，token 边界一旦切错会直接污染 parser 输入。

关键路径
--------

* 解码字符 → lexer 从当前位置选择扫描规则 → 找到最长合法 lexeme → 分类 token kind → 记录 value/位置 → 推入 token stream → parser 消费。
* 名字路径：扫描完整 identifier spelling → 查询 keyword table → 命中则输出关键字 token，否则输出 Identifier。
* 操作符路径：从当前字符尝试更长合法组合，例如 ``=`` 与 ``==``，优先输出最长可接受 token。
* parser 路径：``peek`` 当前 token → 根据 grammar 检查 kind → ``consume`` → 不匹配时直接使用 token location 产生语法诊断。

概念辨析
--------

* **lexeme 与 token**：lexeme 是源码证据，token 是分类后的内部对象；不要把源码文本本身等同于 token。
* **token kind 与 token value**：kind 表示语法类别；value 是字面量值、interned identifier 等附加数据，不是所有 token 都需要 value。
* **token stream 与 AST**：token stream 只有顺序和类别；AST 才表达运算符层级、声明、语句和树形结构。
* **词法错误与语义错误**：lexer 能判断字符是否形成合法 token，不能判断标识符是否声明、操作数类型是否匹配。

本章结论
--------

Token stream 是 parser 的稳定输入边界。阅读 lexer 时，应依次确认 lexeme 边界、token kind、附加 value 和 source location；任何边界或分类错误都会沿 parser、AST 和后续语义分析继续放大。