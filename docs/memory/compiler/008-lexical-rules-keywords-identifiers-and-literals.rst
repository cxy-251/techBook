第008章：Lexical Rules, Keywords, Identifiers, and Literals
===========================================================

核心知识点
----------

* 词法规则定义字符怎样形成关键字、标识符、字面量、操作符和分隔符；lexer 负责边界与分类，不负责名字绑定和类型检查。
* 关键字与标识符常共享同一名字扫描规则：先按 identifier 形态读完整 lexeme，再查询 keyword table。
* 标识符规则至少定义 ``identifier_start``、``identifier_continue``、大小写策略以及 Unicode/规范化策略。
* 字面量 token 需要保留原始 spelling、源码范围以及足够的值或格式信息，供后续类型判定、常量处理和诊断使用。
* ``-1`` 在多数语言中是 ``Minus`` + ``IntegerLiteral(1)``；负号属于表达式语法，数字 lexer 不应擅自吞并一元运算。
* 多字符操作符依赖 longest match；分隔符负责建立结构边界，具体语法关系交给 parser。

关键路径
--------

* 名字：识别起始字符 → 扫描所有 identifier-continue 字符 → 形成 spelling → keyword lookup → Keyword 或 Identifier token。
* 数字：识别进制/数字主体/分隔符/后缀 → 验证局部格式 → 保存 spelling 与解析信息 → 交给后续类型规则。
* 字符串：识别前缀与起始引号 → 扫描内容 → 处理 escape/raw 规则 → 找终止引号 → 形成 String token 或词法诊断。
* 操作符：根据当前字符查候选 → 尝试最长合法组合 → 输出唯一 token kind；括号、逗号、分号等作为结构分隔 token 直接进入 stream。

概念辨析
--------

* **关键字与普通名字**：``returnValue`` 应整体成为 Identifier，而不是 ``return`` + ``Value``；最长名字匹配先于关键字查询。
* **硬关键字与 soft keyword**：硬关键字由 lexer 直接分类；soft keyword 可以先保持名字 token，由 parser 在特定上下文解释。
* **字面量值与最终类型**：lexer 可解析 ``100_000`` 的数值形态，但最终类型可能依赖后缀、语言规则和目标平台。
* **Unicode 字符与标识符身份**：允许哪些字符、是否 NFKC/NFC 归一、视觉相似字符是否等价，必须由语言规范明确，不能由字体外观决定。

本章结论
--------

词法规则把字符空间收敛成有限 token 类别。阅读或实现 lexer 时，应先找字符分派入口，再分别追踪名字、字面量、操作符和分隔符的扫描路径，始终保持“词法只建立边界、类别、payload 和 source range”的职责边界。