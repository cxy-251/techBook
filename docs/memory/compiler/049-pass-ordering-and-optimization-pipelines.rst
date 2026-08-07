第049章：Pass Ordering and Optimization Pipelines
=================================================

核心知识点
----------

* Pass pipeline 不是若干优化名称的简单列表，而是“哪个 IR unit 上、以什么顺序、运行哪些 analysis/transform、何时清理、何时重新分析”的执行策略。
* Pass 顺序决定后一个 pass 能看到什么事实。Inline 能暴露跨函数算术，constant propagation 能暴露恒定 branch，CFG cleanup 能减少路径，随后 CSE/DCE 才可能获得更多证明机会。
* 某个 pass 当前没有产生变化，并不代表它无用；它可能只是运行得太早，所需的 canonical form、constant fact、alias fact 或 call-context 尚未出现。
* 大型 transform 往往产生临时噪声：多余 block、dead phi、重复 expression、unused temporary、恒定 branch。需要 InstCombine/SimplifyCFG/DCE/GVN 等 cleanup 恢复紧凑 IR。
* Cleanup 过早会重复工作，过晚会让昂贵分析处理膨胀 IR。pipeline 设计需要在清理成本和后续输入规模之间权衡。
* Analysis invalidation 是 pipeline 成本的一部分。频繁 CFG 改写会迫使 dominance、loop、frequency 等事实重新计算；稳定阶段则可以复用缓存降低编译时间。
* ``O0/O1/O2/O3/Os/Oz`` 应理解为预设策略，而不是单维度“优化强度”。它们同时权衡编译时间、运行性能、代码大小、调试体验和目标平台成本。
* ``O0`` 更偏向快速编译和源码级调试形态；``O2`` 通常是通用性能平衡；``O3`` 会采用更激进且可能增大代码的优化；``Os/Oz`` 更重视代码体积。
* 更激进的 inline、unroll、vectorization 并不保证程序更快。代码膨胀可能恶化 I-cache、寄存器压力、分支布局和移动端功耗。
* Pipeline tuning 必须结合语言语义。前端可以通过 attributes、intrinsics、ownership/effect 信息给优化器提供更强事实，也可能要求某些 lowering/cleanup 在特定阶段完成。
* Pipeline tuning 也必须结合 target。寄存器数量、向量宽度、指令成本、调用约定、cache、GPU/CPU 特性会改变某些 transform 的收益阈值。
* Pass 粒度与顺序相互约束：module/CGSCC pass 可以创造跨函数事实，function pass 消费局部值图，loop pass 再处理循环结构，后续还可能回到 function cleanup。
* 调整 pipeline 必须依赖证据：IR diff、pass timing、代码大小、运行 benchmark、profile、compile-time 和 target metrics，而不是只凭 pass 数量判断质量。

关键路径
--------

机会创造链：

::

   call boundary
   → inline
   → expose constants/repeated expressions
   → instcombine / constant propagation
   → simplify CFG
   → CSE/GVN
   → DCE
   → compact IR for later passes

Pipeline 设计：

::

   define optimization goal
   → list pass preconditions
   → order passes so earlier stages expose those facts
   → insert cleanup after disruptive transforms
   → manage analysis invalidation
   → benchmark compile time / runtime / size
   → retune thresholds and order

优化等级选择：

::

   development/debugging → O0/O1-like strategy
   general release performance → O2-like strategy
   aggressive hot-path performance → O3-like strategy with measurement
   size-constrained target → Os/Oz-like strategy

概念辨析
--------

* **Pass ordering 与 correctness**：合法 pass 不因顺序改变程序语义，但顺序会显著改变能发现的优化机会、编译成本和最终代码形状。
* **Cleanup 与 primary optimization**：cleanup 主要恢复简洁/规范 IR，也会顺带暴露新的优化机会。
* **Optimization level 与固定 pass 列表**：等级是整体策略，具体 pass、阈值和顺序会随编译器版本与目标变化。
* **O3 与必然更快**：更激进优化可能因代码膨胀或硬件效应变慢，必须用目标工作负载验证。
* **Generic pipeline 与 target-specific pipeline**：通用中端提供基础策略，语言和硬件事实决定最终调优。

本章结论
--------

优化 pipeline 的本质是安排“机会如何被创造、消费和清理”。正确的顺序让前一阶段暴露后一阶段需要的事实，并在每次大改写后控制 IR 膨胀和 analysis 失效；优化等级只是这种策略的预设入口，最终效果必须用编译时间、运行性能和代码大小共同验证。