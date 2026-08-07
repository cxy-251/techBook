第047章：Analysis Passes vs Transform Passes
============================================

核心知识点
----------

* Optimizer 的工作可以分成“生产事实”和“消费事实”两类。Analysis pass 读取 IR 并计算事实，transform pass 根据事实改写 IR。
* Analysis pass 的典型输出包括 CFG、dominator tree、loop info、alias results、liveness、range facts、call graph、block frequency 等。它本身不应改变被分析对象的语义形状。
* Transform pass 会删除、替换、移动、复制或重构 instruction、basic block、loop、function 和 call edge，例如 DCE、CFG simplification、inlining 和 loop transform。
* Transform 可以查询多个 analysis，但查询事实不等于 analysis。区分点在于 pass 是否真正 mutation IR。
* Analysis result 绑定于特定 IR 版本。IR 一旦变化，旧结果可能完全失效、部分可保留，或需要增量更新。
* Pass manager 的关键职责之一是缓存 analysis 并处理 preservation/invalidation。错误复用 stale analysis 会让后续 transform 用旧世界的事实证明新世界的改写。
* 改动 instruction use-list 但不改 CFG，可能仍保留 CFG/dominance 类结果；改动 branch、predecessor 或 block 则通常会影响 reachability、dominance、loop、frequency 等控制流分析。
* Analysis preservation 应尽量精确。全部失效虽然安全，却增加重复计算；错误声明 preserved 则可能直接造成 miscompilation。
* Pass 有不同粒度：loop、function、CGSCC、module 等。粒度决定可见上下文、缓存单位、改写范围和需要维护的不变量。
* Function pass 适合函数内 CFG/value 优化；loop pass 聚焦循环结构；CGSCC 可处理递归相关的调用图区域；module pass 可访问全模块符号和跨函数信息。
* Pass manager 还负责在不同 IR unit 之间调度 adaptor、分析查询和 invalidation，使局部 pass 能嵌入更大的 pipeline。
* 优化器的稳定节奏是 ``analysis -> transform -> invalidate/update -> analysis``。事实不是永久真理，只是当前 IR 的快照。

关键路径
--------

Analysis pass：

::

   current IR unit
   → scan structure / values / effects
   → compute facts
   → cache analysis result
   → expose query interface

Transform pass：

::

   current IR
   → query required analyses
   → prove rewrite preconditions
   → mutate instructions / CFG / calls
   → repair IR invariants
   → declare preserved analyses
   → invalidate or recompute the rest

Pass manager：

::

   schedule IR unit
   → provide cached analyses
   → run pass
   → receive preservation result
   → keep valid caches
   → drop stale caches
   → continue pipeline

概念辨析
--------

* **Analysis 与 transform**：前者回答“程序目前是什么”，后者把程序改成另一个等价表示。
* **Analysis cache 与 immutable truth**：缓存只对产生它的 IR 状态有效，不能跨任意改写永久复用。
* **Preservation 与 recomputation**：能证明未受影响的分析可保留；其余必须更新或重新计算。
* **Pass granularity 与 optimization strength**：更大粒度提供更多上下文，但也带来更高成本和更复杂失效关系。
* **IR mutation 与 semantic change**：transform 改变表示形状，不等于改变程序语义；合法 transform 必须语义保持。

本章结论
--------

优化管线应理解为“学习事实—使用事实—让旧事实失效—重新学习”的循环。Analysis pass 负责建立可靠证据，transform pass 负责在证据约束下改写 IR，pass manager 则保证任何缓存事实只在仍然有效时被后续优化使用。