第114章：Lowering Tensor IR to Kernels
=======================================

核心知识点
----------

* Graph IR 关心 operator 与 tensor 依赖，Tensor IR 进一步显式表示 iteration space、indexing map、reduction、broadcast、buffer 与调度约束。
* 一个高层算子真正进入 kernel 前，需要从“数学节点”变成“每个输出元素如何由循环、索引和内存访问产生”的程序。
* ``Y = relu(matmul(A, B) + bias)`` 在 Tensor IR 中会显式暴露 ``i``、``j`` 输出维与 ``k`` reduction 维，以及 ``A[i,k]``、``B[k,j]``、``bias[j]`` 的访问关系。
* Structured tensor op 比裸 loop nest 多保留一层语义，例如 parallel/reduction iterator、indexing map 和 contraction 结构，因此更适合 tiling、fusion、vectorization 等高层变换。
* Graph-level fusion 与 kernel-level fusion不是同一层。图中三个节点可先合成一个 tensor computation，随后再决定怎样生成循环、tile 和写回路径。
* Bufferization 把不可变 tensor SSA value 转成可写 buffer/memref，并决定 in-place reuse、copy、alias 和 lifetime。
* In-place buffer reuse 的前提是旧内容在写入后不再被需要，且 alias/ownership/可写性约束允许。错误复用会直接破坏语义。
* Bufferization 之后 layout、stride、offset、address space 都会进入真实地址计算；多余 copy 往往来自 RaW conflict、未知 op、保守 alias 或 layout mismatch。
* Scheduling 决定同一 Tensor IR 如何映射硬件：tiling 改善数据复用，vectorization 利用 SIMD/vector units，unrolling 减少 loop overhead，thread binding 把 iteration 映射到 CPU threads 或 GPU block/thread/warp。
* MatMul 性能通常取决于数据移动而不是公式本身。Tile 的目标是让 A/B 子块在 cache、shared memory 或寄存器中复用，减少反复访问 global memory。
* Reduction 维不能像普通并行维一样随意拆分；并行 reduction 需要 partial sum 合并，并受浮点重排语义限制。
* CPU、GPU、NPU/TPU 需要不同 schedule。CPU 关注 cache/SIMD/NUMA，GPU 关注 coalescing/shared memory/occupancy，专用加速器常要求固定 tile、片上 SRAM 与 DMA 约束。
* Tensor lowering 的正确性来源于 shape、dtype、indexing、reduction、side effect 和边界 mask 的共同保持；profitability 则来自目标硬件成本模型。

关键路径
--------

Tensor lowering：

::

   graph operator / fused subgraph
   → structured tensor operation
   → expose iteration space + indexing maps
   → lower to loops / tiles
   → bufferization + alias/lifetime decisions
   → vectorize / unroll / thread binding
   → map memory hierarchy
   → backend kernel / library primitive

MatMul 语义到执行：

::

   Y[i,j] = sum_k A[i,k] * B[k,j]
   → identify i,j parallel dimensions
   → identify k reduction dimension
   → tile M/N/K
   → stage A/B tiles into cache/shared memory
   → accumulate in registers
   → apply bias/activation epilogue
   → write Y

概念辨析
--------

* **Graph IR 与 Tensor IR**：前者描述算子依赖，后者描述元素级 iteration、indexing 与更具体的执行结构。
* **Tensor value 与 buffer**：tensor SSA 强调值语义，buffer 强调可写存储、别名和生命周期。
* **Fusion 与 tiling**：fusion 改变 producer-consumer 执行边界，tiling 改变同一 iteration space 的分块与数据复用方式。
* **Parallel dimension 与 reduction dimension**：前者输出之间通常独立，后者多个迭代共同产生一个结果。
* **Legal schedule 与 fast schedule**：依赖关系允许某种重排，不代表它在目标硬件上一定高效。

本章结论
--------

Tensor lowering 的稳定主线是 ``Graph Semantics → Iteration/Indexing → Bufferization → Schedule → Hardware Kernel``。AI 算子最终不是以“MatMul”“Conv”这些名字运行，而是以具体循环、tile、buffer、线程、向量 lane 与内存层级执行；性能差异主要在这些低层映射中形成。
