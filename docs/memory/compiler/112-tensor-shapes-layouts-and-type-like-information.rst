第112章：Tensor Shapes, Layouts, and Type-Like Information
==========================================================

核心知识点
----------

* Tensor metadata 是 AI 编译器的“类型事实集合”，通常至少包括 shape、dtype、layout、quantization 和 device/memory-space 信息。
* Shape 描述 rank 与各维大小。维度可以静态已知，也可以是 symbolic/dynamic；编译器需要区分“rank 已知但尺寸未知”和“整个结构未知”。
* Shape inference 根据算子 schema、输入 shape、属性与常量推导输出 shape；constraint propagation 则传播维度等式、不等式和符号关系。
* Broadcasting 本质是索引映射规则。合法性不仅要求 rank/维度兼容，还要求后端能把广播关系 lower 成正确访问模式。
* DType 决定元素存储宽度、数值范围、舍入行为和可选硬件路径。``f16``、``bf16``、``int8`` 即使占用相似空间，也具有不同数值语义。
* Quantization 不能只看 ``int8``。scale、zero point、axis、block size、accumulator dtype 与 requantization 规则共同决定低精度值的真实含义。
* Layout 描述逻辑 tensor index 如何映射到线性内存；同样的 shape/dtype 可以使用 NCHW、NHWC、channels-last、tiled、packed 或后端私有布局。
* 逻辑维度顺序与物理 layout 必须区分。看到 ``NCHW`` 不能直接推出内存一定 contiguous NCHW，还要检查 stride/layout attribute。
* Layout conversion 可能比算术节点更昂贵。一次转换是否值得，取决于后续多少 kernel 能复用新布局，以及转换是否可以被消除或融合。
* Shape、dtype、layout 和 quantization 都参与 kernel legality。某个算子在数学上合法，不代表目标后端存在匹配的低精度或布局实现。
* 动态 shape 会把部分检查推迟到 runtime guard；静态维越多，kernel specialization、buffer sizing、tiling 和 vectorization 的空间通常越大。
* 元数据优化的核心目标是让“哪些事实已知、哪些事实动态、哪些事实必须保持”在 IR 中显式化。

关键路径
--------

Tensor 元数据推理：

::

   graph input signature
   → infer rank/static/symbolic dimensions
   → propagate operator shape constraints
   → infer dtype / quantization semantics
   → propagate layout or stride facts
   → validate broadcasting and backend requirements
   → emit runtime guards for remaining dynamic facts

Layout 决策：

::

   logical tensor shape
   → candidate memory layouts
   → inspect producer/consumer requirements
   → estimate conversion cost vs kernel benefit
   → propagate chosen layout
   → eliminate redundant conversions
   → lower indexing to physical addresses

概念辨析
--------

* **Shape 与 layout**：shape 描述逻辑维度，layout 描述这些维度如何落到内存。
* **DType 与 quantization**：dtype 给出存储/基本算术类型，quantization 还需要 scale、zero point 等映射语义。
* **Static dimension 与 symbolic dimension**：前者编译期已知具体值，后者虽未知具体值但仍可参与约束关系。
* **NCHW logical shape 与 NCHW contiguous memory**：逻辑维度顺序与物理 stride 是不同事实。
* **Type correctness 与 backend executability**：metadata 合法只是第一步，后端还必须支持对应 dtype/layout/kernel 组合。

本章结论
--------

AI 编译器读取 tensor 时，应按 ``Shape → DType/Quantization → Layout → Constraint Propagation`` 建立事实链。Tensor metadata 决定算子是否合法、buffer 多大、地址怎样计算以及能选择什么 kernel；它实际上承担了传统类型系统与内存布局系统的双重职责。
