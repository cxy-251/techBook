Parser, Bytecode, Baseline Compilation, and Optimizing Compilation
==================================================================

核心知识点
----------

* 现代 JavaScript engine 通常采用分层执行：``source → parse → bytecode / internal representation → interpreter / baseline tier → runtime feedback → optimizing compiler → optimized machine code``。
* parsing 负责词法扫描、语法检查、函数边界、声明和作用域信息；它处理的是解压后的源码，网络压缩只减少传输量，不消除解析成本。
* lazy parsing / preparsing 把暂时不用的函数完整解析成本推迟到首次调用，降低启动路径压力；代码拆分同时减少网络、parse、compile 和初始执行工作。
* bytecode 是引擎内部执行表示，不是跨浏览器发布格式。V8 的 Ignition bytecode、SpiderMonkey / JavaScriptCore 的内部表示都属于实现细节。
* baseline tier 优先“尽快可执行”，避免第一次运行前进行昂贵深度优化。具体引擎可能用 interpreter、快速 baseline compiler 或多个中间 tier。
* optimizing compiler 根据真实运行反馈对热点代码进行专门化，例如稳定对象形状、稳定参数类型、稳定调用目标；收益来自运行时假设成立。
* deoptimization 表示优化假设失效后退出专门化机器码，回到更通用执行层。偶发慢帧可能来自 deopt、GC、主线程竞争，不能只凭源码复杂度判断。
* 具体 tier 名称属于引擎实现：V8 的 Ignition、Sparkplug、Maglev、TurboFan 不应被当成 ECMAScript 或所有浏览器的固定架构。

关键路径
--------

冷启动：

``JS resource → decompress/source → parser / preparser → bytecode/internal IR → interpreter or baseline execution``

热点升级：

``baseline execution → collect type/shape/call feedback → hotness decision → optimizing compiler → optimized machine code``

假设失效：

``optimized code → unexpected type / object shape / call target → deoptimization → generic tier → collect new feedback``

性能判断顺序：

``网络是否慢 → parse/compile 是否占启动时间 → 首次交互是否仍处冷路径 → 热函数是否稳定 → 是否频繁 deopt → 主线程是否还有其它任务竞争``

概念辨析
--------

* **Parsing vs Execution**：parsing 把文本变成可执行结构；execution 才真正运行程序语义。
* **Bytecode vs Machine Code**：bytecode 是引擎私有中间执行层；machine code 是面向当前 CPU 的执行结果。
* **Baseline vs Optimized**：baseline 追求低编译成本和快速启动；optimized tier 追求热点路径峰值性能。
* **JIT vs ECMAScript 语义**：JIT 是实现策略；语言规范只规定可观察语义，不规定必须有几级编译器。
* **Warm-up vs Cache**：重复操作变快可能来自引擎 tier-up，也可能来自 HTTP cache、应用 cache、DOM/数据复用；需要 trace 证据区分。
* **Deoptimization vs Bug**：deopt 本身是动态语言引擎维持正确性的正常机制；持续高频 deopt 才可能成为性能问题。

本章结论
--------

JavaScript 性能不是“源码直接变机器码”。稳定模型是 ``Parse → Baseline → Runtime Feedback → Optimize → Deopt if needed``。启动问题优先看代码体积、解析与低层执行；长期热点问题再看运行反馈、类型与对象形状稳定性。所有具体 tier 名称都应视为目标引擎版本的实现细节。
