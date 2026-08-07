第056章：Loop Dominance in Performance Engineering
===================================================

核心知识点
----------

* 循环优化的价值来自重复次数放大。一次 load、branch、add 或索引更新很便宜，执行数百万次后就可能成为主成本。
* 性能判断不能只看源码长度，必须结合 trip count、backedge-taken count、block frequency 和真实 workload 热度。
* Hot loop 是运行时 profile 证明高频或高耗时的循环；profile 决定“是否值得优化”，不替代语义合法性证明。
* 循环成本可粗分为 setup、per-iteration body 和 exit。优化重点通常落在重复路径中的计算、内存、分支和依赖链。
* CFG 中自然循环由 header、latch、backedge、preheader、exiting block 和 exit block 等结构描述；源码 ``for``/``while`` 只是前端表面形式。
* Header 是循环入口并支配循环内节点；latch 含回到 header 的 backedge；preheader 位于循环外并作为进入循环前的稳定落点。
* LoopInfo/等价分析把循环组织成层级结构。内层循环的重复成本常被外层 trip count 再次放大，因此通常更值得优先观察。
* Irreducible control flow 没有单一支配 header，会破坏许多经典 loop pass 的结构前提，往往需要先规范化或直接放弃某些优化。
* Loop canonicalization 的目标是让后续 pass 面对稳定结构，例如 preheader、single latch/backedge、dedicated exits 和 LCSSA。
* Preheader 让 LICM 有稳定插入点；single latch 让 induction variable 更新更容易分析；dedicated exit/LCSSA 让循环内外值边界更明确。
* Canonical form 不是性能优化本身，而是后续 LICM、unroll、vectorize、induction/range analysis 的输入契约。
* 循环优化必须同时读取静态结构与动态热度：CFG 决定“能否改”，profile/cost model 决定“值不值得改”。

关键路径
--------

热点循环定位：

::

   runtime profile
   → hot function / hot block
   → identify loop and trip count
   → classify repeated cost
   → inspect memory / branch / arithmetic / dependence bottleneck

循环结构识别：

::

   CFG
   → find header
   → find latch + backedge
   → find preheader
   → find exiting / exit blocks
   → build loop hierarchy

规范化：

::

   arbitrary natural loop
   → create preheader if needed
   → normalize latch/backedge
   → create dedicated exits
   → establish LCSSA / stable boundary
   → hand to loop transforms

概念辨析
--------

* **源码循环与 IR loop**：源码语法会消失；优化器真正操作的是 CFG 中的循环区域和 value/memory 关系。
* **Hotness 与 legality**：热度影响收益判断；合法性仍由控制流、依赖、副作用和语言语义决定。
* **Header 与 preheader**：header 属于循环并接收回边，preheader 位于循环外且只在进入循环时执行。
* **Canonicalization 与 optimization**：规范化主要建立稳定结构，不必直接减少运行成本。
* **Trip count 与源码边界**：编译器关心实际执行次数/回边次数，不只关心源码写出的循环条件。

本章结论
--------

循环性能工程应按“Profile—CFG Loop Structure—Trip Count—Canonical Form—Repeated Cost”理解。先找真正热点，再把循环整理成可分析的 header/preheader/latch/exit 结构，后续优化才能稳定地减少重复计算、内存访问和控制开销。