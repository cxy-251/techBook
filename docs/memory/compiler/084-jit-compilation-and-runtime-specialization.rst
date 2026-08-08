第084章：JIT Compilation and Runtime Specialization
===================================================

核心知识点
----------

* JIT 在程序执行期间把 bytecode、IR、trace 或热点函数编译成本机机器码。它和 AOT 的主要区别是编译时可以利用当前进程的真实运行证据。
* JIT 的输入不仅有程序表示，还包括 counters、type feedback、branch behavior、object shapes、call targets 等 runtime profile。
* JIT 的收益来自两部分：消除 interpreter dispatch 开销，以及根据真实运行模式进行 specialization；代价是编译延迟、代码内存、metadata 和 code-cache 管理。
* “代码热”表示预计未来执行次数足以摊销编译成本。Hotness 可以通过函数调用次数、loop backedge、采样时间或其它 profile 证据估计。
* Tiered compilation 用多个执行层级控制成本：interpreter 负责快速启动，baseline JIT 快速生成等价机器码，更高层 optimizing JIT 使用更多分析和 profile 追求峰值性能。
* 层级越高，编译成本通常越大。短生命周期程序、冷函数和一次性路径不值得进入重优化层级。
* Baseline JIT 往往尽量保持 VM frame/bytecode 语义形状，只去掉解释器循环开销；optimizing JIT 才会构造更强 IR、传播类型、内联、去虚拟化和重排代码。
* Runtime type feedback 把动态语言中原本未知的事实转成“过去观察到的稳定模式”，例如某属性访问点长期只看到一种 object shape。
* Speculative optimization 不是无条件相信 profile，而是生成基于假设的 fast path，并用 guard 在执行时验证当前输入仍满足假设。
* 典型属性访问 specialization 是 ``shape guard → fixed-offset load``。只有 guard 通过时，JIT 才能跳过通用动态属性查找。
* Guard 是动态优化正确性的核心。Profile 提供盈利证据，guard 提供当前执行合法性证据；历史上常见不代表当前必然成立。
* Guard 失败后必须进入 generic slow path、lower tier 或 deoptimization；没有安全回退，speculation 就会变成 wrong-code。
* JIT 生成的不只是机器码。还需要保存 bytecode/source mapping、GC safepoints、stack maps、exception metadata、deopt state、profile slots 等，使机器码继续属于 VM/runtime 世界。
* Code cache 管理生成机器码的地址、权限、生命周期和失效。代码可以被替换、回收、重新编译或因为依赖失效而禁止继续执行。
* JIT 的优化决策必须同时看 execution benefit 和 compilation cost。热点阈值、tier promotion、cache pressure 和 deopt frequency 都属于同一收益模型。

关键路径
--------

分层执行：

::

   bytecode/IR
   → interpreter executes
   → collect hotness/profile
   → baseline JIT when profitable
   → keep collecting feedback
   → optimizing JIT for stable hot path
   → install machine code in code cache
   → execute guarded fast path

运行时专门化：

::

   dynamic operation site
   → observe runtime types/shapes/targets
   → profile becomes stable enough
   → build specialized IR
   → emit guard
   → emit direct/fixed fast operation
   → guard fail → slow path or deopt

成本闭环：

::

   expected future executions
   × saved cost per execution
   → compare with compile + memory cost
   → choose interpreter/baseline/optimized tier
   → observe actual behavior
   → promote, keep, invalidate, or discard code

概念辨析
--------

* **JIT 与 interpreter**：interpreter 执行虚拟指令，JIT 把程序表示转换成本机代码后直接执行。
* **JIT 与 AOT**：两者都做编译；JIT 多了运行时 profile、当前 CPU/进程状态和严格的在线编译预算。
* **Profiling 与 proof**：profile 说明过去常见情况，不证明未来必然成立；guard 才把 speculation 转成当前可验证条件。
* **Baseline JIT 与 optimizing JIT**：前者主要减少 dispatch，后者更积极利用反馈和全局分析进行 specialization。
* **Code cache 与 ordinary heap**：code cache 保存可执行机器码及其元数据，需要处理执行权限、入口更新、失效和回收等额外约束。

本章结论
--------

JIT 的稳定模型是 ``Runtime Evidence → Hotness Decision → Compilation Tier → Guarded Specialization → Code Cache``。它的优势不是“运行时编译”本身，而是能把真实执行模式变成更窄的机器码；正确性依赖每个推测假设都有 guard 和安全回退，盈利性则依赖收益足以覆盖在线编译成本。