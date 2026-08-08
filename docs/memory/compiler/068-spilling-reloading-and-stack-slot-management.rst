第068章：Spilling, Reloading, and Stack Slot Management
========================================================

核心知识点
----------

* Spill 是把暂时放不进物理寄存器的值写入当前函数的 stack slot，以释放寄存器；reload 是在后续 use 前把该值重新读回满足指令约束的寄存器。
* Spill/reload 保持的核心语义是“后续 use 仍看到原 virtual value”。寄存器位置可以消失，值本身不能被破坏。
* Spill 由 register pressure、register class、fixed operands、call clobber 和分配策略共同触发，并不只发生在“物理寄存器数量明显不够”时。
* Stack slot 在后端早期常以 frame index 等抽象位置存在，等 frame layout 确定后再 lower 成 ``sp/fp + offset`` 或目标等价地址。
* Spill slot 必须满足值大小、alignment、addressing mode 和目标 frame lowering 规则；向量、宽整数和特殊寄存器类可能需要更大或更严格对齐的 slot。
* Reload 的位置由 use 驱动。若目标指令需要寄存器操作数，被 spill 的值必须在该 use 前重新物化为可用寄存器。
* 某些目标支持 memory operands，可把 reload 折叠进算术指令；是否折叠仍受寻址、调度、异常和寄存器压力影响。
* Rematerialization 是 reload 的替代方案：若值是常量、简单地址或廉价表达式，使用点重新计算可能比从栈读取更便宜。
* Spill cost 取决于动态执行频率，不只是静态 store/load 数量。内层热循环中的一次 reload 可能被执行数百万次。
* 分配器通常结合 block frequency、loop depth、use count、reload 次数、rematerialization 成本和寄存器类别稀缺程度估计 spill weight。
* Spill 会引入真实 memory traffic、load-use latency、额外地址计算和调度依赖，也可能抵消 unrolling/vectorization 带来的收益。
* Stack slot 可以复用。若两个 spilled values 的内存生命周期不重叠，它们可以共享同一 frame 区域，从而减小 stack frame。
* Slot reuse 必须依据机器级生命周期和大小/对齐兼容性；源码变量名不同不代表必须分配不同栈位置。
* 过大的 stack frame 还可能影响 cache、stack probing、unwind、security instrumentation 和大偏移寻址，因此 slot packing 本身也属于后端质量问题。

关键路径
--------

Spill / reload：

::

   register pressure exceeds capacity
   → choose spill candidate
   → assign frame slot
   → insert store before value leaves register
   → keep slot as canonical saved value
   → reload before later use
   → continue allocation

Spill 成本：

::

   candidate live range
   → use frequency / loop depth
   → number of stores and reloads
   → rematerialization possibility
   → register-class scarcity
   → estimate dynamic cost
   → spill lowest-cost candidate

Stack slot 复用：

::

   spilled-value memory lifetimes
   → compare overlap
   → compare size / alignment
   → pack non-overlapping compatible slots
   → finalize frame offsets

概念辨析
--------

* **Spill 与普通局部变量存栈**：spill 是寄存器资源不足导致的机器级值迁移；源码局部对象可能因取地址等原因天然需要内存。
* **Reload 与 rematerialization**：reload 从 stack slot 读取旧值；rematerialization 在 use 点重新计算等价值。
* **Frame index 与 stack offset**：前者是后端抽象栈对象编号，后者是 frame layout 完成后的具体机器地址偏移。
* **Spill count 与 spill cost**：静态次数相同，热循环内的动态代价可能远高于冷路径。
* **Stack slot reuse 与 variable aliasing**：复用依据生命周期不重叠，不表示两个语言对象在同一时刻别名。

本章结论
--------

Spilling 是“寄存器稀缺”变成“内存流量”的时刻。应沿 ``Pressure → Spill Candidate → Stack Slot → Reload/Rematerialize → Slot Reuse`` 理解；好的后端不仅要保证值能从栈中正确恢复，还要把最昂贵的 spill 赶出热路径，并尽量压缩由这些临时值形成的栈帧。