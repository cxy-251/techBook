第129章：Differential Testing and Miscompilation Detection
===========================================================

核心知识点
----------

* Miscompilation 是编译器成功接受输入并产出可执行结果，但最终可观察行为违背了源程序或输入 IR 承诺的语义。
* Wrong-code 比 crash 更难发现，因为编译、链接和运行都可能正常结束；测试系统必须额外提供 correctness oracle。
* Differential testing 用多个独立实现、多个优化等级、多个版本或多个后端执行同一有效输入，再比较结果差异。
* 差分测试首先得到的是“存在需要解释的分歧”，并不能自动证明哪一方正确。实现独立性越强，差分证据越有价值。
* ``O0`` 常被当作优化 bug 的参考路线，但它只是启发式基线；低优化编译器、runtime、library 与输入程序自身也可能有问题。
* 差分测试的首要前提是输入具有明确语义。Undefined behavior、unspecified behavior、并发竞态或环境不确定性会破坏输出比较的解释力。
* 随机有效程序生成器的关键能力不是“随机”，而是主动规避 UB、保持类型/作用域/副作用规则，使最终 checksum 成为可靠 oracle。
* Csmith 类方法把“有效随机程序 + 多编译器/多优化级别 + checksum 比较”组合成大规模 miscompilation 搜索。
* Metamorphic testing 不要求多个独立编译器，而是构造语义等价的程序变体，检查同一编译器对等价输入是否保持应有关系。
* 可用 metamorphic relation 包括等价源码重写、优化等级变化、IR canonicalization、输入扰动后应保持的数学关系等。
* 编译器失败类型必须区分：crash/assert、wrong-code、compile-time explosion、runtime performance regression、diagnostic regression 都需要不同 oracle。
* 一旦发现行为差异，应固定源码/IR、编译器版本、target、选项、运行环境、输入与输出，再进入 reduction 与 pass/commit 定位。
* Miscompilation 的最终证据不是“两个二进制不同”，而是“一个具有确定含义的输入在某条编译路径下产生了违背该含义的行为”。

关键路径
--------

差分检测：

::

   generate/select well-defined program
   → compile with A/O0, A/O2, B/O2 or other independent routes
   → run under same inputs/environment
   → compare output + exit status + observable effects
   → disagreement
   → validate language semantics / exclude UB
   → add more independent references
   → isolate suspicious compiler route
   → reduce testcase

Metamorphic 检测：

::

   original valid program
   → semantics-preserving source/IR transformation
   → compile/run original and variant
   → compare promised relation
   → mismatch
   → inspect transformation/optimizer/backend boundary

概念辨析
--------

* **Crash 与 miscompilation**：crash 直接暴露编译器失败，miscompilation 产出“看起来成功”的错误代码。
* **Differential oracle 与 ground truth**：多个实现不一致说明存在候选问题，但多数投票仍不等于形式化真值。
* **Well-defined input 与 random input**：只有语义明确的输入才能让行为差异具有 correctness 含义。
* **Differential testing 与 metamorphic testing**：前者比较不同实现/配置，后者比较具有已知关系的等价或关联输入。
* **Binary difference 与 semantic difference**：机器码不同很正常；只有可观察行为违反语义承诺才构成 wrong-code 证据。

本章结论
--------

Miscompilation 检测的稳定模型是 ``Well-Defined Input → Independent/Equivalent Compilation Routes → Observable Behavior Comparison → Semantic Validation``。差分本身只是报警信号；只有排除输入语义歧义、固定运行条件并把分歧缩到可复现路径后，才能把“结果不同”升级为真正可调试的 compiler wrong-code bug。
