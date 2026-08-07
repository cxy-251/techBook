第005章：Compiler Correctness, Performance, and Developer Experience
===================================================================

核心知识点
----------

* 编译器工程同时承担三类目标：保持程序语义、控制编译与运行成本、向程序员提供可行动的诊断和调试证据。
* correctness 是第一契约；任何性能收益都必须建立在 semantic preservation 成立的前提上。
* 性能至少分三层：生成程序的 runtime performance、编译器自身的 compile time / memory cost、开发者的 edit-compile-debug latency。
* diagnostics 是编译器公共接口的一部分，依赖 lexer、parser、semantic analysis 保存的 source location、range、binding 和 type facts。
* 优化会压缩源码变量、语句和控制流，因此 debug info 只能尽力把机器状态映射回源码，不能保证优化后仍有完整源码视图。

关键路径
--------

* 正确性检查：固定语言版本与目标平台 → 写出源码可观察行为 → 定位发生的表示转换 → 验证输出仍满足语义契约。
* 性能分析：区分 runtime、compile-time 和 developer latency，再为每类目标选择 benchmark、profile、构建日志或增量构建时间等对应证据。
* 优化 pass 只有在前提成立时才能改写程序，例如无副作用、无别名冲突、控制流事实成立或溢出规则允许。
* 诊断链：source range / token → AST context → name/type facts → primary diagnostic → note / candidate / fix-it。
* 调试链：optimized IR / machine code → debug metadata → address/source mapping → debugger variable/location view。

概念辨析
--------

* **correctness vs performance**：前者决定转换是否合法；后者只在合法转换集合中选择成本更低的实现。
* **runtime performance vs compile time**：运行更快可能需要更昂贵的分析和优化，二者不能用同一指标评价。
* **diagnostic vs debug info**：diagnostic 服务编译期错误反馈；debug info 服务已生成程序的源码级观察。
* **源码变量不存在 vs 程序错误**：优化后变量没有独立位置是正常现象，只要程序语义仍被保持。
* **warning / error / fix-it**：严重级别说明问题性质；fix-it 只有在替换足够确定时才应自动给出。

本章结论
--------

评价编译器不能只看生成代码速度。稳定的判断顺序是：先验证语义正确性，再衡量运行与编译成本，然后检查诊断是否能定位根因，最后评估优化后调试证据是否足够。编译器质量本质上是 correctness、performance 与 developer experience 三条约束的共同结果。
