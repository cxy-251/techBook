第004章：Interpreter, Compiler, Transpiler, and JIT
==================================================

核心知识点
----------

* Interpreter、AOT compiler、transpiler 和 JIT 的稳定区别不是语言标签，而是“什么表示在何时被翻译或执行”。
* interpreter 直接消费 AST、bytecode 或 VM instruction 等内部表示；AOT 在运行前完成主要 lowering；transpiler 输出另一种源码；JIT 在运行时根据真实执行状态继续生成机器码。
* 同一语言实现可以组合多种策略，例如先编译 bytecode、解释执行，再对热点路径 JIT。
* 四种策略都遵循表示转换与语义保持，只是转换成本、优化机会和错误证据分布在不同阶段。
* JIT 的核心价值来自 runtime feedback：类型、分支频率、调用目标等动态事实可以驱动 specialization，但依赖 guard 和 deoptimization 保证原始语义。

关键路径
--------

* interpreter：source → AST/bytecode → evaluation loop → runtime effects；主要成本落在运行时取指、分派和动态检查。
* AOT：source → AST → IR → machine code/object → executable；主要编译和优化成本在程序运行前支付。
* transpiler：source language A → AST/IR → source language B → 下游工具链；目标输出仍需再次解析、编译或解释。
* JIT：初始表示先运行 → 收集 profile / type feedback → 识别 hot code → runtime compilation → optimized machine code。
* JIT 假设失效时：guard failure → deoptimization → 恢复到通用表示或较低优化层继续执行。

概念辨析
--------

* **interpreter vs compiler**：解释器也可能先有编译阶段；关键在当前程序表示最终是被直接消费还是被进一步翻译成目标代码。
* **AOT vs JIT**：二者都可以生成机器码，区别主要在生成时机和可利用的信息来源。
* **transpiler vs backend**：transpiler 仍输出源码级语言；backend 输出目标机器或低层执行格式。
* **bytecode VM vs JIT VM**：bytecode 是执行表示，JIT 是运行时继续编译的策略，两者经常共存。
* **specialization vs semantic change**：JIT 可以针对已观察类型优化，但必须保留在假设失效时恢复通用语义的路径。

本章结论
--------

分析一种语言实现时，不要先贴“解释型”或“编译型”标签。应追踪表示在运行前和运行时分别经历什么转换、成本在哪里支付、优化依据来自静态事实还是动态反馈，以及失败时从哪一层证据开始排查。这套模型能同时解释 AOT、bytecode VM、transpiler 和现代分层 JIT。
