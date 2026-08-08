第095章：MLIR in Heterogeneous and Domain-Specific Compilation
===============================================================

核心知识点
----------

* 异构编译的根本困难是不同硬件需要不同层级的程序事实。CPU、GPU、NPU、TPU、DSP、FPGA 对并行、内存、数据布局、同步和指令资源的关注点不同。
* 高层 domain IR 适合保留算子、shape、layout、广播、量化、代数关系等领域事实；低层 IR 适合暴露 address space、thread hierarchy、vector width、ABI、pointer 和 target instruction 等执行约束。
* MLIR 通过多个 dialect 把这些事实分层保存，使一个高层 matmul 可以逐步变成 tensor/linalg、affine/scf/vector、gpu 或 LLVM dialect，而不是一步坍缩成机器相关代码。
* ``tensor`` 层保留 rank、shape、element type 和 tensor value 语义，适合 shape inference、fusion 和高层 value transform。
* ``linalg`` 把线性代数写成 structured operations、indexing maps、iterator types 和 reduction regions，适合 tiling、fusion、destination-passing 和 vectorization 准备。
* ``affine``/``scf`` 把结构进一步落到循环和控制流，开始直接暴露 loop bounds、iteration space、memory access pattern 和 loop-carried dependencies。
* ``vector`` 层把硬件 SIMD/向量化所需的宽值、transfer、shuffle、contract 等结构显式化，为后续目标指令映射提供更直接证据。
* ``gpu`` dialect 表达 kernel、grid/block/thread hierarchy、address spaces、workgroup memory、barrier 与 offloading 边界，使并行映射进入 IR。
* ``LLVM`` dialect 把程序带入接近 LLVM IR 的函数、指针、结构体、整数/浮点、内存与调用语义，适合继续交给 LLVM optimizer/backend。
* Domain-specific compiler 的价值不是重新实现所有通用优化，而是用自定义 dialect 保留专属语义，再在合适阶段降低到可复用的 MLIR/LLVM 基础设施。
* 从 domain IR 到 target-specific IR 的每一步都在交换信息：高层名称可能消失，但 indexing、loop、memory 或 parallel mapping 必须以新的可验证结构继续承载原语义。
* CPU 路径通常更关注 cache blocking、loop/vector transform 和 ABI；GPU 路径更关注 kernel launch、thread mapping、shared memory 和 synchronization；专用加速器可能进一步显式表达 SRAM、DMA、tile、quantization 或 pipeline。
* 过早 lowering 会让领域 pass 失去算子级事实；过晚 lowering 会让 target mapping、memory planning 和 instruction selection 缺少足够低层信息。
* Optimization placement 应跟随证据：只有高层还保留的事实就在高层优化，只有低层才可证明的 machine constraints 则应在 lowering 后处理。
* Heterogeneous compilation 的稳定不变量仍然是语义保持。表示可以从一个 matmul op 变成 loops、threads、loads/stores 和 target calls，但最终输出元素关系必须与原计算一致。
* MLIR 的工程意义在于降低“语言 × 领域 × 硬件目标”组合爆炸：通过可组合 dialect 和逐级 conversion，让前端、领域优化和后端映射共享基础设施。

关键路径
--------

异构 lowering：

::

   domain operation
   → tensor / shape semantics
   → linalg structured computation
   → affine/scf loop structure
   → vector / memory mapping
   → choose target path
   → CPU: LLVM dialect/backend
   → GPU: gpu dialect → device backend
   → accelerator: hardware-specific dialect/runtime

优化放置：

::

   high-level algebra/shape facts available?
   → optimize before lowering
   → expose loop/memory structure
   → optimize locality/parallelism/vectorization
   → expose target resource constraints
   → perform target-specific mapping/codegen

概念辨析
--------

* **Domain IR 与 target IR**：前者强调领域计算含义，后者强调硬件资源与执行规则；两者应通过可验证 lowering 连接。
* **Tensor 与 memref/buffer**：tensor 强调整体值和 shape，buffer 强调存储身份、布局、生命周期和 mutation。
* **Linalg 与 ordinary loops**：linalg 仍保留 indexing/reduction 等结构化线性代数语义，普通循环则把这些关系进一步展开。
* **GPU dialect 与 GPU machine code**：GPU dialect 表达中层并行/设备语义，仍需继续 lower 到 NVVM/ROCDL/SPIR-V 或其它目标形式。
* **High-level optimization 与 target-specific optimization**：前者消费领域结构，后者消费机器约束；它们适合放在不同 lowering 阶段。

本章结论
--------

异构编译的稳定模型是 ``Domain Semantics → Structured Compute → Loop/Memory/Vector → Target Mapping → Backend``。MLIR 的作用不是提供一个万能 IR，而是提供可组合的语义层级，让领域优化和硬件映射各自在证据最充分的阶段工作，并通过 dialect conversion 把这些阶段可靠连接起来。