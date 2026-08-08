第132章：Implementing Lexer, Parser, and AST
=============================================

核心知识点
----------

* 小编译器 frontend 的第一条稳定链是 ``source text → token stream → parser → AST → diagnostics``。
* Lexer 的职责是把字符流切成 parser 可消费的 token，并保存 source location；它不负责名字绑定和类型判断。
* 一个实用 token 至少包含 ``kind``、``lexeme``、可选 literal value 与 source span。lexeme 保留源码证据，literal 提前提供可计算值。
* Source span 最好能表达文件、起止偏移以及可映射的行列信息；诊断、AST range、fix-it 和后续调试都依赖这组坐标。
* Lexer 必须稳定处理 longest match，例如 ``=``/``==``、``<``/``<=``，并保证扫描位置单调向前。
* Recursive descent 很适合 declaration、statement、block 等由起始 token 明确驱动的结构。
* 表达式 parser 必须显式处理 precedence、associativity、prefix/infix 关系。Pratt parser 或分层 precedence parser 都能完成这一点。
* Parser 的核心契约是：成功时消费一个完整语法结构并返回 AST node；失败时生成 diagnostic，并把 token cursor 推进到可恢复边界。
* AST 应保留后续 semantic analysis 真正需要的结构，而不是复制 parse tree 的全部语法噪声。常见节点包括 Program、Function、Block、Let、Assign、If、While、Return、Call、Binary、Unary、Literal、Name。
* 每个 AST node 应保留 source range，使后续名字、类型和控制流错误能重新锚定到源码。
* Parser recovery 需要区分 missing token 与 unexpected token。当前 token 若明显属于外层结构，应优先插入缺失结构，而不是把外层边界吞掉。
* Partial AST 是合法工程产物：正常节点继续承载可信结构，Missing/Error node 显式标记恢复区域，使 IDE 和后续诊断能继续工作。
* 第一阶段的完成标准不是“parser 能接受几个例子”，而是源码到 AST 的转换可重复、可定位、可恢复并可被测试。

关键路径
--------

Frontend：

::

   source bytes/text
   → lexer scans lexemes
   → Token(kind, lexeme, literal, span)
   → recursive-descent statement parser
   → Pratt/precedence expression parser
   → AST nodes with source ranges
   → syntax diagnostics / partial AST
   → semantic analysis

错误恢复：

::

   expected token/construct
   → mismatch
   → report at current/minimal source range
   → insert missing token if outer boundary should be preserved
   → otherwise skip to synchronization token
   → create Missing/Error node
   → continue parsing later declarations/statements

概念辨析
--------

* **Character/lexeme 与 token**：lexeme 是源码片段，token 是带类别和值/位置的结构化输入。
* **Parse tree 与 AST**：parse tree 更贴近 grammar，AST 只保留后续语义和执行真正需要的结构。
* **Recursive descent 与 Pratt parser**：前者适合声明/语句结构，后者特别适合表达式优先级和结合性。
* **Lexer error 与 parser error**：前者无法形成合法 token，后者已经有 token，但 token 序列不满足 grammar。
* **Valid AST 与 partial AST**：partial AST 可以包含显式恢复节点，后续阶段不能把这些区域当作完全可信结构。

本章结论
--------

Frontend 的稳定模型是 ``Text → Located Tokens → Structured AST → Recoverable Diagnostics``。Lexer 固定最小语法单元，parser 固定结构关系，AST 保存后续阶段所需语义骨架；source range 与恢复节点让错误输入仍然保持可分析性。