第057章：Loop Invariant Code Motion and Strength Reduction
==========================================================

核心知识点
----------

* LICM（Loop Invariant Code Motion）把循环内每次迭代都得到相同结果的计算移出重复路径；strength reduction 把随迭代规律变化的昂贵运算改写成更便宜的递推。
* Loop-invariant 是相对于具体循环而言。定义在循环外的 SSA values 天然稳定；定义在循环内的值还要继续沿 def-use 检查其输入是否都不随迭代变化。
* 表达式“值不变”不等于“可以移动”。Hoisting 还必须满足 dominance、执行域、副作用、内存别名、异常/trap 与 UB 条件。
* Preheader 是 LICM 的标准落点：它位于循环外且进入循环前必经，使提升后的 definition 仍支配循环内 users。
* Sinking 把只在退出后需要的计算移动到 exit，减少循环内重复执行，也可能缩短 value live range。
* 纯整数/位运算通常容易移动；store、volatile、atomic、未知 call、I/O 等具有可观察 effect 的操作不能按普通纯计算处理。
* 循环内 load 是否 invariant 取决于目标 memory location 是否在所有迭代中保持不变。任何可能别名的 store/call 都可能成为 clobber。
* Hoist load 需要证明 loop 内没有 Mod 该位置的 memory operation；MayAlias 时通常必须保留 load 在循环体内。
* Speculative execution 是 LICM 的重要边界。原来只在部分迭代/分支执行、且可能 trap/抛异常的操作，不能无条件提升到 preheader。
* Strength reduction 常围绕 induction variable。若 ``i`` 每轮加固定步长，则 ``base + i*stride`` 可改写成指针/地址每轮递增 ``stride``。
* 乘法改递增并非永远更快；现代目标对乘法、LEA、地址模式和寄存器压力有自己的成本，最终仍需 target cost model。
* Strength reduction 必须保持整数位宽、overflow、pointer provenance 和地址空间语义，不能只按数学等式改写。
* LICM 与 strength reduction 经常协同：先把 loop-invariant 基址/步长移出循环，再把每轮地址计算改成 recurrence。

关键路径
--------

LICM：

::

   instruction in loop
   → prove operands loop-invariant
   → check side effects / alias / exceptions
   → check speculative safety
   → ensure new position dominates uses
   → hoist to preheader or sink to exit

内存不变量：

::

   load inside loop
   → identify address/range
   → inspect all loop MemoryDefs/calls
   → prove none may clobber target
   → mark load invariant
   → hoist when execution safety permits

Strength reduction：

::

   induction variable
   → recognize affine expression
   → derive initial value + fixed step
   → compute initial result before loop
   → update result incrementally per iteration
   → verify overflow/address semantics

概念辨析
--------

* **Loop-invariant 与 movable**：结果不随迭代变化只是必要条件，移动仍要满足 effect、exception 和执行域约束。
* **Hoisting 与 speculative execution**：提升会让操作更早甚至更多次执行，因此必须检查原本未执行的路径。
* **Sinking 与 DCE**：sinking 延后仍需要的计算；DCE 删除完全无可观察贡献的计算。
* **Strength reduction 与 constant folding**：前者利用规律递推降低重复成本，后者直接计算编译期已知值。
* **Induction variable 与源码 index**：归纳变量是 IR 中按固定关系演进的 value，不要求与源码循环变量一一对应。

本章结论
--------

循环内的工作应分成“根本不必重复”和“必须变化但可更便宜地变化”两类。LICM 把前者移出重复路径，strength reduction 把后者改成低成本 recurrence；两者都必须在 CFG、alias/effect、异常和 IR 数值语义证明成立后才能执行。