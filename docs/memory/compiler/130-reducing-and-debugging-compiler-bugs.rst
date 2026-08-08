第130章：Reducing and Debugging Compiler Bugs
==============================================

核心知识点
----------

* 编译器 bug 的第一目标不是立刻猜根因，而是把复杂工程失败变成稳定、可自动判断、可重复的最小 testcase。
* Reduction 的核心是不变量：每次删除源码、IR、参数或 pass 后，都必须保留同一个 failure property。
* Interestingness test 是 reducer 的判定器。它应明确描述“什么仍算同一个 bug”，例如固定 crash、verifier failure、``O0`` 与 ``O2`` 输出分歧或特定 codegen 错误。
* 判定器设计决定 reduction 方向。只检查“非零退出”可能保留完全不同的失败；检查具体行为差异、断言或 verifier 文本更容易保持原 bug 身份。
* Source reduction 适合保留语言级复现和 frontend 问题；IR/MIR reduction 更适合 optimizer、backend 与 codegen；pass-pipeline reduction 用于定位最小触发变换序列。
* 缩减层级应从“最早能稳定观察失败的表示”开始。若未优化 IR 正确、优化后 IR 已错误，就应优先缩减 IR 与 pass，而不是继续保留完整源码工程。
* Crash、wrong-code、performance regression、diagnostic regression 需要不同 interestingness predicate；不要用一种判定方式混合多类失败。
* 自动 reducer 的作用是提高可观察性，不是证明根因。最小 testcase 仍需要通过中间 IR、pass 日志、机器码或运行行为分析真正错误的 transformation。
* Pass bisection 的目标是找出“哪一步第一次把好状态变成坏状态”。保存每个关键阶段的 IR，比只看最终汇编更容易定位中端错误。
* Optimization-level bisection 可以先比较 ``O0/O1/O2/O3``，再把对应 pipeline 展开并逐步关闭/二分 pass，缩小触发条件。
* Commit bisection 用历史上已知 good/bad 两端做二分搜索，定位首次引入失败的提交；前提仍是 testcase 和判定器足够稳定。
* Target features、CPU flags、ABI、语言选项、链接方式也可能是 bug 条件，应和源码/IR 一样进入缩减矩阵。
* 修复完成后必须把最小复现转成 regression test。真正闭环是“发现 → 缩减 → 定位 → 修复 → 永久防复发”。
* 编译器 bug 应被当作一个结构化系统：输入、表示、pass、target、版本和观察结果共同决定失败，任何单一维度都可能掩盖根因。

关键路径
--------

Wrong-code 调试：

::

   stable source + commands + environment
   → define reference and failing behavior
   → write interestingness test
   → reduce source or capture IR
   → compare pre/post optimization IR
   → reduce pass pipeline
   → identify first bad transformation
   → inspect generated code/runtime evidence
   → fix
   → add regression test

版本定位：

::

   known-good compiler revision
   + known-bad revision
   + deterministic testcase
   → automated good/bad predicate
   → commit bisect
   → first bad commit
   → inspect changed transformation/invariant

概念辨析
--------

* **Reduction 与 root-cause analysis**：reduction 让 bug 更小、更稳定；它不自动说明根因。
* **Source reducer 与 IR reducer**：前者保留用户语言输入，后者更接近 optimizer/backend 的真实工作表示。
* **Pass bisect 与 commit bisect**：前者定位哪次 transformation 触发，后者定位哪个源码历史提交引入。
* **Interestingness 与 correctness**：interestingness 只定义“候选仍像原 bug”，最终 correctness 仍要回到语言/IR 语义判断。
* **Minimal testcase 与 realistic workload**：最小用例服务归因和 regression，真实 workload 服务确认工程影响；两者用途不同。

本章结论
--------

编译器 bug 调试的稳定模型是 ``Define Failure Precisely → Reduce Representation → Bisect Transformations/History → Preserve as Regression``。复杂工程问题只有被压缩成稳定判定器、最小输入和最短触发路径后，才能从“偶现异常”转成可解释、可修复、可永久防止复发的编译器缺陷。
