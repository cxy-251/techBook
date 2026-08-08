第121章：Diagnostics as a Compiler User Interface
==================================================

核心知识点
----------

* Diagnostic 是编译器把内部事实交给程序员、IDE 和 CI 的用户界面，不是附带日志。
* 一条完整诊断通常包含 source location/range、severity、primary message、source evidence、related information 与可选 action hint。
* ``error`` 表示当前输入无法形成合法产物；``warning`` 表示可疑但通常仍可继续；``note`` 补充主诊断证据；``help`` 给出修复方向；``remark`` 常用于优化或代码生成反馈。
* 严重性与事实要分离。同一事实可因构建策略从 warning 升级为 error，但底层语义判断没有改变。
* 高质量诊断应先说明用户代码中的问题，再补充编译器内部推理；不要让用户先理解符号表节点、模板替换细节或 pass 名。
* Source range 应尽量落在真正参与失败的最小源码片段，related range 再连接声明点、候选、宏展开或实例化上下文。
* 诊断生产端应优先生成结构化记录，再由 terminal、IDE、CI 等 renderer 各自呈现；不要把字符串排版直接耦合进语义分析器。
* IDE 需要 range、severity、code、related information 与 code action；CI 更关心稳定、可解析、可聚合的输出；终端更关心紧凑与可读。
* Warning flag、diagnostic code 与机器可读字段构成长期工具接口，因此命名与稳定性也属于编译器兼容性的一部分。
* 诊断质量直接影响工程效率：位置越准、原因越清、证据越完整、动作越安全，用户越少把时间花在猜测编译器意图上。

关键路径
--------

诊断生成链：

::

   lexer / parser / sema / optimizer facts
   → identify failure or noteworthy fact
   → attach primary source location/range
   → classify severity + diagnostic code
   → attach related declarations/candidates/context
   → attach safe hint/fix-it if available
   → structured diagnostic record
   → terminal / IDE / CI renderer

用户阅读链：

::

   severity
   → primary location
   → primary message
   → highlighted source evidence
   → notes / related locations
   → safe next action

概念辨析
--------

* **Diagnostic 与 log**：diagnostic 面向用户决策，log 主要面向实现调试。
* **Error 与 warning**：前者通常阻断合法产物，后者表达风险；构建策略可以改变 warning 的处理级别。
* **Note 与 primary diagnostic**：主诊断给结论，note 负责补充推理链和跨位置证据。
* **Structured diagnostic 与 rendered text**：前者是稳定事实记录，后者只是终端、IDE 或 CI 的显示形式。
* **Compiler fact 与 build policy**：编译器发现什么是事实层，当前项目是否把它视为失败属于策略层。

本章结论
--------

诊断系统的稳定模型是 ``Compiler Facts → Structured Evidence → Human/Tool Action``。优秀编译器不只要发现错误，还要把位置、原因、上下文和修复方向压缩成用户能立即验证的接口；如果失败解释不清，编译器本身就会成为调试成本的一部分。
