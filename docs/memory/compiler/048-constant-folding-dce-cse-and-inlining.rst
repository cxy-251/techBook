第048章：Constant Folding, DCE, CSE, and Inlining
=================================================

核心知识点
----------

* Constant folding、DCE、CSE 和 inlining 分别解决“已知值直接算掉”“无贡献计算删除”“重复工作复用”“函数边界展开”四类基础优化问题。
* Constant folding 要求 operation 的结果在编译期唯一确定，并且求值过程没有必须保留的副作用、异常或环境依赖。
* Constant propagation 与 folding 经常连续发生：先把已知常量沿 def-use 传播到使用点，再把全常量 expression 直接求值。
* 整数溢出、``nsw/nuw``、poison、浮点 rounding/NaN/fast-math、目标数据布局都会影响 folding 是否合法。
* DCE 的必要条件是 result 没有 live use；充分条件还要求 defining operation 没有可观察副作用。无用 SSA value 与可删除 instruction 不是同一件事。
* DCE 往往递归发生：删除一个 dead instruction 后，它的 operands 可能失去最后一个 user，从而暴露新的 dead definitions。
* CSE/GVN 复用的是语义等价值，不是文本相同表达式。必须比较 opcode、type、operand identity、flags、dominance 和 relevant memory effects。
* 普通纯算术的 CSE 较直接；load/call 的冗余消除需要 alias、memory dependence 或函数 effect summary 证明中间状态没有变化。
* Inlining 把 callee body 展开到 caller call site，并用实参替换形参。它不仅减少调用边界，还会暴露跨函数常量、CSE、DCE、branch simplification 等新机会。
* Inlining 不是越多越好。成本模型要权衡 call overhead、后续优化收益、代码体积、I-cache、编译时间、递归和调试信息膨胀。
* Inline 后必须正确重建 return 合流、异常/unwind 路径、局部 value、debug info 与调用图关系；它是大粒度 CFG/IR 重写。
* 四类优化的真正威力来自组合：inline 暴露常量，folding 简化计算，CSE 合并重复值，DCE 删除因此失去用途的节点。
* 优化 pipeline 经常反复运行轻量 canonicalization 和 cleanup，因为一个 pass 的输出会改变另一个 pass 的前提。

关键路径
--------

Constant folding：

::

   operation
   → prove operands compile-time known
   → check integer/fp/poison/effect semantics
   → evaluate result
   → replace SSA uses with constant
   → delete old pure instruction if dead

DCE：

::

   observable roots
   → walk use-def dependencies backward
   → identify unneeded definitions
   → check side effects / exceptions
   → delete safe dead instructions
   → recursively recheck operands

CSE/GVN：

::

   new computation
   → find dominating candidate
   → compare opcode/type/operands/flags
   → verify memory/effect equivalence
   → replace uses with existing value
   → remove redundant computation

Inlining：

::

   call site + callee
   → evaluate inline cost
   → clone callee CFG/body
   → substitute arguments
   → reconnect returns/exceptions
   → update call graph/debug info
   → run local cleanup and scalar optimization

概念辨析
--------

* **Constant propagation 与 folding**：传播把常量事实送到 use；folding 对已经确定的 operation 直接求值。
* **Dead result 与 removable instruction**：result 无人使用还要继续检查 operation 本身是否有副作用。
* **CSE 与字符串去重**：CSE 判断的是 IR 语义等价和可用性，不是源码写法相同。
* **Inlining 与 macro expansion**：inline 在已完成语义分析的 IR 上复制函数体并维护 CFG/异常/值关系，不是简单文本替换。
* **Inlining benefit 与 code size**：展开调用可以创造优化机会，也可能造成代码膨胀和缓存压力。

本章结论
--------

基础优化应按“已知值—值用途—等价计算—调用边界”连续理解。Constant folding、DCE、CSE 和 inlining 单独都是局部规则，放入 pipeline 后会彼此制造新事实和新删除机会；每一步仍必须以类型、控制流、内存、副作用和可观察语义为合法性边界。