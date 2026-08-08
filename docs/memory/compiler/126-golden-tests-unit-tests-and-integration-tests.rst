第126章：Golden Tests, Unit Tests, and Integration Tests
=========================================================

核心知识点
----------

* 编译器测试的对象不是单个返回值，而是一串表示转换是否持续保持结构与语义。不同测试粒度应绑定不同证据层。
* Unit test 直接测试 lexer、parser、AST、symbol table、type checker、CFG、analysis 等局部组件，目标是快速验证局部算法与数据结构不变量。
* Unit test 的输入应尽量靠近目标组件，避免无关 frontend/backend 阶段把失败定位范围扩大。
* Golden test 用固定输入与人工审查过的稳定输出比较，适合 token dump、AST dump、IR、diagnostic、assembly 等文本表示。
* Golden test 不应机械锁死所有打印细节。应优先固定真正属于契约的结构，规范化随机 ID、临时路径、无关排序与版本噪声。
* Pattern-based checking 比全量文本 diff 更适合部分不稳定的中间表示，因为测试可以只声明“必须出现/不得出现”的关键结构。
* Regression test 是 compiler bug 的长期记忆。修复一个 bug 后，应把最小触发输入与修复后证据保存下来，阻止后续 pass 或 backend 再次引入同类错误。
* Regression test 的价值不在覆盖新功能，而在固定“曾经坏过的语义边界”。用例应比原始 bug report 更小、更稳定、更直接。
* Integration/end-to-end test 从 source 一路穿过 frontend、IR、optimization、backend、link/runtime，最终检查可观察行为，验证各阶段组合起来仍满足语言承诺。
* End-to-end test 覆盖广但定位弱；unit/pass-level test 定位强但覆盖窄。成熟测试体系需要两者并存。
* 测试设计应先问“哪个表示发生变化”，再选择最近的证据点；不要默认所有问题都用端到端运行来验证。
* 编译器正确性最终依赖多层测试共同建立信任：局部结构正确、中间变换可观察、历史缺陷不复发、最终程序行为一致。

关键路径
--------

测试分层：

::

   compiler change / bug
   → identify affected representation
   → nearest local invariant: unit test
   → stable textual representation: golden/pattern test
   → historical bug: regression test
   → cross-stage risk: integration/end-to-end test
   → run all relevant layers in CI

Bug 进入测试套件：

::

   real failure
   → reduce to minimal reproducer
   → identify failing stage
   → encode expected structure/behavior
   → add regression test
   → fix implementation
   → keep test permanently

概念辨析
--------

* **Unit test 与 integration test**：前者隔离局部组件，后者验证多个阶段组合后的行为。
* **Golden test 与 regression test**：golden 描述一种输出验证形式；regression 描述测试目的。一个 regression test 可以使用 golden/FileCheck，也可以直接执行程序。
* **Text equality 与 semantic evidence**：完整文本相等很严格，关键结构匹配更接近编译器真正承诺的语义证据。
* **Coverage 与 diagnosability**：端到端覆盖范围大，局部测试失败定位更强；二者不是替代关系。
* **Bug report 与 regression testcase**：bug report 可以包含复杂工程上下文，regression testcase 应压缩成最小、稳定、可自动判断的失败证据。

本章结论
--------

编译器测试的稳定模型是 ``Local Invariants → Stable Representation Checks → Bug Memory → End-to-End Behavior``。测试层级越接近目标变换，失败越容易定位；测试层级越靠近最终执行，语义覆盖越完整。可靠编译器依赖多层证据共同证明每次表示转换仍值得信任。
