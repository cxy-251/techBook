第088章：The LLVM Pass Manager and Analysis Preservation
=========================================================

核心知识点
----------

* LLVM middle-end 的核心循环是“先计算事实，再根据事实改写 IR”。Pass Manager 负责组织这些 analysis/transform actions，并维护分析结果的缓存与失效。
* Pass 是可调度的编译器工作单元。New Pass Manager 常见 IR 层级是 ``Module → CGSCC → Function → Loop``，每个 pass 应在最小足够粒度上运行。
* Analysis pass 读取 IR 并产出事实，例如 dominator tree、loop info、alias information、call graph 等；它不应无意修改 IR。
* Transform pass 根据已有事实改写 IR，例如 simplify CFG、DCE、instcombine、inline、loop transform 等；它必须同时保证语义等价和 IR 结构合法。
* Analysis manager 缓存某一级 IR unit 的 analysis result，避免多个 transform pass 反复重新计算昂贵事实。
* 缓存只有在事实仍与当前 IR 一致时才安全。Transform 修改 IR 后，旧 analysis 可能过期，因此必须准确报告 preservation/invalidation。
* ``PreservedAnalyses::all()`` 表示该 pass 没有破坏已有分析；``none()`` 是最保守结果，表示此前分析不能继续信任；实际 pass 可以声明只保留某些分析。
* CFG 改写通常会影响 dominator tree、post-dominator、loop info、branch probability 等；只做不改变控制流的局部 instruction rewrite 时，部分 CFG analyses 仍可能有效。
* 错误的 analysis preservation 是隐蔽 miscompilation 来源：当前 pass 本身可能改写正确，但后续 pass 读取了过期事实并据此做出错误转换。
* ``PassBuilder`` 负责注册 analyses、构造默认 optimization pipeline、解析 textual pipeline，并允许 frontend/backend/plugin 在 extension points 插入 pass。
* New Pass Manager 通常需要 ``LoopAnalysisManager``、``FunctionAnalysisManager``、``CGSCCAnalysisManager``、``ModuleAnalysisManager``，并通过 proxy/cross-registration 管理层级之间的查询与失效传播。
* Pass manager nesting 与 IR granularity 对应。Function pass 必须运行在 function pipeline，loop pass 需要 loop pipeline 或 adaptor；粒度不匹配不是语法小问题，而是 pass observation scope 不匹配。
* 默认 ``-O1/-O2/-O3`` pipeline 是策略组合而不是一个“超级优化”。多个 pass 通过 canonicalization、analysis、transform、cleanup 反复互相创造机会。
* Pass ordering 很重要。前一个 transform 可以让后一个 analysis 更准确，也可能使旧 analysis 失效；pipeline correctness 依赖顺序和失效协议同时正确。
* New Pass Manager 主要覆盖 LLVM middle-end；部分 backend codegen 仍有不同 pass-manager/version 边界，不能把所有 LLVM pass pipeline 统一假设成同一框架。
* 排查 pass interaction 时，应按 ``pass input IR → queried analyses → mutation → PreservedAnalyses → next pass`` 检查事实是否仍然可信。

关键路径
--------

Analysis/transform 协作：

::

   current IR unit
   → analysis manager computes/caches facts
   → transform queries facts
   → transform rewrites IR
   → pass reports PreservedAnalyses
   → invalidate stale cached facts
   → next pass queries valid/recomputed facts

New Pass Manager 层级：

::

   ModulePassManager
   → CGSCC adaptor/pipeline
   → FunctionPassManager
   → Loop adaptor/pipeline
   → individual pass

错误失效链：

::

   transform changes IR
   → incorrectly preserves old analysis
   → next pass receives stale result
   → proves transformation from false premise
   → wrong IR / miscompilation

概念辨析
--------

* **Analysis pass 与 transform pass**：前者产生 facts，后者消费 facts 并修改 IR。
* **Analysis cache 与 IR truth**：缓存只是性能机制；一旦 IR 改变，缓存内容必须重新证明有效。
* **Pass granularity 与 optimization scope**：granularity 决定 pass 一次看到的 IR unit，不能用更大/更小粒度随意替代。
* **Preservation 与 semantic preservation**：``PreservedAnalyses`` 描述 analysis cache 是否仍有效；semantic preservation 描述程序行为是否保持，两者是不同契约。
* **Default pipeline 与 fixed pass list**：默认 pipeline 随 LLVM 版本、target 和配置演进，稳定知识是层级、事实、失效和 pass interaction 模型。

本章结论
--------

Pass Manager 的核心不是“依次调用很多优化”，而是管理 ``IR → Facts → Rewrite → Fact Invalidation`` 的可信循环。只要 transform 会改变表示，就必须重新判断哪些分析仍能被后续 pass 信任；analysis preservation 是大型优化 pipeline 正确性与编译性能之间的关键协议。