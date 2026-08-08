第085章：Deoptimization, Inline Caches, and Dynamic Feedback
============================================================

核心知识点
----------

* Dynamic optimization 依赖一个闭环：runtime 先观察真实执行，inline cache/profile 记录常见形态，JIT 基于这些证据生成专门化代码，现实变化时再通过 slow path 或 deoptimization 撤回。
* Inline cache（IC）附着在具体动态操作 site 上，记录“这个位置过去看到过什么”，例如 receiver shape、字段偏移、调用目标或属性查找结果。
* IC 缓存的通常不是属性值本身，而是查找路径。对 ``point.x``，更有价值的是 ``ShapeXY → offset_x``，因为不同对象的 ``x`` 值可以不同。
* IC 的正确性来自“先验证当前 receiver 是否匹配已记录形态，再复用快路径”。历史记录只是优化提示，当前对象必须重新通过 guard。
* Monomorphic site 长期看到一种 shape/target，最适合生成单个 guard + direct/fixed operation。
* Polymorphic site 看到少量几种 shape/target，可以生成有限比较链或多版本快路径；成本来自额外分支和代码体积。
* Megamorphic site 看到大量不同形态，继续内联枚举通常失去收益，runtime 往往退回共享 stub、哈希缓存或通用查找。
* Site 稳定性会影响更多优化。Monomorphic call 更容易 inline，monomorphic property access 更容易固定字段偏移；megamorphic site 常保留间接/通用路径。
* Dynamic feedback 是 JIT 的输入数据，而不是语言语义。优化器可以利用它改变代码形状，却必须保持所有合法输入下的语言行为。
* Deoptimization 是从优化机器码撤回到解释器、baseline tier 或通用执行层的机制，用于处理 guard 失败、依赖失效或 speculative assumptions 不再成立。
* Deopt 不能只“跳回解释器”。优化机器码可能已经消除了源码变量、内联多个函数、把对象拆成 SSA values，因此 runtime 必须重建较低层级所需的完整执行状态。
* Deoptimization metadata 需要描述 machine PC 对应的 bytecode/source position、虚拟 frame、locals、operand stack、inline frames 和 materialized objects。
* Scalar replacement/escape optimization 可能让一个源码对象从未真正分配；deopt 时如果解释器状态需要该对象，runtime 必须根据 metadata 重新 materialize。
* Dependency invalidation 处理“当前机器码假设的外部事实变化”，例如对象布局/原型/类层级变化。失效可以触发代码标记无效、patch entry 或下一次执行 deopt。
* Frequent deopt 表示 specialization 与真实 workload 不稳定匹配，会浪费编译时间并增加执行抖动；性能分析要同时看 IC state、guard failures 和 recompilation/deopt rate。
* Dynamic optimization 的安全边界是可逆性：优化层可以大胆假设，但必须能检测假设失效，并把程序恢复到语义等价、可继续执行的状态。

关键路径
--------

Inline cache：

::

   dynamic site executes
   → no matching IC entry
   → generic lookup/dispatch
   → observe receiver shape/target
   → update site feedback
   → next execution checks shape/target
   → match? execute cached fast path
   → miss? generic path / extend IC

Site 状态演化：

::

   uninitialized
   → monomorphic
   → a few receiver shapes: polymorphic
   → too many unstable shapes: megamorphic
   → use increasingly generic dispatch strategy

Deoptimization：

::

   optimized machine code
   → guard/dependency fails
   → locate deopt metadata for current PC
   → reconstruct virtual inline frames
   → recover/materialize locals, stack values, objects
   → resume at bytecode/lower-tier position
   → collect new feedback / maybe recompile

概念辨析
--------

* **Inline cache 与 value cache**：IC 主要缓存动态查找/分派路径，不是简单保存上一次属性值。
* **Monomorphic 与 monotyped function**：monomorphic 描述某个具体 site 的运行时历史，不表示整个函数或语言静态只有一种类型。
* **Slow path 与 deoptimization**：slow path 可以在当前优化代码框架中完成通用操作后返回；deopt 会离开当前优化层并重建较低层执行状态。
* **Guard failure 与 program error**：guard 失败只表示优化假设不成立，不表示用户程序非法；正确运行时必须有语义完整的回退。
* **Deopt metadata 与 debug info**：前者服务运行时恢复正确性，必须重建可执行 VM 状态；debug info 主要服务开发者观察，允许更不完整。

本章结论
--------

动态 JIT 的核心不是“猜得准”，而是 ``Observe → Cache/Profile → Specialize → Guard → Recover``。Inline cache 把动态行为压成 site-local 证据，JIT 把证据变成快路径，deoptimization 则保证现实变化时仍能恢复完整语言状态；能安全撤回，才允许运行时进行激进推测优化。