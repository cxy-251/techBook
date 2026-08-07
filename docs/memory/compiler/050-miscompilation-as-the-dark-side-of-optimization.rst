第050章：Miscompilation as the Dark Side of Optimization
=======================================================

核心知识点
----------

* Miscompilation 指源程序在当前语言、编译选项和目标约束下具有定义良好语义，但编译器产物没有保持该语义。它与源程序本身触发 UB、越界或数据竞争等 bug 必须先区分。
* 判断 compiler bug 的第一步不是比较 ``-O0`` 与 ``-O2``，而是先证明失败输入属于源语言定义域。``-O0`` 正常只说明较少改写，并不能证明源码正确。
* 优化错误常来自“证明前提范围扩大”：某个事实只在特定分支、dominance 区域或内存状态下成立，却被错误当成全局事实使用。
* Speculative execution 是高风险点。把可能除零、trap、抛异常或产生副作用的 operation 提前到原本不会执行它的路径，会扩大执行域并可能改变定义良好的行为。
* Undefined Behavior 可被优化器利用，但 UB 前提必须保留原控制流条件。局部路径进入 UB 不代表其它路径也可以被当成未定义。
* 错误 side-effect 建模会导致错误删除、合并或重排。未知 call、``volatile``、atomic、I/O、异常和同步都必须按实际 effect contract 处理。
* Alias analysis 的错误结论尤其危险：把 may-alias 错判为 no-alias，可能让 load/store 被非法交换、复用或删除。
* Pass interaction 会产生 stale-analysis bug。前一 pass 改了 CFG、dominance、range、alias 或 effect 状态，后一 pass 若仍消费旧结果，就可能得到结构合法但语义错误的 IR。
* Verifier 只能捕获 type、dominance、phi/terminator 等结构不变量，不能证明所有 transform 都语义保持。IR 完全合法仍可能 miscompile。
* 定位错误应保存中间 IR 和 pass pipeline，找出“最后一个正确状态”和“第一个错误状态”。这比直接从最终汇编倒推通常更稳定。
* Reduction 是核心调试手段：最小化源码、输入、IR、函数与 pass 列表，保留最小可复现反例，减少无关语义和 pipeline 噪声。
* Differential testing 可以比较不同优化等级、不同编译器、解释执行或 reference implementation，但差异本身仍需结合语言定义域判断谁错。
* Bisect pass pipeline、逐 pass verifier、禁用某类优化、比较 IR diff、启用 sanitizer 都能帮助区分 source UB、frontend lowering、middle-end transform 与 backend codegen 问题。
* 优化器越强，依赖的 facts 和前提越复杂；一个错误证明可能穿过多轮 cleanup 后只在特定输入、特定优化等级或特定目标上表现出来。

关键路径
--------

Miscompilation 判定：

::

   failing input
   → prove source behavior is defined
   → compare source/reference behavior with optimized result
   → identify first representation where behavior diverges
   → inspect transform preconditions
   → classify compiler bug or source bug

Pass 定位：

::

   reproducible source/IR
   → capture exact compiler flags and target
   → dump pipeline/intermediate IR
   → bisect pass sequence
   → verify after each transform
   → isolate first bad pass
   → inspect stale/unsound facts

最小化：

::

   failing program
   → remove unrelated functions/data
   → simplify control flow and types
   → reduce input
   → reduce pass list
   → preserve failure
   → produce minimal counterexample

概念辨析
--------

* **Miscompilation 与 source UB**：只有源程序在该输入上有定义而目标行为不同，才能建立 miscompilation 反例。
* **O0/O2 差异与 compiler bug**：优化等级差异只是定位线索，不是错误证明。
* **Invalid IR 与 unsound transform**：前者可由 verifier 抓到；后者可能生成完全合法但语义错误的 IR。
* **Local fact 与 global fact**：range、nonzero、no-alias 等事实常带路径和作用域，越界使用会破坏优化证明。
* **Differential result 与 correctness proof**：实现之间结果不同能帮助发现问题，最终仍需语言/IR 语义判断正确结果。

本章结论
--------

Miscompilation 本质上是优化证明链断裂。排查时必须先确认源程序定义域，再沿“源码语义—IR—analysis facts—transform—pass interaction—后端”寻找第一个行为分歧点；越强的优化器越需要严格的前提作用域、analysis invalidation、verifier、reduction 和差分测试来约束错误证明。