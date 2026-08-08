第125章：Designing Diagnostics for Human Understanding
======================================================

核心知识点
----------

* Diagnostic design 的目标是把编译器内部失败事实映射到用户分析程序时使用的心智模型，而不是把 solver、AST 节点或内部约束原样打印出来。
* 主消息应优先使用用户能直接修改的对象：变量、参数、返回值、成员、导入、声明、调用，而不是内部编号或临时类型变量。
* 一条可读诊断通常按“结论 → 主源码范围 → 相关事实 → 下一步动作”组织，展示顺序应服务修复过程。
* Locality 要区分检测点与原因点。Parser、type checker、macro/template instantiation 发现问题的位置，不一定是用户最应该修改的位置。
* Primary range 应尽量指向根因；secondary/related range 用于连接 previous declaration、parameter declaration、macro expansion、generic constraint 等上下文。
* Actionability 不是强行提供自动修复，而是把修改空间缩小到可判断范围，例如改实参、补 import、调整类型、补括号、检查候选或添加约束。
* Safe edit 与 explanatory suggestion 要分离。局部、唯一、高置信的编辑可以成为 quick fix；可能改变 API、运行时语义或依赖选择的建议应保留人工确认。
* 拼写修复、缺失分号等通常适合自动 fix；自动类型转换、自动导入、多候选 API 替换等风险更高。
* 诊断应区分确定事实与推测。确定事实进入主消息，候选猜测更适合 help、note 或可选 code action。
* IDE/LSP 需要机器可读的 range、severity、code、related information 与 edits；命令行文本只是同一结构化诊断的一种 renderer。
* Diagnostic code 应稳定，使文档、CI 策略、IDE quick fix、搜索和测试都能围绕同一错误类别工作。
* 错误恢复、fix-it、IDE 集成与 wording 都是编译器产品能力。Developer experience 不是“编译器核心之外”的装饰层。
* 好诊断的终极标准是：用户能否快速建立正确问题模型，并知道接下来检查或修改什么。

关键路径
--------

面向人类的诊断设计：

::

   compiler failure fact
   → translate internal relation into user-facing concept
   → choose root-cause primary range
   → add only relevant related evidence
   → distinguish fact from suggestion
   → derive actionable repair surface
   → emit safe quick fix only when confidence is high
   → serialize structured diagnostic
   → render in CLI / IDE / CI

Quick-fix 风险判断：

::

   proposed edit
   → local and syntactically precise?
   → unique/high-confidence intent?
   → preserves intended semantics with high confidence?
   → no cross-module/package ambiguity?
   → preferred automatic fix
   → otherwise explanatory help or candidate list

概念辨析
--------

* **Compiler mental model 与 user mental model**：前者围绕内部数据结构和约束，后者围绕源码对象和程序意图。
* **Detection point 与 cause point**：编译器在哪里发现失败，不一定等于用户应该修改哪里。
* **Actionable diagnostic 与 automatic fix**：可行动只要求缩小修复空间，自动 fix 还要求编辑足够安全确定。
* **Fact 与 suggestion**：事实是编译器已证明的关系，suggestion 是对用户意图的推测。
* **Human-readable 与 machine-readable diagnostics**：前者服务阅读，后者服务 IDE、CI、自动修复与工具链；两者应共享同一结构化事实源。

本章结论
--------

面向人类的诊断设计可压缩为 ``Align Mental Model → Point to Cause → Provide Evidence → Offer Safe Action``。Developer experience 是编译器正确性接口的一部分：编译器不仅要知道程序为什么失败，还要让用户以最短路径理解这个失败并完成修复。
