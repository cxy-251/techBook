第059章：Auto-Vectorization and SIMD Code Generation
====================================================

核心知识点
----------

* Auto-vectorization 把标量循环或局部标量操作改写成 SIMD vector operations，目标是让一条机器指令同时处理多个 data lanes。
* 向量化必须分成三步理解：legality 证明语义保持，profitability 判断是否值得，code generation 把 vector IR 映射到目标 ISA。
* SIMD 的收益来自规则性：多次操作同构、lane 之间独立、内存访问模式可被向量 load/store 或 gather/scatter 高效表达。
* Loop vectorization 沿迭代维度合并多个连续迭代；SLP vectorization 在同一 basic block/局部区域把多个相似独立标量操作打包成向量。
* Loop vectorization 常需要处理 trip count、vector width、tail/remainder、alignment 和 loop-carried dependence；SLP 更关注 pack 选择、shuffle 和局部依赖。
* Legality 的核心是跨 lane/跨迭代依赖。若第 ``i`` 次迭代读取第 ``i-1`` 次写入的结果，直接 widened execution 会破坏顺序。
* Alias analysis 是向量化关键输入。``restrict``/noalias 可直接证明数组互不重叠；只有 MayAlias 时，编译器可能生成 runtime pointer checks。
* Runtime versioning 的结构是“先检查 ranges 是否独立 → 满足则走 vector loop → 否则回退 scalar loop”，检查本身是优化正确性的保护条件。
* Reduction 是特殊依赖模式。整数/位运算或允许重排的浮点 reduction 可被向量化成多个 partial accumulators 再合并；严格浮点语义可能限制重排。
* Profitability 由 target cost model 决定，包括 vector width、指令吞吐、load/store 对齐、shuffle、gather/scatter、mask、epilogue 和 runtime check 成本。
* 更宽向量并不总更快。宽度过大可能增加 shuffle、寄存器压力、downclock 或尾部浪费。
* Target backend 最终决定 vector operation 是否有原生指令；不支持的向量操作可能被 legalize 成更窄向量或标量序列。
* Predication/masking 可以处理条件执行和尾部元素，但 mask 生成和 masked memory operation 也有成本。
* 自动向量化是否发生不能从源码循环外形直接判断，应结合 optimization remarks、vector IR 和最终 assembly 验证。

关键路径
--------

Loop vectorization：

::

   scalar loop
   → identify induction/trip count
   → dependence + alias checks
   → choose vector width/interleave factor
   → widen operations and memory accesses
   → create runtime guard if needed
   → create tail/epilogue path
   → lower vector IR to target SIMD

SLP：

::

   basic-block scalar operations
   → find isomorphic independent statements
   → build packs
   → estimate shuffle/extract/insert cost
   → form vector operations
   → target lowering

合法性检查：

::

   candidate lanes/iterations
   → inspect RAW/WAR/WAW dependencies
   → inspect alias and side effects
   → inspect reductions / recurrences
   → prove reordering allowed
   → vectorize or keep scalar

概念辨析
--------

* **Loop vectorization 与 SLP**：前者从连续迭代提取并行性，后者从局部相似语句提取并行性。
* **Vectorization 与 unrolling**：unroll 复制标量主体；vectorization 把同类标量 operations 合成向量 operation。
* **Legality 与 cost model**：合法只说明改写不破坏语义，成本模型还可能认为向量路径不划算。
* **NoAlias 与 runtime check**：静态 no-alias 可直接放行；证据不足时可通过运行时 guard 建立快路径条件。
* **Vector IR 与 SIMD instruction**：vector IR 是中间表示，后端仍需合法化并选择具体目标指令。

本章结论
--------

自动向量化本质是从标量程序中证明“多份相同工作可以同时执行”。编译器先用 dependence、alias 和语言语义证明 lane 独立或可安全重构，再用 target cost model 选择向量宽度与保护路径，最后把 vector IR 落到真实 SIMD 指令；源码看起来规则，只是候选，不是证明。