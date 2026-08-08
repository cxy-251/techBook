第111章：Neural Networks as Computation Graphs
===============================================

核心知识点
----------

* AI 编译器真正优化的对象通常不是 Python 调用序列，而是由 operator 节点与 tensor 边组成的 computation graph。节点描述计算，边描述值与依赖关系。
* Eager execution 逐个算子立即执行，便于调试；graph compilation 先捕获一段计算，再跨 operator 分析、重写、融合和调度。
* 图表示会保留 operator kind、输入输出、parameter、constant、shape、dtype、layout 等编译事实，同时丢弃大量 Python 对象组织、局部变量名和框架调用表面结构。
* Tensor 边不只是“连线”，还携带类型化元数据。编译器依赖这些事实判断 MatMul 内维、broadcast、layout compatibility 和后端 lowering 是否合法。
* Parameter 与 constant 都可能在运行前已知，但语义不同：parameter 是模型状态，constant 是固定计算值。Constant folding、weight packing 和持久化存储会分别利用这些属性。
* Reshape、Transpose 等节点 FLOPs 很低，却可能改变 stride/layout 并触发真实数据搬运；图优化不能只看算术量。
* 图边界决定编译器当前能控制的范围。外部 Python 调用、I/O、无法建模的副作用或动态控制可能造成 graph break，切断跨节点优化。
* Dynamic shape 不等于“完全未知”。Rank、部分静态维、符号维和维度关系都可以保留为约束，并由 runtime guard 在执行时验证。
* 对动态输入，系统可以选择 symbolic executable，也可以针对常见 batch/sequence length specialization；前者减少编译版本，后者换取更强优化。
* AI 模型从调用序列变成图后，编译器才真正获得跨算子的 use-def、shape propagation、constant folding、fusion、memory planning 和 backend partition 能力。

关键路径
--------

模型进入编译器：

::

   framework program
   → capture / export
   → operator graph
   → annotate tensor shape/dtype/layout
   → infer dependencies and symbolic constraints
   → graph optimization
   → tensor/kernel lowering
   → runtime executable

动态图处理：

::

   runtime input
   → bind rank/dtype/device/shape
   → symbolic shape propagation
   → guard specialization assumptions
   → cache hit: reuse executable
   → guard miss: alternate executable / recompile / fallback

概念辨析
--------

* **Eager execution 与 graph compilation**：前者以单次算子调用为执行单位，后者以一段可捕获计算图为优化单位。
* **Operator 与 tensor**：operator 是计算规则，tensor 是沿数据流传播的值；优化依赖二者之间的 use-def 关系。
* **Parameter 与 constant**：parameter 是模型状态，constant 是固定值；二者都可能编译期已知，但生命周期和处理策略不同。
* **Dynamic shape 与 unknown program**：动态维度可以被符号化，编译器仍能保留 rank、静态维和维度关系。
* **Graph break 与 control flow**：动态控制流本身不必然导致 graph break；是否断图取决于捕获系统和 IR 能否表示该语义。

本章结论
--------

AI 编译的起点是 ``Framework Calls → Typed Computation Graph``。图把模型从“逐条调用”改造成可分析的数据依赖系统；只有当 operator、tensor metadata、动态边界和副作用被显式表示后，跨算子融合、内存规划与后端 specialization 才有可靠依据。
