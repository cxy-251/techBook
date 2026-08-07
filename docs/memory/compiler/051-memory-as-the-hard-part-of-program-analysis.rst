第051章：Memory as the Hard Part of Program Analysis
====================================================

核心知识点
----------

* 普通 SSA value 的定义与使用直接写在 IR 中；内存值通过地址间接访问，某次 ``load`` 到底读到哪次写入，需要结合地址、控制流和副作用共同判断。
* ``load`` 是“内存状态 -> SSA value”的边界；``store`` 是“SSA value -> 内存状态”的边界。``load`` 有明确 SSA result，但 result 的值来源不等于它自己的定义指令。
* 内存状态不仅包括堆，还包括栈槽、全局变量、对象字段、数组元素、闭包捕获、运行时元数据以及内存映射 I/O 等。
* 函数调用会扩大隐藏状态。若缺少 effect summary，调用通常必须视为可能读写可达内存、抛异常或触发其它运行时行为的边界。
* 跨 CFG 判断一次读取来源，需要同时回答：哪些写入能到达这里、这些写入是否访问同一地址范围、中间是否存在 clobber、当前路径实际经过哪些 predecessor。
* Alias fact 决定内存依赖强度。``NoAlias`` 可排除无关写入；``MustAlias`` 可把写入和读取绑定到同一位置；``MayAlias`` 要保守保留多个可能来源。
* 仅有 dominance 不足以证明内存值不变。一个支配当前 ``load`` 的旧 ``load`` 或 ``store``，仍可能被中间可能别名的写入或调用覆盖。
* MemorySSA 的核心价值是给内存访问建立类似 SSA 的版本关系：可能修改内存的操作形成 ``MemoryDef``，读取形成 ``MemoryUse``，控制流合流通过 ``MemoryPhi`` 汇总内存版本。
* MemorySSA 并不会自动解决 alias。它提供内存版本图，真正判断某个 ``MemoryDef`` 是否 clobber 当前访问，仍需要 alias/effect information。
* 内存优化的通用前提是“证明当前访问看到的内存版本”。Load elimination、store forwarding、LICM、DSE、GVN 等都建立在这个问题上。
* ``volatile``、atomic、fence、异常调用和外部 I/O 会引入额外顺序与可观察性约束，不能只按普通 load/store 的数据依赖处理。
* 内存事实越弱，优化器越应保守。多保留一次 load 通常只是性能损失；错误忽略一次可能写入则会直接改变程序语义。

关键路径
--------

读取来源分析：

::

   load address + size
   → walk dominating memory accesses
   → query alias / ModRef
   → filter unreachable paths
   → find possible clobbering MemoryDefs
   → determine visible memory version
   → keep, forward, or eliminate load

跨控制流内存合流：

::

   predecessor A memory state
   + predecessor B memory state
   → merge at CFG join
   → MemoryPhi / equivalent memory version
   → downstream load queries merged state

普通 SSA 与内存关系：

::

   SSA producer
   → explicit def-use

   store/call
   → hidden memory state change
   → alias/effect analysis
   → load
   → new SSA value

概念辨析
--------

* **SSA definition 与 load value source**：``load`` 是 SSA result 的定义点，但其读取内容来自此前某个内存版本。
* **Value dependency 与 memory dependency**：前者可由 operand 直接表达；后者通常必须通过地址、alias 和 effect 分析恢复。
* **Dominance 与 memory availability**：定义支配使用只是必要条件之一；中间 clobber 仍可能让旧内存值失效。
* **MemorySSA 与 alias analysis**：MemorySSA 组织内存版本，alias analysis 判断两个访问是否可能触碰同一范围，两者互补。
* **Hidden state 与 unknown state**：内存状态并非不可分析，只是需要显式构造额外关系；证据不足时才保守视为未知。

本章结论
--------

内存分析的核心不是“看到 load/store”，而是证明“当前 load 能看到哪个 memory version”。普通 SSA 把值关系天然显式化，内存则必须借 CFG、alias、effect 和 MemorySSA 等结构恢复读写关系；任何跨内存的删除、复用或移动，都必须先证明中间没有改变目标位置的可观察状态。