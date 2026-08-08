第127章：IR Tests and Pass-Level Verification
==============================================

核心知识点
----------

* IR-level test 把输入直接固定在中间表示层，跳过 frontend 与 backend 噪声，使测试能精确观察某个 pass 的输入、输出与结构不变量。
* Pass 测试的目标不是只证明“程序还能跑”，而是证明目标 transformation 确实发生，并且转换后的 IR 仍合法。
* 最小 IR 用例应只保留触发目标行为所需的类型、基本块、属性、metadata 与控制流。输入越小，pass 前提和失败原因越容易看清。
* FileCheck/pattern-based validation 应围绕语义结构写断言：用 ``CHECK-LABEL`` 建立作用域，用正面检查证明新结构出现，用 ``CHECK-NOT`` 证明旧结构消失。
* 测试应避免过度依赖临时 SSA 编号、属性打印顺序、metadata ID 等非本质文本细节；必要时使用捕获变量表达值之间的关系。
* ``CHECK-NEXT``、``CHECK-SAME``、``CHECK-DAG`` 等约束应只在顺序本身属于语义证据时使用，否则会把格式变化误判成编译错误。
* 单独运行一个目标 pass 能最大限度减少 pipeline 交互。若目标 pass 依赖 loop-simplify、LCSSA 等前置形态，应显式写出最小必要 pipeline。
* 完整 ``O2/O3`` pipeline 能证明集成效果，但很难证明是哪一个 pass 完成或破坏了变换；pass-level test 应优先隔离目标阶段。
* Verifier 与文本检查承担不同职责。FileCheck 证明“想要的结构出现了”，verifier 证明“IR 仍满足类型、SSA、CFG、dominance 等内部规则”。
* ``verify-each`` 这类策略能把“后面才暴露的非法 IR”提前定位到刚刚执行的 pass，显著缩短 debugging 路径。
* Analysis pass 也可以通过 printer/pass dump 变成可测试输出，检查 dominance、loop info、alias facts 等分析结果是否符合预期。
* 一个 pass 测试最好同时包含 transformation evidence 与 invariant evidence：既验证优化发生，也验证生成的表示可被后续 pipeline 信任。

关键路径
--------

Pass 级测试：

::

   failing or target transformation
   → capture/minimize IR input
   → run target pass or minimal prerequisite pipeline
   → print resulting IR
   → check positive transformation evidence
   → check old/illegal structure is absent
   → run verifier
   → store as regression test

定位非法 IR：

::

   full pipeline failure
   → save intermediate IR
   → narrow pass sequence
   → enable verifier after each pass
   → first verifier failure
   → inspect transformation that just ran
   → minimize IR precondition

概念辨析
--------

* **Source test 与 IR test**：source test覆盖 frontend 生成过程，IR test 直接固定中间表示，更适合隔离 optimizer/lowering 行为。
* **Output pattern 与 verifier**：前者检查测试作者期待的结构，后者检查编译器定义的通用 IR 不变量。
* **Target pass 与 full optimization pipeline**：前者便于归因，后者便于验证真实集成效果。
* **Positive evidence 与 negative evidence**：不仅要确认新结构出现，还要确认旧结构、非法 op 或未 lower 的高层表示已经消失。
* **Minimal prerequisite 与 accidental dependency**：目标 pass 可以依赖明确前置形态，但测试不应依赖完整 O2 pipeline 偶然提供的环境。

本章结论
--------

Pass 测试的稳定模型是 ``Minimal IR → Isolated Transformation → Structural Checks → Verifier``。高质量 IR 测试既证明 pass 做了该做的变换，也证明它没有破坏表示不变量；这比只观察最终程序“还能运行”提供更直接、更可定位的编译器证据。
