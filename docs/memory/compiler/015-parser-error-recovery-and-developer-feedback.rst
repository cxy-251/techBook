第015章：Parser Error Recovery and Developer Feedback
====================================================

核心知识点
----------

* Syntax error 是 parser 已经承诺某条 grammar 路径后，当前 token 无法继续闭合结构的断点。
* 一个高质量语法诊断至少要保存：已接受前缀、当前规则上下文、expected token 集合、actual token、source range 与恢复动作。
* Local recovery 优先尝试最小修改：合成缺失 token 或删除一个多余 token；只有局部恢复不可靠时才进入 panic mode。
* Panic mode 通过跳过输入直到 synchronization token 重新建立结构边界；常见同步点包括 ``;``、``}``、换行或下一条声明/语句的起始 token。
* 恢复策略必须保证输入位置前进，并尽量减少 cascading errors；错误节点应阻止后续阶段把“不可信子树”继续解释成大量派生错误。
* 面向用户的 diagnostic rendering 应把内部 token 枚举翻译成源码符号和上下文概念，并只在修复足够确定时给 fix-it。

关键路径
--------

``parser 当前状态 → expected set 与 actual token 不匹配 → 建立 diagnostic → 尝试 missing-token insertion → 尝试 single-token deletion → panic-mode 同步 → 构造 error/synthetic node → 继续解析``。

例如函数参数列表后缺少 ``)`` 且直接看到 ``{``：parser 知道 ``{`` 可以合法跟在 ``)`` 后，因此可报告缺失右括号并合成 synthetic ``)``，随后继续解析 block。变量声明末尾缺少 ``;`` 而下一 token 是 ``if`` 时，也可把 ``if`` 识别为下一条语句起点，在其前合成分号。局部解释不稳定时，才跳到同步 token。

概念辨析
--------

* **Syntax error vs lexical error**：lexer 发现字符无法形成合法 token；parser 发现合法 token 无法放入当前结构。
* **Local recovery vs panic mode**：local recovery 只增删极少 token；panic mode 会跳过一段输入直到重新同步。
* **Expected token vs human label**：内部可能是 ``RightParen`` 或一大组 token；用户消息更适合显示 ``')' after parameter list`` 或 ``expected expression``。
* **Primary error vs cascading error**：primary error 是最早破坏结构的真实断点；后续大量“缺少表达式/未知语句”可能只是恢复不当产生的级联噪声。
* **Fix-it vs recovery**：recovery 是让 parser 内部继续工作；fix-it 是给用户的源码修改建议，两者可以使用同一假设，但 fix-it 的确定性要求更高。

本章结论
--------

Parser 错误恢复的目标不是强行接受坏源码，而是在保留真实断点的同时尽快重新建立可信结构。实现和评估语法诊断时，应优先检查 expected/actual、source range、局部恢复、同步集合和级联错误控制，确保一次真实错误不会污染整份后续分析。