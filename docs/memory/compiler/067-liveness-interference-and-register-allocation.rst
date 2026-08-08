第067章：Liveness, Interference, and Register Allocation
========================================================

核心知识点
----------

* Register allocation 的直接问题是：哪些 virtual registers 在同一程序点仍然需要保留，哪些值可以复用同一个 physical register。
* Liveness 表示某个值在当前程序点之后是否仍可能被使用。一个值从 definition 到最后一次 relevant use 之间形成 live range。
* 活跃性通常是 backward data-flow 问题，因为“现在是否还要保留这个值”由未来 use 决定。
* 在直线代码中可从后往前维护 live set；在 CFG 中，basic block 的 live-out 由后继入口事实合并而来，再结合当前 block 的 use/def 反向传播。
* Interference 表示两个值的 live ranges 在某个时刻重叠，因此不能占用同一个会互相覆盖的 physical register。
* 没有 interference 只说明生命周期允许共享；最终仍要检查 register class、fixed operands、subregister overlap、call clobber 和指令 tied/early-clobber 等目标约束。
* Interference graph 用节点表示 live ranges，用边表示不能共用寄存器；graph coloring 把 physical registers 看成颜色，并要求相邻节点颜色不同。
* 当图在可用颜色数下无法着色时，分配器需要 spill、split live range、重写 copies 或改变分配选择。
* Linear scan 按 live intervals 的顺序快速分配，编译开销低，适合 JIT/快速编译；graph-coloring 类策略能进行更全局的冲突推理，但实现和编译成本更高。
* 真实工业分配器通常不是纯粹教科书算法，而会混合 live interval splitting、coalescing、eviction、priority、spill weight 和 target hints。
* Coalescing 尝试让 COPY 两端共享同一物理寄存器，从而消除 move；它必须避免把原本可着色的冲突图合并成难以分配的形状。
* Live range splitting 把一个长生命周期值拆成多个区段，使不同区段可使用不同寄存器或部分 spill，降低局部压力。
* Call instructions 会 clobber caller-saved registers，因此跨 call 的 live range 会额外干扰这些物理寄存器，或需要 save/reload。
* Register allocation 是在语义和资源之间调度“值的生命周期”。错误的 liveness 或 interference 会导致 still-live value 被覆盖，直接生成 wrong-code。

关键路径
--------

Liveness：

::

   machine def/use
   → start from block exits
   → propagate uses backward
   → kill at definitions
   → merge successor facts
   → obtain live-in / live-out
   → build live ranges

Interference：

::

   live ranges
   → detect overlapping lifetimes
   → apply register-class / alias constraints
   → build conflicts
   → choose compatible physical registers
   → spill/split if capacity insufficient

分配策略：

::

   prioritized live ranges
   → try preferred register / coalescing
   → check interference
   → assign / evict / split
   → spill lowest-value candidate when needed
   → rewrite machine code

概念辨析
--------

* **Liveness 与 source scope**：源码变量仍在作用域内不等于其机器值仍 live；后端看最后一次真实 use。
* **Live range 与 lifetime**：live range 是机器级“值必须可取”的区间，不等于语言对象的完整语义生命期。
* **Interference 与 dependence**：interference 关注两个值能否共用存储槽；data dependence 关注计算先后关系。
* **Graph coloring 与 linear scan**：前者从冲突图全局分配，后者按区间快速推进；二者目标相同，成本结构不同。
* **No interference 与 same register**：无冲突只是允许复用，还要满足 register class 和指令约束。

本章结论
--------

寄存器分配首先是活跃性问题，其次才是“选哪个寄存器”。稳定路径是 ``Def/Use → Liveness → Live Range → Interference → Allocation → Spill/Split``；只有准确知道每个值何时仍然重要，后端才能安全地让生命周期不重叠的值复用有限硬件寄存器。