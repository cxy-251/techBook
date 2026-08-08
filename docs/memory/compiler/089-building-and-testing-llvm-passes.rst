第089章：Building and Testing LLVM Passes
==========================================

核心知识点
----------

* 写 LLVM pass 的第一步不是写 C++ API，而是确定变换需要观察多大范围的 IR：Module、CGSCC、Function 还是 Loop。
* 选择最小足够粒度能减少无关遍历、缩小 analysis invalidation 范围，也让 pass 的正确性前提更清晰。
* Function pass 适合局部 instruction、basic block、SSA def-use 和函数级 analysis；Loop pass 适合 loop header/latch/exit/induction；CGSCC 适合调用图与递归组件；Module pass 适合全局符号和跨函数结构。
* LLVM C++ API 的常见遍历路径是 ``Function → BasicBlock → Instruction``。真正的工程任务是维护 IR invariants，而不是简单修改文本。
* 删除一个产生 SSA value 的 instruction 前，必须先处理所有 uses。``replaceAllUsesWith``、``eraseFromParent`` 这类 API 分别对应 use-def 重写和结构删除。
* 遍历过程中直接删除当前 instruction 容易破坏 iterator；常见做法是安全迭代或先收集待删除对象，再统一 erase。
* 新建 instruction 常通过 ``IRBuilder``；替换已有 SSA value 时 use-def API 往往更直接。API 选择应跟随 IR 变换类型。
* 每个变换都必须回到 LLVM IR semantics 检查合法性。整数 ``add x, 0`` 可以安全简化；看起来类似的浮点变换可能受 signed zero、NaN、rounding、fast-math flags 影响。
* Pass 的 ``run`` 返回 ``PreservedAnalyses``，它描述改写后哪些 analysis cache 仍有效。初版实现宁可保守失效，也不能虚假保留。
* Pass plugin 把 C++ pass 类型暴露给 ``opt`` pipeline。注册入口、plugin ABI/version 和 textual pass name 都是工具链契约的一部分。
* ``PassBuilder`` 的 pipeline parsing callback 把例如 ``remove-add-zero`` 的文本名称映射到具体 FunctionPass/ModulePass 对象。
* ``opt`` 是测试和观察中端 pass 的关键入口：它可以加载 plugin、运行指定 ``-passes=`` pipeline，并输出变换后的 LLVM IR。
* Pass 测试应尽量直接从最小 ``.ll`` 输入开始，减少 frontend/backend 噪声。一个局部 IR transform 通常不需要用完整 C/C++ 程序才能验证。
* FileCheck 适合验证“关键结构存在/不存在”，例如 ``CHECK: ret i32 %x`` 与 ``CHECK-NOT: add i32``；不应无必要地锁死整个 IR 文本、临时变量名或无关格式。
* Regression test 是 compiler bug memory。每个修复过的 pass bug 都应留下能稳定触发旧错误、验证新行为的最小测试。
* Pass 测试至少要验证三层：目标 transformation 是否发生、结果 IR 是否 verifier-valid、特殊边界是否不会错误变换。
* 负面用例同样重要，例如非零常量、浮点 add、带特殊 flags 的操作、不同位宽或控制流环境，确保 pattern 只匹配证明成立的情况。
* 一个 production pass 的完成标准不是“能跑”，而是 ``Precise Scope + Legal Rewrite + Correct Analysis Preservation + Regression Tests``。

关键路径
--------

实现 pass：

::

   define optimization goal
   → choose smallest IR granularity
   → identify semantic preconditions
   → traverse LLVM objects
   → query required analyses
   → rewrite use-def / CFG safely
   → report PreservedAnalyses
   → run verifier

插件与 opt：

::

   C++ pass type
   → register plugin entry
   → PassBuilder textual name
   → build shared plugin
   → opt -load-pass-plugin
   → -passes=<name>
   → transformed .ll output

回归测试：

::

   minimal input.ll
   → RUN opt with target pass
   → FileCheck expected structure
   → verifier confirms valid IR
   → add negative/edge cases
   → keep test with future changes

概念辨析
--------

* **Pass implementation 与 text rewriting**：LLVM pass 操作内存对象、SSA uses 和 CFG，不是对 ``.ll`` 字符串做搜索替换。
* **Function pass 与 Module pass**：区别是观察/修改范围和 analysis 层级，不是“代码多少”。
* **IRBuilder 与 replaceAllUsesWith**：前者偏向构造新 IR，后者偏向重定向已有 SSA use。
* **FileCheck 与 exact golden file**：FileCheck 更适合断言关键结构，避免对无关文本细节过拟合。
* **Transformation test 与 execution test**：IR pass 首先应有 pass-level test；端到端执行测试可补充语义验证，但不能替代精确的 IR 回归证据。

本章结论
--------

LLVM pass engineering 的稳定闭环是 ``Choose Scope → Prove Legality → Rewrite IR → Preserve/Invalidate Analyses → Verify → FileCheck Regression``。真正困难的不是遍历 API，而是把每次改写限制在可证明的语义边界内，并把这个边界固化成长期可回归的测试。