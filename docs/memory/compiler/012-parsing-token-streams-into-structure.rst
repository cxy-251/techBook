第012章：Parsing Token Streams into Structure
=============================================

核心知识点
----------

* Parser 消费 token stream，把线性 token 序列组织成 parse tree、AST 或其它语法结构；核心状态是当前位置、部分结构和当前规则调用栈。
* Parsing 的基本动作是 predicting、matching、consuming：先根据当前 token 与 lookahead 预测规则，再检查 token 是否符合期待，成功后消费并推进位置。
* Recursive descent 用函数对应 grammar 规则；Pratt parsing 主要解决表达式优先级；PEG 用 ordered choice、lookahead 与 cut 控制选择；LR 用状态机和 shift/reduce 建立结构。
* Lookahead 用于区分共享前缀的规则；回溯允许撤销暂时选择；commit/cut 会缩小回退空间，把后续失败归入已选路径。
* Parser 的诊断证据应保留失败位置、expected token、actual token、规则上下文以及是否发生回退或提交。

关键路径
--------

``token stream → peek/lookahead → 选择 grammar 路径 → match → consume → 构造部分节点 → commit 或回退 → 完成结构``。

例如 ``let total = price + tax * 2;``：statement 看到 ``LET`` 后进入声明规则，依次消费 ``LET``、``IDENT``、``EQUAL``，随后调用 expression parser，表达式完成后期待 ``SEMICOLON``。每一次成功消费都会扩大当前节点的 source range，并减少后续可解释空间；出现失败时，应从当前规则、最远失败位置和期待集合判断真正断点。

概念辨析
--------

* **Predict vs match**：predict 选择可能的规则；match 判断当前位置 token 是否满足选中的规则。
* **Lookahead vs consume**：lookahead 只观察；consume 会推进输入并把 token 纳入当前结构。
* **Backtracking vs commit**：backtracking 允许撤销候选路径；commit/cut 表示某个前缀已经足以确认规则，不再回到更早分支。
* **Recursive descent vs Pratt**：recursive descent 适合整体 grammar；Pratt 主要把 prefix/infix/postfix 与 binding power 集中到 expression parser。
* **PEG vs LR**：PEG 依赖有序选择和可控回溯；LR 依赖状态栈与 shift/reduce 决策。两者目标都是把同一 token stream 收敛成确定结构。

本章结论
--------

Parsing 是在有限上下文中持续做受控承诺。阅读 parser 时，应跟踪当前位置、lookahead、规则选择、消费动作、回退边界和输出节点；判断错误质量时，则看 parser 是否能把最远失败位置、期待 token 集合和规则上下文转成稳定诊断。