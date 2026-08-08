第123章：Syntax Error Recovery
===============================

核心知识点
----------

* Syntax error recovery 的目标不是“把错误代码当成正确代码”，而是把局部结构损坏限制在最小范围，让 parser 能继续分析后续源码。
* Parser 出错时应先判断哪个最小结构已经接近完成，再决定插入 missing token、跳过异常 token，还是退回更外层语法规则。
* Synchronization token 是恢复锚点，常见有 ``;``、``}``、``)``, 换行、缩进边界、声明/语句起始关键字等；可靠同步点取决于语言结构。
* Panic recovery 会跳过 token 直到遇到同步点。它实现简单，但同步集合过宽会吞掉有效代码，过窄则容易形成诊断雪崩。
* 当当前 token 同时是外层结构的重要边界时，优先插入缺失 token 往往比吞掉该 token 更稳。例如调用缺 ``)`` 而当前位置是 ``;``，应保留分号给外层 statement。
* Placeholder node、MissingToken、ErrorNode、SkippedRange 让 parser 在不完整输入上仍能构造 partial AST。
* Partial AST 的核心是“局部可信”：正常节点继续可供 outline、highlight、scope、补全等工具使用，恢复节点显式标记不可靠区域。
* 恢复节点必须保留 source location/range，才能支持 caret、fix-it、IDE 标记以及后续错误抑制。
* 后续语义分析读取 recovered AST 时应降低对错误节点附近结论的置信度，避免一个语法错误产生大量伪类型错误和未定义名字。
* Cascading diagnostics 的控制比“尽可能多报错误”更重要。恢复策略应优先输出少量独立、可行动的根因诊断。
* IDE 场景要求 parser 能长期处理“正在编辑、尚未闭合”的程序，因此 error recovery 是交互式编译基础设施，不只是批量编译器的容错功能。
* 不同语言的恢复锚点不同：C-like 依赖分号/花括号，Python-like 依赖 newline/indent/dedent，数据格式常依赖逗号和闭合括号。

关键路径
--------

局部恢复：

::

   parser expects token/construct
   → mismatch detected
   → identify nearest stable grammar boundary
   → insert missing token if current token belongs to outer rule
   → otherwise skip invalid range to synchronization token
   → create Missing/Error/Skipped node
   → continue building partial AST
   → suppress diagnostics derived only from damaged region

IDE 路径：

::

   incomplete source
   → token stream
   → recovered parse tree
   → mark reliable vs recovered nodes
   → syntax highlighting / outline / scope / completion
   → incremental reparse after edit

概念辨析
--------

* **Syntax recovery 与 semantic recovery**：前者恢复语法结构，后者处理名字、类型等语义失败；两者依赖的证据不同。
* **Missing token 与 skipped token**：前者假设用户漏写结构，后者承认输入中存在无法归入当前规则的真实 token。
* **Partial AST 与 valid AST**：partial AST 可以包含恢复痕迹，不应被后续阶段当作完全可靠程序。
* **Synchronization token 与 ordinary token**：同步 token 的价值来自它能稳定界定更外层结构，而不是某个固定字符天然特殊。
* **More diagnostics 与 better diagnostics**：恢复后继续报更多错误不一定更好，根因清晰且少级联才更有价值。

本章结论
--------

语法恢复的稳定模型是 ``Local Failure → Recover at Stable Boundary → Preserve Partial Structure → Suppress Cascades``。高质量 parser 不只解析合法程序，还要在不完整程序中明确区分可信结构与恢复痕迹，使后续诊断和 IDE 功能仍能继续工作。
