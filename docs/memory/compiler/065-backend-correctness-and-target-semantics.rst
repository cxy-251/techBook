第065章：Backend Correctness and Target Semantics
=================================================

核心知识点
----------

* 后端正确性要求 lowering、legalization、instruction selection、scheduling、register/ABI lowering 后的目标行为与源 IR 在所有定义良好输入上的可观察语义一致。
* 判断后端 bug 的入口是 IR 语义，而不是“汇编看起来奇怪”。必须先明确 IR 的定义域、返回值、内存效果、异常/volatile/atomic 行为，再比较目标代码。
* ``nsw/nuw/exact``、poison、undef/freeze、fast-math flags 等都不是附加装饰，它们会改变后端可合法选择和重排的空间。
* ``add nsw`` 可以选择普通固定宽度机器加法，因为在 IR 定义良好的无溢出输入上结果一致；不能反过来把普通 wraparound IR 擅自当成带 ``nsw`` 的操作。
* Signed/unsigned compare 必须严格区分。目标条件码、operand order、flags 设置方式只要有一处映射错误，就会在定义良好的输入上产生 wrong-code。
* 隐式 flags、特殊状态寄存器也是语义依赖。Scheduler 若让中间指令覆盖后续 branch 需要的 flags，即使数据寄存器关系没错也会错误。
* 浮点后端必须遵守当前 IR 许可的 NaN、Inf、signed zero、rounding、reassociation、FMA 等规则。目标提供更强指令不等于 IR 自动允许使用其不同语义。
* Memory lowering/scheduling 还要保留 alias、volatile、atomic、ordering、barrier 和异常边界；机器级重排不能扩大 IR 允许的行为集合。
* ABI 是后端正确性的外部边界：参数位置、返回寄存器、stack alignment、callee/caller-saved registers、aggregate layout、varargs 和 unwind 规则必须符合平台约定。
* 调用约定错误可能让单个函数内部机器代码完全正确，却在函数边界读到错误参数、破坏保存寄存器或返回错误值。
* 后端测试必须分层：IR/MIR tests 检查 lowering 和机器表示；assembly tests 检查选择出的指令与约束；execution/differential tests 检查真实目标行为。
* Verifier/结构测试只能发现部分错误，无法证明所有 target instruction sequence 都语义等价，因此需要边界输入、随机测试、差分执行和真实硬件/模拟器覆盖。
* 后端 bug 本质是 IR semantics、target semantics 或 ABI contract 三者之一的映射断裂。

关键路径
--------

正确性检查：

::

   source IR semantics
   → identify defined input domain
   → lowering/legalization
   → instruction selection
   → scheduling/register/ABI lowering
   → target instruction semantics
   → compare observable behavior

后端错误定位：

::

   failing input
   → confirm IR behavior
   → inspect first differing MIR/assembly stage
   → check signedness / flags / poison / memory effects
   → check register and ABI constraints
   → reduce to minimal target-specific counterexample

测试分层：

::

   IR/MIR structural tests
   → instruction-selection assembly tests
   → ABI boundary tests
   → execution / differential tests
   → regression case for first bad transform

概念辨析
--------

* **IR UB 与 backend bug**：IR 已未定义的输入不能作为普通 wrong-code 反例；必须寻找 IR 仍有定义而目标行为不同的输入。
* **Poison 与普通任意值**：poison 有传播和触发规则，``freeze`` 后还要求后续 uses 看到一致具体值。
* **Signed compare 与 unsigned compare**：位模式相同不代表比较语义相同，目标 condition code 必须匹配 IR signedness。
* **Target instruction capability 与 IR permission**：硬件能做某种融合、饱和或快速浮点，不代表 IR 允许使用不同语义实现。
* **Function correctness 与 ABI correctness**：函数体内部计算正确仍可能因参数、返回值或保存寄存器规则错误而整体失败。

本章结论
--------

后端正确性就是维持 ``IR Semantics ↔ Target Semantics ↔ ABI`` 三方契约。每次 lowering 和机器级重排都必须保留定义良好输入上的值、内存、控制与边界行为；排查后端错误时，应从 IR 定义域出发，沿 MIR、目标指令和 ABI 找到第一个契约断裂点，而不是从最终汇编外观猜测。